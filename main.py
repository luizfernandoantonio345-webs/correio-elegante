"""
Correio Elegante Anônimo — Arraiá TI
Backend FastAPI + bot do Telegram + banco (SQLite por padrão, Postgres se quiser).

Fluxo:
  - Pessoa ativa o bot no Telegram (dá /start) -> vira "registrada" e pode receber na hora.
  - Barraca cria um correio (pra quem, mensagem, anônimo) -> se a pessoa estiver
    registrada, o bot manda na hora; senão, gera link + QR pra ela abrir o envelope.
  - Telão mostra o que está rolando + QR pra ativar o bot.
  - Moderação esconde mensagem ofensiva (filtro de palavrão automático também).

Rode com:  uvicorn main:app --reload
Veja o README.md para criar o bot e colocar online.
"""
import os, secrets, asyncio, html, re, json, threading, time
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from filtro import analisar
from pydantic import BaseModel
from sqlalchemy import (create_engine, String, Integer, Boolean, DateTime, Text,
                        select, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

# ----------------------------------------------------------------------------
# Configuração (variáveis de ambiente)
# ----------------------------------------------------------------------------
TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
BASE_URL  = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_KEY = os.getenv("ADMIN_KEY", "trocar-essa-chave")
DB_URL    = os.getenv("DATABASE_URL", "sqlite:///correio.db")
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)
if DB_URL.startswith("postgresql://") and "+psycopg2" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

API = f"https://api.telegram.org/bot{TOKEN}"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------
# Banco de dados
# ----------------------------------------------------------------------------
engine = create_engine(
    DB_URL, echo=False,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
)

class Base(DeclarativeBase): pass

class Usuario(Base):
    __tablename__ = "usuarios"
    chat_id:   Mapped[int]  = mapped_column(Integer, primary_key=True)
    username:  Mapped[str]  = mapped_column(String(64), default="")
    codinome:  Mapped[str]  = mapped_column(String(64), default="")
    aguardando_codinome: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Correio(Base):
    __tablename__ = "correios"
    id:        Mapped[int]  = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo:    Mapped[str]  = mapped_column(String(12), unique=True, index=True)
    para:      Mapped[str]  = mapped_column(String(120))
    mensagem:  Mapped[str]  = mapped_column(Text)
    de:        Mapped[str]  = mapped_column(String(120), default="")
    anonimo:   Mapped[bool] = mapped_column(Boolean, default=True)
    remetente_real: Mapped[str] = mapped_column(String(120), default="")  # registro interno (privado)
    ip:             Mapped[str] = mapped_column(String(64), default="")
    user_agent:     Mapped[str] = mapped_column(String(300), default="")
    termos:         Mapped[str] = mapped_column(String(300), default="")  # termos detectados pelo filtro
    via:       Mapped[str]  = mapped_column(String(20), default="link")   # link | telegram
    entregue:  Mapped[bool] = mapped_column(Boolean, default=False)
    oculto:    Mapped[bool] = mapped_column(Boolean, default=False)        # moderação
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
ALFA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sem letras/números confusos (0/O, 1/I)
def gerar_codigo(n: int = 4) -> str:
    return "".join(secrets.choice(ALFA) for _ in range(n))

# Filtro de palavrão/bullying/racismo está em filtro.py (analisar()).

def achar_usuario(s: Session, para: str):
    alvo = para.strip().lstrip("@").lower()
    if not alvo:
        return None
    u = s.scalars(select(Usuario).where(func.lower(Usuario.username) == alvo)).first()
    if u:
        return u
    return s.scalars(select(Usuario).where(func.lower(Usuario.codinome) == alvo)).first()

# ----------------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------------
BOAS_VINDAS = (
    "💌 <b>Bem-vindo(a) ao Correio Elegante do Arraiá TI!</b>\n\n"
    "Pra galera conseguir te mandar correio, me diga como você quer ser chamado(a) "
    "(seu nome e turma, ex.: <i>Ana 3ºB</i>). É só responder essa mensagem 👇"
)

async def enviar_telegram(chat_id: int, texto: str) -> bool:
    if not TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{API}/sendMessage", json={
                "chat_id": chat_id, "text": texto,
                "parse_mode": "HTML", "disable_web_page_preview": False,
            })
            return r.status_code == 200
    except Exception as e:
        print("[telegram] erro ao enviar:", e)
        return False

def texto_correio(para: str, mensagem: str, de: str, link: str) -> str:
    return (
        "💌 <b>Você recebeu um correio elegante!</b>\n\n"
        f"<b>Para:</b> {html.escape(para)}\n"
        f"“{html.escape(mensagem)}”\n\n"
        f"<i>De: {html.escape(de)}</i>\n\n"
        f"✨ Veja com o envelope animado: {link}"
    )

async def tratar_update(upd: dict):
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return
    chat_id  = msg["chat"]["id"]
    texto    = (msg.get("text") or "").strip()
    username = (msg.get("from", {}).get("username") or "").strip()

    try:
        with Session(engine) as s:
            u = s.get(Usuario, chat_id)

            if texto.startswith("/start"):
                if not u:
                    u = Usuario(chat_id=chat_id, username=username, aguardando_codinome=True)
                    s.add(u)
                else:
                    u.username = username or u.username
                    u.aguardando_codinome = True
                s.commit()
                await enviar_telegram(chat_id, BOAS_VINDAS)
                return

            if u and u.aguardando_codinome and texto and not texto.startswith("/"):
                u.codinome = texto[:64]
                u.aguardando_codinome = False
                u.username = username or u.username
                s.commit()
                extra = f" ou <b>@{username}</b>" if username else ""
                await enviar_telegram(
                    chat_id,
                    f"Prontinho! Agora a galera pode te mandar correio como "
                    f"<b>{html.escape(u.codinome)}</b>{extra}.\nBoa festa!")
                return

            await enviar_telegram(chat_id, "Manda /start pra ativar seu correio elegante")
    except Exception as e:
        print(f"[bot] erro em tratar_update chat_id={chat_id}: {e}", flush=True)
        await enviar_telegram(chat_id, "Erro interno. Tente novamente com /start")

async def _bot_loop_async():
    """Loop assincrono do bot — roda em thread propria para evitar conflito de event loop no Windows."""
    print("[bot] Bot do Telegram rodando...", flush=True)
    offset = None
    tmt = httpx.Timeout(connect=10, read=35, write=10, pool=5)
    async with httpx.AsyncClient(timeout=tmt) as c:
        while True:
            try:
                params = {"timeout": 30}
                if offset is not None:
                    params["offset"] = offset
                r = await c.get(f"{API}/getUpdates", params=params)
                for upd in r.json().get("result", []):
                    offset = upd["update_id"] + 1
                    txt = upd.get("message", {}).get("text", "")
                    print(f"[bot] recebido de chat_id={upd.get('message',{}).get('chat',{}).get('id')}: {txt!r}", flush=True)
                    await tratar_update(upd)
            except Exception as e:
                print(f"[bot] erro: {e}", flush=True)
                await asyncio.sleep(3)

def _bot_thread():
    """Thread dedicada ao bot com event loop proprio."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_bot_loop_async())
    except Exception as e:
        print(f"[bot] thread encerrada: {e}", flush=True)
    finally:
        loop.close()

# ----------------------------------------------------------------------------
# App
# ----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    if TOKEN:
        t = threading.Thread(target=_bot_thread, daemon=True)
        t.start()
    else:
        print("[bot] TELEGRAM_BOT_TOKEN nao definido — bot desativado.", flush=True)
    yield
    # daemon=True garante que a thread encerra junto com o processo

app = FastAPI(title="Correio Elegante Arraiá TI", lifespan=lifespan)

# ---- Tempo real (SSE): avisa o telão no instante em que chega um correio ----
_assinantes: set = set()

async def _broadcast(evento: dict):
    for q in list(_assinantes):
        try:
            q.put_nowait(evento)
        except Exception:
            _assinantes.discard(q)

@app.get("/api/stream")
async def stream():
    q: asyncio.Queue = asyncio.Queue()
    _assinantes.add(q)
    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            _assinantes.discard(q)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})

class CorreioIn(BaseModel):
    para: str
    mensagem: str
    de: str = ""
    anonimo: bool = True
    remetente_real: str = ""   # nome de quem envia (registro interno, não aparece pra ninguém)

@app.post("/api/correios")
async def criar_correio(c: CorreioIn, request: Request):
    para = c.para.strip()
    msg  = c.mensagem.strip()
    remetente = c.remetente_real.strip()
    if not para or not msg:
        raise HTTPException(400, "Preencha o destinatário e a mensagem.")
    if not remetente:
        raise HTTPException(400, "Identifique quem está enviando (registro interno).")

    bloqueado, termos = analisar(msg)
    de = "Anônimo 🎭" if c.anonimo else (c.de.strip() or "Anônimo 🎭")

    # registro de origem (privado, só aparece na moderação)
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else ""))
    ua = request.headers.get("user-agent", "")[:300]

    with Session(engine) as s:
        codigo = gerar_codigo()
        while s.scalars(select(Correio).where(Correio.codigo == codigo)).first():
            codigo = gerar_codigo()
        correio = Correio(codigo=codigo, para=para, mensagem=msg, de=de,
                          anonimo=c.anonimo, oculto=bloqueado,
                          remetente_real=remetente, ip=ip, user_agent=ua,
                          termos=", ".join(termos)[:300])
        s.add(correio); s.commit(); s.refresh(correio)

        link = f"{BASE_URL}/c/{codigo}"
        via_telegram = False
        if not bloqueado:
            u = achar_usuario(s, para)
            if u:
                via_telegram = await enviar_telegram(u.chat_id, texto_correio(para, msg, de, link))
                if via_telegram:
                    correio.via = "telegram"; correio.entregue = True; s.commit()
            # tempo real no telão
            await _broadcast({"tipo": "novo", "para": para, "codigo": codigo,
                              "via": correio.via})

        return {
            "codigo": codigo, "link": link,
            "via": correio.via, "telegram": via_telegram,
            "oculto": bloqueado,
            "aviso": "Mensagem retida para moderação (filtro)." if bloqueado else None,
        }

@app.get("/api/correios/{codigo}")
def obter_correio(codigo: str):
    with Session(engine) as s:
        c = s.scalars(select(Correio).where(Correio.codigo == codigo.upper())).first()
        if not c or c.oculto:
            raise HTTPException(404, "Correio não encontrado.")
        if not c.entregue:
            c.entregue = True; s.commit()
        return {"para": c.para, "mensagem": c.mensagem, "de": c.de, "anonimo": c.anonimo}

@app.get("/api/telao")
def telao_dados():
    """Dados públicos do telão — NÃO expõe o texto das mensagens."""
    with Session(engine) as s:
        cs = s.scalars(select(Correio).where(Correio.oculto == False)  # noqa: E712
                       .order_by(Correio.id.desc())).all()
        total = len(cs)
        entregues = sum(1 for c in cs if c.entregue)
        registrados = s.scalar(select(func.count()).select_from(Usuario)) or 0
        feed = [{"codigo": c.codigo, "para": c.para, "via": c.via,
                 "entregue": c.entregue} for c in cs[:25]]
        return {"total": total, "entregues": entregues,
                "registrados": registrados, "feed": feed}

@app.get("/api/info")
async def info():
    bot_username = ""
    if TOKEN:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{API}/getMe")
                bot_username = r.json().get("result", {}).get("username", "")
        except Exception:
            pass
    return {"bot_username": bot_username, "base_url": BASE_URL}

# ----- Moderação -----
def checa_admin(key: str):
    if key != ADMIN_KEY:
        raise HTTPException(403, "Chave de moderação inválida.")

@app.get("/api/admin/correios")
def admin_listar(key: str):
    checa_admin(key)
    with Session(engine) as s:
        cs = s.scalars(select(Correio).order_by(Correio.id.desc())).all()
        return [{"codigo": c.codigo, "para": c.para, "de": c.de,
                 "mensagem": c.mensagem, "via": c.via,
                 "entregue": c.entregue, "oculto": c.oculto,
                 "remetente_real": c.remetente_real, "ip": c.ip,
                 "termos": c.termos,
                 "quando": c.criado_em.strftime("%d/%m %H:%M") if c.criado_em else ""}
                for c in cs]

@app.post("/api/admin/ocultar/{codigo}")
def admin_ocultar(codigo: str, key: str, ocultar: bool = True):
    checa_admin(key)
    with Session(engine) as s:
        c = s.scalars(select(Correio).where(Correio.codigo == codigo.upper())).first()
        if not c:
            raise HTTPException(404, "Não encontrado.")
        c.oculto = ocultar; s.commit()
        return {"codigo": c.codigo, "oculto": c.oculto}

# ----- Páginas -----
def pagina(nome): return FileResponse(os.path.join(BASE_DIR, "static", nome))

@app.get("/")            # barraca (criar correio)
def p_barraca():   return pagina("barraca.html")
@app.get("/telao")       # telão da festa
def p_telao():     return pagina("telao.html")
@app.get("/moderacao")   # painel de moderação
def p_moderacao(): return pagina("moderacao.html")
@app.get("/ativar")       # QR de ativação do bot (tela cheia, imprimível)
def p_ativar():    return pagina("ativar.html")
@app.get("/c/{codigo}")  # envelope que a pessoa abre
def p_reveal(codigo: str): return pagina("reveal.html")
