# src/electoral/test_ciegas.py
"""Test a ciegas: propuestas de un programa, resumidas sin delatar al partido y con sus condiciones jurídicas.
Ver docs/superpowers/specs/2026-10-30-test-a-ciegas-design.md."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.electoral.llm import PresupuestoAgotado

MODELO = "deepseek/deepseek-v4-flash"
ADIVINO = "google/gemini-2.5-flash-lite"
MAX_POR_PARTIDO_TEMA = 3
MAX_REESCRITURAS = 2
TEMAS_LANZAMIENTO = ["Economía e industria", "Vivienda", "Sanidad", "Fiscalidad", "Empleo y trabajo", "Pensiones"]

SISTEMA_SELECCION = f"""Eliges propuestas de un programa electoral español para un test donde la gente las vota sin saber
de qué partido son. De la lista, elige como mucho {MAX_POR_PARTIDO_TEMA}: las más CONCRETAS (qué se hace, a quién, cuánto)
y de MÁS ALCANCE (a cuánta gente afecta o cuánto cambia). Si hay {MAX_POR_PARTIDO_TEMA} o menos, elígelas todas.
No valores si son buenas o malas.

Responde SOLO con JSON: {{"ids": [int, ...]}}"""


def seleccionar(conn, llm, anio: int, temas: list[str]) -> int:
    """Una llamada por (partido, tema) aún no hecho. Reanudable: el par se marca cuando su selección está guardada."""
    hechos = {(r["partido"], r["tema"]) for r in conn.execute("SELECT partido, tema FROM test_hechos WHERE anio = ?", (anio,))}
    grupos: dict[tuple, list] = {}
    vistos = set()
    for p in conn.execute(f"SELECT id, partido, tema, texto FROM promesas WHERE anio = ? AND procedimental = 0 "
                          f"AND tema IN ({','.join('?' * len(temas))}) ORDER BY id", (anio, *temas)):
        if (p["partido"], p["tema"]) in hechos or (p["partido"], p["texto"]) in vistos:
            continue
        vistos.add((p["partido"], p["texto"]))
        grupos.setdefault((p["partido"], p["tema"]), []).append(p)
    n = 0
    for (partido, tema), promesas in grupos.items():
        lista = "\n".join(f"[id={p['id']}] {p['texto']}" for p in promesas)
        try:
            out = llm.json(MODELO, SISTEMA_SELECCION, f"Tema: {tema}\n\nSELECCIONAR:\n{lista}", max_tokens=300)
        except PresupuestoAgotado:
            break
        if out is None:
            continue
        validos = {p["id"] for p in promesas}
        ids = [int(i) for i in out.get("ids", []) if str(i).isdigit()]
        elegidos = [i for i in dict.fromkeys(ids) if i in validos][:MAX_POR_PARTIDO_TEMA]
        for i in elegidos:
            conn.execute("INSERT OR IGNORE INTO test_propuestas (promesa_id, anio, partido, tema) VALUES (?,?,?,?)",
                         (i, anio, partido, tema))
        conn.execute("INSERT INTO test_hechos VALUES (?,?,?)", (anio, partido, tema))
        conn.commit()
        n += len(elegidos)
    return n


SISTEMA_RESUMEN = """Resumes una propuesta de un programa electoral español para un test donde la gente la vota SIN SABER
de qué partido es. Tu resumen es lo único que verán antes de votar.

Escribe 2-4 frases en castellano con lo CRÍTICO: qué se hace, a quién afecta, cuánto (si el programa lo dice) y cómo
se paga (si el programa lo dice). Nada de titulares vacíos: «bajar impuestos» no vale; «bajar el IRPF a las rentas de
menos de 30.000 euros» sí, si el texto lo dice.

Reglas de neutralidad (obligatorias):
- Ni el nombre del partido ni el de sus líderes, ni ninguna pista de quién gobierna o gobernó.
- Nada de primera persona («haremos», «nuestro»): describe la medida en impersonal.
- Nada de balance de gestión («como ya hicimos», «seguiremos»).
- Nada de léxico identitario o de marca («Euskal Herria», «la Nación española», «justicia climática», «Països
  Catalans»). Si el territorio o la identidad es el objeto mismo de la propuesta, usa el término jurídico neutro
  (p. ej. «la Comunidad Autónoma del País Vasco», «Cataluña»).
- Ninguna cifra, plazo o dato que no esté en el texto del programa. Si el programa no concreta, no inventes.
- No valores la propuesta.

Además:
- "concreta": false si el programa no dice qué se hace en concreto (solo intención general).
- "materias": claves de la lista de MATERIAS que describen lo que haría falta jurídicamente para aprobarla.
  Varias si aplica. Ninguna si no encaja ninguna.
- "coste": true si implica gasto público o pérdida de ingresos.

Responde SOLO con JSON: {"resumen": str, "concreta": bool, "materias": [str], "coste": bool}"""


def materias_validas(raiz: Path) -> dict:
    """Clave -> descripción para el modelo, de config/condiciones.json."""
    tabla = json.loads((raiz / "config" / "condiciones.json").read_text(encoding="utf-8"))
    return {k: v["descripcion_para_el_modelo"] for k, v in tabla["materias"].items()}


def _resumir_una(conn, llm, fila, materias: dict, pista: str | None = None) -> bool:
    lista = "\n".join(f"- {k}: {d}" for k, d in materias.items())
    usuario = (f"MATERIAS:\n{lista}\n\nTema: {fila['tema']}\n\nRESUMIR:\nPROMESA: {fila['texto']}\n"
               f"CITA LITERAL: {fila['cita']}\n\nTEXTO DEL PROGRAMA DE DONDE SALE:\n{fila['bloque']}")
    if pista:
        usuario += f"\n\nREESCRIBE: {pista}\nResumen anterior: {fila['resumen']}"
    out = llm.json(MODELO, SISTEMA_RESUMEN, usuario, max_tokens=600)
    if not out or not str(out.get("resumen", "")).strip():
        return False
    elegidas = [m for m in dict.fromkeys(out.get("materias") or []) if m in materias]
    conn.execute("UPDATE test_propuestas SET resumen = ?, concreta = ?, materias = ?, coste = ? WHERE promesa_id = ?",
                 (out["resumen"].strip(), int(out.get("concreta") is not False), json.dumps(elegidas),
                  int(bool(out.get("coste"))), fila["promesa_id"]))
    return True


FILAS = """SELECT t.*, p.texto, p.cita, b.texto AS bloque FROM test_propuestas t
           JOIN promesas p ON p.id = t.promesa_id JOIN bloques b ON b.id = p.bloque_id WHERE t.anio = ?"""


def resumir(conn, llm, anio: int, raiz: Path) -> int:
    """Resume las propuestas sin resumen. Reanudable."""
    materias = materias_validas(raiz)
    pendientes = conn.execute(FILAS + " AND t.resumen IS NULL", (anio,)).fetchall()

    def una(f):
        try:
            return _resumir_una(conn, llm, f, materias)
        except PresupuestoAgotado:
            return False

    with ThreadPoolExecutor(8) as ex:
        n = sum(ex.map(una, pendientes))
    conn.commit()
    return n
