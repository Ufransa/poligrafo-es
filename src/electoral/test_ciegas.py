# src/electoral/test_ciegas.py
"""Test a ciegas: propuestas de un programa, resumidas sin delatar al partido y con sus condiciones jurídicas.
Ver docs/superpowers/specs/2026-10-30-test-a-ciegas-design.md."""
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
