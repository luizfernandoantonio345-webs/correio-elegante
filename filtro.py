"""
filtro.py — Moderação de conteúdo do Correio Elegante (Arraiá TI)

Objetivo: barrar palavrão, bullying, racismo, homofobia e capacitismo ANTES da
mensagem ser entregue. É uma camada de PROTEÇÃO (anti-abuso), não de censura aleatória.

Como funciona (3 defesas):
  1) Normalização — deixa minúsculo, tira acento, desfaz "leetspeak" (v1@d0 -> viado),
     colapsa letras repetidas (carraalho -> caralho) e remove pontuação. Isso pega
     a maioria das tentativas de driblar o filtro.
  2) Lista de termos — palavras exatas (curtas/ambíguas) e termos "contidos"
     (xingamentos distintos e frases coladas, ex.: "vaitomarnocu").
  3) Moderação humana — o que passar reto é pego no painel /moderacao, que mostra
     QUEM enviou (registro interno). Nenhum filtro é 100%; a combinação é que protege.

A função principal é `analisar(texto)` -> (bloqueado: bool, termos: list[str]).
"""
import re
import unicodedata

# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------
_LEET = str.maketrans({
    "0": "o", "1": "i", "2": "z", "3": "e", "4": "a", "5": "s", "6": "g",
    "7": "t", "8": "b", "9": "g", "@": "a", "$": "s", "|": "i", "!": "i",
    "(": "c", "+": "t",
})

def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))   # tira acentos
    t = t.translate(_LEET)                                       # desfaz leetspeak
    t = re.sub(r"[^a-z\s]", " ", t)                             # só letras e espaço
    t = re.sub(r"(.)\1{2,}", r"\1", t)                         # 3+ repetidas -> 1
    t = re.sub(r"\s+", " ", t).strip()
    return t

def _juntar_letras_soltas(norm: str) -> str:
    """Junta sequências do tipo 'v i a d o' em 'viado' (driblagem por espaços)."""
    return re.sub(r"\b(?:[a-z]\s){2,}[a-z]\b",
                  lambda m: m.group(0).replace(" ", ""), norm)

def _despacado(norm: str) -> str:
    return norm.replace(" ", "")

# ---------------------------------------------------------------------------
# Listas (PROTEÇÃO). Edite conforme a realidade da sua escola.
# EXATAS  = casadas por PALAVRA inteira (curtas/ambíguas, evitam falso positivo).
# CONTIDAS = casadas como TRECHO no texto sem espaços (xingamentos distintos + frases).
# ---------------------------------------------------------------------------

EXATAS = {
    # --- gerais curtos / ambíguos ---
    "cu", "cuz", "pqp", "krl", "vsf", "vtnc", "vtmnc", "fdp", "pnc", "tnc",
    "puta", "puto", "pau", "rola", "pinto", "saco", "tosco", "lixo", "verme",
    "burro", "burra", "besta", "jumento", "jumenta", "anta", "tapado", "tapada",
    "otario", "otaria", "babaca", "trouxa", "panaca", "mané", "mane", "joao",
    "feio", "feia", "feioso", "feiosa", "horrendo", "horrenda", "nojento", "nojenta",
    "gordo", "gorda", "gordao", "gordice", "baleia", "obeso", "obesa", "porcao",
    "magrelo", "magrela", "palito", "varapau", "nanico", "anao", "ana",
    "nerd", "cdf", "mocreia", "jacare", "orelhudo", "narigudo", "dentuco",
    "gay", "bicha", "viado", "veado", "boiola", "fresco", "fresca",
    "preto", "pretinho", "nego", "neguinho", "macaco", "macaca", "crioulo",
    "japa", "china", "baiano", "paraiba", "indio", "bugre",
    "manco", "aleijado", "retardado", "debil", "tonto", "lesado", "lerdo",
    "corno", "corna", "chifrudo", "vagaba", "piranha", "biscate", "galinha",
    "merda", "bosta", "porra", "cacete", "caceta", "foda", "fodase",
    "buceta", "xota", "ppk", "rabo", "bunda", "tetas", "peido", "peidao",
    "demente", "doente", "psicopata", "esquizo", "louco", "louca", "maluco",
}

CONTIDAS = {
    # --- palavrões / sexual (trechos distintos) ---
    "caralho", "carai", "porra", "cacete", "arrombado", "arrombada", "escroto",
    "escrota", "desgraca", "desgracado", "desgracada", "vagabundo", "vagabunda",
    "safado", "safada", "pilantra", "canalha", "cretino", "cretina", "imbecil",
    "idiota", "estupido", "estupida", "babaca", "otario", "merdao", "bostao",
    "filhadaputa", "filhodaputa", "filhaduma", "filhoduma", "fimdaputa",
    "vaitomarnocu", "tomanocu", "vaisefuder", "vaisefoder", "vaiseffuder",
    "vaitepicar", "vaitomarno", "fodase", "fodase", "fudido", "fudida", "fuder",
    "punheta", "punheteiro", "siririca", "boquete", "chupada", "chupavo",
    "buceta", "bucetao", "xereca", "xoxota", "xota", "perereca", "piroca",
    "rola", "caralhuda", "pauzudo", "gozada", "gozar", "trepar", "transar",
    "cuzao", "cuzinho", "arregaca", "putaria", "putinha", "puteiro",
    # --- bullying / aparência / peso ---
    "baleia", "obeso", "obesa", "gorducho", "gorducha", "bucha", "barril",
    "magrelo", "magrela", "anorexico", "anorexica", "varapau", "palito",
    "dentedecavalo", "dentuco", "narigudo", "orelhudo", "espinhento", "cravoso",
    "feioso", "mocreia", "jacare", "tristao", "fracassado", "fracassada",
    "burrice", "ignorante", "analfabeto", "analfabeta", "incompetente",
    "ninguemtecurte", "ninguemgosta", "sumissedomundo", "vaimorrer",
    "sematracao", "encalhada", "encalhado", "rejeitado", "rejeitada",
    # --- homofobia / lgbtfobia ---
    "viado", "veado", "viadinho", "bicha", "bichinha", "boiola", "baitola",
    "frutinha", "frutifera", "maricas", "mariquinha", "sapatao", "sapatona",
    "fanchona", "traveco", "trans", "paneleiro", "broxa",
    # --- racismo / xenofobia ---
    "macaco", "macaca", "macaquice", "crioulo", "crioula", "neguinho", "neguinha",
    "preteco", "tisnado", "urubu", "carvao", "jambo", "queimado", "denegrir",
    "japa", "olhopuxado", "pastel", "amarelo", "gringo",
    "cabecachata", "paraiba", "nordestinho", "bugre", "selvagem", "indiozinho",
    "favelado", "favelada", "marginalzinho",
    # --- capacitismo (deficiência) ---
    "retardado", "retardada", "mongoloide", "mongol", "debiloide", "aleijado",
    "aleijada", "manco", "capenga", "ceguinho", "ceguinha", "surdinho",
    "deficientemental", "down", "autista", "especial", "doentemental",
    # --- ameaças / violência ---
    "voutebater", "voutematar", "tematar", "tebater", "apanhar", "morre",
    "sematar", "tequebrar", "vouquebrar", "ameaca",
}


def analisar(texto: str):
    """Retorna (bloqueado, termos_encontrados)."""
    norm = _juntar_letras_soltas(_normalizar(texto))
    tokens = set(norm.split())
    junto = _despacado(norm)

    achados = []
    for w in EXATAS:
        if w in tokens:
            achados.append(w)
    for w in CONTIDAS:
        if w and w in junto and w not in achados:
            achados.append(w)

    return (len(achados) > 0, sorted(set(achados)))


def tem_ofensa(texto: str) -> bool:
    return analisar(texto)[0]


if __name__ == "__main__":
    testes = [
        "voce ilumina o arraia",          # ok
        "seu idiota",                     # bloqueia
        "v i a d o",                      # driblagem por espaço
        "vc eh um 1diot4",                # leetspeak
        "caaaralho que festa",            # repetição
        "vai tomar no cu",                # frase
    ]
    for t in testes:
        b, termos = analisar(t)
        print(f"{'BLOQUEADO' if b else 'ok       '} | {t!r:35} -> {termos}")
    print("Total de termos na lista:", len(EXATAS | CONTIDAS))
