# 💌 Correio Elegante Anônimo — Arraiá TI

Sistema completo: barraca pra criar correios, **bot do Telegram** que entrega no celular
de quem ativou, **link + QR** (envelope animado) pra quem não ativou, **telão** ao vivo e
**painel de moderação**. Backend em FastAPI, banco SQLite (troca pra Postgres em 1 linha).

---

## ⚠️ Leia isto primeiro (o ponto-chave)

O bot do Telegram **só consegue mandar mensagem pra quem já deu `/start` nele.** É regra
da plataforma, não tem como burlar. Por isso o sistema tem **dois caminhos** e usa o melhor
disponível pra cada pessoa:

- **Pessoa ativou o bot** → o correio chega no celular dela **na hora**.
- **Pessoa NÃO ativou** → a barraca/telão mostra **código + QR**; ela escaneia e abre o envelope.

👉 Na festa, deixe um **QR grandão "Ative seu correio"** na entrada e no telão (ele já aparece
sozinho na tela `/telao`). Quanto mais gente ativa, mais correios chegam automágicos.

---

## 1. Criar o bot (2 minutos)

1. No Telegram, fale com o **@BotFather**.
2. Mande `/newbot`, escolha um nome e um @username (ex.: `arraia_ti_bot`).
3. Ele te dá um **token** parecido com `123456:ABC-DEF...`. **Guarde.**

## 2. Rodar no seu PC

```bash
pip install -r requirements.txt

# Linux/Mac:
export TELEGRAM_BOT_TOKEN="cole-seu-token-aqui"
export BASE_URL="http://localhost:8000"
export ADMIN_KEY="uma-senha-sua"

# Windows (PowerShell):
$env:TELEGRAM_BOT_TOKEN="cole-seu-token-aqui"
$env:BASE_URL="http://localhost:8000"
$env:ADMIN_KEY="uma-senha-sua"

uvicorn main:app --reload
```

Abra:
- **http://localhost:8000/** → barraca (criar correio)
- **http://localhost:8000/telao** → telão da festa
- **http://localhost:8000/moderacao** → moderação (usa a `ADMIN_KEY`)

> Sem token o sistema roda igual — só o Telegram fica desligado e tudo vai por link/QR.

## 3. Fazer o QR funcionar nos celulares (importante!)

`localhost` só abre no seu PC. Pros celulares da galera abrirem o envelope, o site precisa
de um **endereço público**. Duas opções:

**A) Túnel rápido (recomendado pra festa num PC só) — Cloudflare Tunnel:**
```bash
# baixe o cloudflared (uma vez) e rode:
cloudflared tunnel --url http://localhost:8000
```
Ele te dá uma URL tipo `https://algo.trycloudflare.com`. Aí rode o servidor assim:
```bash
export BASE_URL="https://algo.trycloudflare.com"   # use a URL que ele deu
uvicorn main:app
```
Pronto: os QR já apontam pra esse endereço e funcionam em qualquer celular. O bot do
Telegram funciona normalmente (ele não precisa de endereço de entrada, ele "busca" sozinho).

**B) Hospedar online (sempre no ar) — Render (grátis):**
1. Suba a pasta num repositório no GitHub.
2. No Render: *New → Web Service* apontando pro repo.
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Em *Environment*, adicione `TELEGRAM_BOT_TOKEN`, `ADMIN_KEY` e
   `BASE_URL` (a URL que o Render te der, ex.: `https://correio-ti.onrender.com`).
4. (Opcional) Crie um Postgres grátis no Render e cole a `DATABASE_URL` nas variáveis —
   o código já entende Postgres automaticamente.

> No plano grátis do Render o serviço "dorme" parado. Na noite da festa, mantenha aberto/
> acessado de tempos em tempos, ou use a opção A (túnel) que não dorme.

## 4. Como usar na festa

1. Telão na TV/projetor mostrando `/telao` (QR de ativação + correios chegando).
2. Atendente da barraca usa `/` pra criar os correios.
3. Quem ativou o bot recebe no Telegram; os demais recebem o código/QR na mão.
4. Um colega fica de olho em `/moderacao` pra esconder qualquer mensagem ofensiva.

## Personalizar

- **Filtro (palavrão/bullying/racismo):** edite as listas em `filtro.py` (267 termos).
  Rode `python filtro.py` pra testar. Ele já pega leetspeak (`g0rd0`), espaçamento
  (`g o r d o`) e repetição (`gooordo`).
- **Quem enviou:** todo correio guarda nome interno + IP + horário (aparece só em `/moderacao`).
- **Cores/visual:** estão nos `:root { --variáveis }` no topo de cada arquivo em `static/`.
- **Selo do envelope ("TI"):** procure por `>TI<` em `static/reveal.html`.

## Arquivos

```
main.py                 backend + bot + API + tempo real (SSE)
filtro.py               moderação (267 termos + normalização anti-driblagem)
static/barraca.html     criar correio (QR + código + identificação de quem envia)
static/telao.html       telão ao vivo (reage em tempo real quando chega correio)
static/reveal.html      o envelope animado que a pessoa abre
static/moderacao.html   painel de moderação (mostra quem enviou + IP + termos)
requirements.txt
```

Boa festa! 🌽🔥💌
