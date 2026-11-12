# src/electoral/verificar.py
"""Segunda pasada sobre los cruces que llegan a «veredicto»: se contrasta la promesa con el CONTENIDO de la
iniciativa (arranque de su texto en el BOCG), no solo con el título.

El juez (juez.py) solo ve el título. La revisión del 2026-11-11 encontró veredictos firmes donde la iniciativa
tocaba la misma ley que la promesa pero decidía otra cosa (PP y la LOREG: la proposición solo derogaba el artículo
222). Este paso no cambia el juez ni su huella: guarda su resultado aparte (tabla `verificaciones`) y `exportar`
lo usa para bajar a «Juzga tú» los «cumple» que no se sostienen. Los «incumple» no se tocan: lo que el modelo
ve en ellos va como nota en el aviso de revisión. Nunca sube un cruce ni cambia su sentido.
Sin texto del BOCG no decide: el cruce sigue como está.
"""
import hashlib
import io
import json
import os
import re
import time

import requests

from src.electoral import fuentes
from src.electoral.llm import PresupuestoAgotado
from src.electoral.votaciones import clave_iniciativa

MODELO = "deepseek/deepseek-v4-flash"
PASADAS = 2                 # solo cuenta lo que el modelo repite igual (misma regla que el juez)
RECORTE = 2600              # caracteres del arranque del texto
MAX_RUBRICAS = 30           # títulos de artículos y disposiciones: delatan el objeto real y las normas ómnibus
CABECERAS = {"User-Agent": "PoligrafoES/1.0 (herramienta personal)"}

SISTEMA = """Compruebas si una iniciativa parlamentaria española decide lo que promete un programa electoral.
Te doy el título de la iniciativa, el arranque de su texto oficial (BOCG) y los títulos de sus artículos, y una o
varias promesas. No sabes cómo votó nadie y no debes suponerlo. No opines sobre la iniciativa.

Para cada promesa responde:
- "objeto":
  "mismo" si el texto regula, aprueba, crea, modifica o suprime precisamente la medida o la norma de la promesa
  (aunque la promesa quiera lo contrario de lo que la iniciativa hace: «derogar la ley X» frente a una iniciativa
  que desarrolla la ley X es "mismo");
  "otro" si la iniciativa toca la misma ley, el mismo organismo o el mismo tema pero decide OTRA cosa
  (ejemplo: la promesa es impedir que los condenados por terrorismo sean elegibles y la iniciativa reforma la ley
  electoral solo para cambiar las papeletas de las elecciones europeas);
  "no_se" si con este fragmento no puedes afirmarlo. Ante la duda, "no_se": nunca "otro" por falta de datos.
- "mezcla": true SOLO si los títulos de los artículos muestran que la norma regula además asuntos importantes ajenos
  a la promesa, capaces por sí solos de explicar un voto. Disposiciones de trámite (entrada en vigor, títulos
  competenciales, habilitaciones) no cuentan. Ante la duda, false.
- "por_que": una frase corta, citando lo que dice el texto.

Responde SOLO con JSON: {"promesas": [{"id": int, "objeto": "mismo"|"otro"|"no_se", "mezcla": bool, "por_que": str}]}"""

ESQUEMA = """CREATE TABLE IF NOT EXISTS verificaciones (
    votacion_id TEXT, promesa_id INTEGER, partido TEXT,
    resultado TEXT,             -- 'sostiene' | 'no_sostiene' | 'nota' | 'sin_contenido'
    motivo TEXT, url TEXT, huella TEXT, fecha TEXT,
    PRIMARY KEY (votacion_id, promesa_id, partido)
);
CREATE TABLE IF NOT EXISTS bocg_textos (url TEXT PRIMARY KEY, texto TEXT);"""


# --- De qué iniciativa es la votación -------------------------------------------------

INICIO = re.compile(r"^(proposición|proyecto) de ley( orgánica)?\b")


def _resto(clave: str) -> str | None:
    """El título sin «proposición de ley [orgánica]» ni la palabra «orgánica» que el Congreso pospone al autor."""
    m = INICIO.match(clave)
    if not m:
        return None
    return re.sub(r"^orgánica ", "", clave[m.end():].strip(" ,"))


def enlace_bocg(v, indice: dict) -> str | None:
    """El BOCG de la iniciativa: el que ya resolvió `fuentes` o, si falta, el de la iniciativa de mismo título.

    En las tomas en consideración el expediente lleva el autor en medio («Proposición de Ley del Grupo X, de
    reforma de…») y los datos abiertos no («Proposición de Ley de reforma de…»): se casa por el final del título.
    Solo si casa con una única iniciativa; ante la duda, None.
    """
    if v["url_bocg"]:
        return v["url_bocg"]
    clave = clave_iniciativa(v["expediente"])
    if not INICIO.match(clave):
        return None
    candidatos = set()
    for k, url in indice.items():
        resto = _resto(k)
        if resto and len(resto) >= 30 and clave.endswith(resto) and k.split(" ")[0] == clave.split(" ")[0]:
            candidatos.add(url)
    return candidatos.pop() if len(candidatos) == 1 else None


# --- Qué dice la iniciativa -----------------------------------------------------------

RUBRICA = re.compile(r"((?:Artículo (?:\d+|único|primero|segundo|tercero|cuarto|quinto|sexto)|"
                     r"Disposición (?:adicional|final|transitoria|derogatoria) [\wáéíóú]+)\.[^.]{3,260}\.)")
TRAMITE = re.compile(r"entrada en vigor|título competencial|títulos competenciales|habilitación|desarrollo reglamentario|"
                     r"derogación normativa|salvaguardia del rango", re.I)


def recortar(texto: str) -> str:
    """El arranque de la exposición de motivos (o del texto, si no la hay) y los títulos de artículos y
    disposiciones. Poco texto a propósito: cada carácter se paga en cada cruce."""
    texto = " ".join(texto.split())
    m = re.search(r"exposición de motivos|preámbulo", texto, re.I)
    cuerpo = texto[m.start():] if m else texto
    rubricas = []
    for r in RUBRICA.findall(cuerpo):
        r = r.strip()
        if not TRAMITE.search(r) and r not in rubricas:
            rubricas.append(r[:260])
    salida = cuerpo[:RECORTE]
    if rubricas:
        salida += "\n\nTÍTULOS DE ARTÍCULOS Y DISPOSICIONES:\n" + "\n".join(f"- {r}" for r in rubricas[:MAX_RUBRICAS])
    return salida


def _descargar(url: str) -> str | None:
    falso = os.environ.get("ELECTORAL_BOCG_FALSO")
    if falso:
        return json.loads(open(falso, encoding="utf-8").read()).get(url)
    import pdfplumber
    try:
        r = requests.get(url, headers=CABECERAS, timeout=90)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            return None
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            return " ".join(" ".join((p.extract_text() or "").split()) for p in pdf.pages[:25])
    except Exception:                        # red o PDF ilegible: sin contenido, el cruce sigue como está
        return None
    finally:
        time.sleep(1.5)                      # el Congreso es un servicio público, no un CDN


def contenido(conn, url: str) -> str | None:
    """Texto recortado del BOCG, guardado para no volver a bajarlo."""
    url = url.split("#")[0]
    fila = conn.execute("SELECT texto FROM bocg_textos WHERE url = ?", (url,)).fetchone()
    if fila:
        return fila[0] or None
    bruto = _descargar(url)
    texto = recortar(bruto) if bruto and len(bruto) > 200 else None
    if bruto is not None:                    # un fallo de red no se guarda: se reintenta la próxima vez
        conn.execute("INSERT OR REPLACE INTO bocg_textos VALUES (?, ?)", (url, texto or ""))
        conn.commit()
    return texto


# --- La comprobación ------------------------------------------------------------------

def decidir(pasadas: list[dict | None], veredicto: str) -> tuple[str, str]:
    """(resultado, motivo). Cuenta solo lo que el modelo repite en todas las pasadas.

    Un «cumple» deja de sostenerse si la iniciativa decide otra cosa. Un «incumple» nunca se baja: ya solo es
    firme si una persona lo confirma, y en la medición del 2026-11-12 la regla de mezcla ocultó uno correcto
    (101-19). Lo que el modelo ve en un «incumple» queda como `nota` para el aviso de revisión."""
    if any(p is None for p in pasadas):
        return "sostiene", ""
    por_que = str(pasadas[0].get("por_que") or "")[:300]
    otro = all(p.get("objeto") == "otro" for p in pasadas)
    if veredicto == "cumple":
        return ("no_sostiene", "otro objeto: " + por_que) if otro else ("sostiene", por_que)
    if otro:
        return "nota", "El texto de la iniciativa parece decidir otra cosa: " + por_que
    if all(p.get("mezcla") is True for p in pasadas):
        return "nota", "La norma parece mezclar asuntos que pueden explicar el voto: " + por_que
    return "sostiene", por_que


def _huella(texto: str, promesas: list) -> str:
    base = json.dumps([hashlib.sha1(SISTEMA.encode("utf-8")).hexdigest(), MODELO, PASADAS, texto,
                       [(p["id"], p["texto"], p["cita"]) for p in promesas]], ensure_ascii=False)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _preguntar(llm, titulo: str, texto: str, promesas: list) -> dict | None:
    """{promesa_id: respuesta} de una pasada, o None si el modelo falla."""
    usuario = (f"VERIFICAR:\nINICIATIVA: {titulo}\n\nTEXTO OFICIAL (arranque):\n{texto}\n\nPROMESAS:\n"
               + "\n".join(f"[id={p['id']}] ({p['partido']}) {p['texto']} · Cita literal: «{p['cita'][:300]}»" for p in promesas))
    out = llm.json(MODELO, SISTEMA, usuario, max_tokens=120 + 110 * len(promesas))
    if out is None:
        return None
    salida = {}
    for r in out.get("promesas") or []:
        try:
            salida[int(r.get("id"))] = r
        except (TypeError, ValueError):
            continue
    return salida


def verificar(conn, llm, iniciativas: list[dict] | None = None) -> dict:
    """Comprueba los cruces a nivel «veredicto» que aún no lo están (o cuyo texto o promesa han cambiado).
    Una llamada por votación y pasada, con todas sus promesas. Reanudable; si se acaba el tope, para."""
    from src.electoral import exportar
    conn.executescript(ESQUEMA)
    firmes = [c for c in exportar._cruces(conn, set(), verificaciones={})
              if c["nivel"] == "veredicto" or c["pendiente_revision"]]
    hechas = {(r["votacion_id"], r["promesa_id"], r["partido"]): r["huella"] for r in conn.execute("SELECT * FROM verificaciones")}
    por_votacion: dict[str, list] = {}
    for c in firmes:
        por_votacion.setdefault(c["votacion_id"], []).append(c)
    indice = None
    cuenta = {"sostiene": 0, "no_sostiene": 0, "nota": 0, "sin_contenido": 0, "ya_hechas": 0, "pendientes": 0}
    for vid, cruces in por_votacion.items():
        v = conn.execute("SELECT * FROM votaciones WHERE id = ?", (vid,)).fetchone()
        url = v["url_bocg"]
        if not url and re.match(r"(?i)(proposición|proyecto) de ley", clave_iniciativa(v["expediente"])):
            if indice is None:               # los datos abiertos solo se bajan si hacen falta
                indice = fuentes.indice_iniciativas(iniciativas if iniciativas is not None else fuentes.cargar_iniciativas(None))
            url = enlace_bocg(v, indice)
        texto = contenido(conn, url) if url else None
        promesas = [dict(conn.execute("SELECT id, partido, texto, cita FROM promesas WHERE id = ?", (c["promesa_id"],)).fetchone())
                    for c in cruces]
        huella = _huella(texto or "", promesas)
        claves = [(c["votacion_id"], c["promesa_id"], c["partido"]) for c in cruces]
        if all(hechas.get(k) == huella for k in claves):
            cuenta["ya_hechas"] += len(claves)
            continue
        if not texto:
            resultados = {k: ("sin_contenido", "") for k in claves}
        else:
            try:
                pasadas = [_preguntar(llm, " ".join(v["expediente"].split())[:500], texto, promesas) for _ in range(PASADAS)]
            except PresupuestoAgotado:
                cuenta["pendientes"] += len(claves)
                break
            if any(p is None for p in pasadas):
                cuenta["pendientes"] += len(claves)      # el modelo falló: se reintenta en la próxima ejecución
                continue
            resultados = {(c["votacion_id"], c["promesa_id"], c["partido"]):
                          decidir([p.get(c["promesa_id"]) for p in pasadas], c["veredicto"]) for c in cruces}
        for k, (resultado, motivo) in resultados.items():
            conn.execute("INSERT OR REPLACE INTO verificaciones VALUES (?,?,?,?,?,?,?, datetime('now'))",
                         (*k, resultado, motivo, url, huella))
            cuenta[resultado] += 1
        conn.commit()
    return cuenta


def no_sostenidos(conn) -> set:
    """Cruces (votación, promesa, partido) que el contenido de la iniciativa no sostiene."""
    conn.executescript(ESQUEMA)
    return {(r[0], r[1], r[2]) for r in conn.execute(
        "SELECT votacion_id, promesa_id, partido FROM verificaciones WHERE resultado = 'no_sostiene'")}


def notas(conn) -> dict:
    """{(votación, promesa, partido): motivo} de los «incumple» en los que el texto de la iniciativa pide cautela."""
    conn.executescript(ESQUEMA)
    return {(r[0], r[1], r[2]): r[3] for r in conn.execute(
        "SELECT votacion_id, promesa_id, partido, motivo FROM verificaciones WHERE resultado = 'nota'")}
