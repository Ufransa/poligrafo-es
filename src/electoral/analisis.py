# src/electoral/analisis.py
"""Cálculos sin LLM: cambios de postura, lo hecho desde el Gobierno, finanzas."""
import json
from collections import defaultdict
from pathlib import Path


def postura(subtipo: str, voto: str) -> str | None:
    """'a_favor' o 'en_contra' de la iniciativa. La devolución invierte el voto; el texto alternativo no cuenta."""
    if subtipo == "texto_alternativo" or voto not in ("Sí", "No"):
        return None
    favorable = voto == "Sí"
    if subtipo == "devolucion":
        favorable = not favorable
    return "a_favor" if favorable else "en_contra"


def coherencia(conn) -> dict:
    filas = conn.execute("""SELECT v.id, v.clave_iniciativa, v.subtipo, vp.partido, vp.voto FROM votaciones v
                            JOIN votos_partido vp ON vp.votacion_id = v.id
                            WHERE v.excluida_tramite = 0 AND vp.dividido = 0 ORDER BY v.fecha""").fetchall()
    por = defaultdict(lambda: defaultdict(dict))
    for f in filas:
        p = postura(f["subtipo"], f["voto"])
        if p:
            por[f["partido"]][f["clave_iniciativa"]].setdefault(p, f["id"])
    salida = {}
    for partido, inis in por.items():
        pares = [{"clave_iniciativa": c, "a_favor": d["a_favor"], "en_contra": d["en_contra"]}
                 for c, d in inis.items() if "a_favor" in d and "en_contra" in d]
        if pares:
            salida[partido] = pares
    return salida


def gobierno(conn, partidos: list[dict]) -> dict:
    de_gobierno = {p["id"] for p in partidos if p.get("gobierno")}
    salida = defaultdict(list)
    for c in conn.execute("""SELECT c.*, v.url_boe FROM cruces c JOIN votaciones v ON v.id = c.votacion_id
                             WHERE c.nivel = 'veredicto' AND c.veredicto = 'cumple' AND v.resultado = 'aprobada'
                             AND (v.es_convalidacion = 1 OR v.tipo LIKE 'Dictámenes de Comisiones sobre iniciativas%'
                                  OR v.tipo LIKE 'Enmiendas del Senado%')"""):
        if c["partido"] in de_gobierno:
            salida[c["partido"]].append({"votacion_id": c["votacion_id"], "promesa_id": c["promesa_id"], "url_boe": c["url_boe"]})
    return dict(salida)


def finanzas(raiz: Path) -> dict:
    d = json.loads((raiz / "config" / "finanzas_2023.json").read_text(encoding="utf-8"))
    return {p: {**f, "url_informe": d["url_informe_campana"]} for p, f in d["partidos"].items()}
