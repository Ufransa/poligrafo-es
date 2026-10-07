# src/electoral/exportar.py
import json

import jsonschema
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.electoral import analisis

VERSION_CONTRATO = "1.0.0"


def _votaciones(conn) -> list[dict]:
    salida = []
    for v in conn.execute("SELECT * FROM votaciones ORDER BY fecha, sesion, numero"):
        votos = {r["partido"]: {"voto": r["voto"], "dividido": bool(r["dividido"])}
                 for r in conn.execute("SELECT * FROM votos_partido WHERE votacion_id = ?", (v["id"],))}
        salida.append({
            "id": v["id"], "fecha": v["fecha"], "sesion": v["sesion"], "numero": v["numero"],
            "tipo": v["tipo"], "subtipo": v["subtipo"], "expediente": v["expediente"],
            "que_se_vota": v["texto_subgrupo"], "clave_iniciativa": v["clave_iniciativa"],
            "resultado": v["resultado"], "a_favor": v["a_favor"], "en_contra": v["en_contra"],
            "abstenciones": v["abstenciones"], "excluida_tramite": bool(v["excluida_tramite"]),
            "votos": votos, "url_xml": v["url_xml"], "url_sesion": v["url_sesion"],
            "url_bocg": v["url_bocg"], "url_boe": v["url_boe"],
        })
    return salida


def _promesas(conn) -> list[dict]:
    salida = []
    for p in conn.execute("""SELECT p.*, b.url_programa FROM promesas p JOIN bloques b ON b.id = p.bloque_id
                             WHERE p.procedimental = 0 ORDER BY p.partido, p.anio, p.pagina, p.id"""):
        salida.append({"id": p["id"], "partido": p["partido"], "anio": p["anio"], "texto": p["texto"],
                       "cita": p["cita"], "pagina": p["pagina"], "tema": p["tema"],
                       "url_programa_pagina": f"{p['url_programa']}#page={p['pagina']}"})
    return salida


def _temas(promesas: list[dict]) -> dict:
    cuenta = defaultdict(Counter)
    for p in promesas:
        cuenta[(p["partido"], str(p["anio"]))][p["tema"]] += 1
    salida = defaultdict(dict)
    for (partido, anio), c in cuenta.items():
        total = sum(c.values())
        salida[partido][anio] = {t: round(100 * n / total, 1) for t, n in c.most_common()}
    return dict(salida)


def _cruces(conn) -> list[dict]:
    salida = []
    for c in conn.execute("""SELECT c.*, vp.voto, vp.dividido FROM cruces c
                             JOIN votos_partido vp ON vp.votacion_id = c.votacion_id AND vp.partido = c.partido
                             ORDER BY c.votacion_id, c.partido"""):
        salida.append({"votacion_id": c["votacion_id"], "promesa_id": c["promesa_id"], "partido": c["partido"],
                       "voto": c["voto"], "dividido": bool(c["dividido"]), "nivel": c["nivel"],
                       "veredicto": c["veredicto"], "jueces": json.loads(c["jueces"])})
    return salida


def construir(conn, raiz: Path) -> dict:
    partidos = json.loads((raiz / "config" / "partidos_electoral.json").read_text(encoding="utf-8"))
    votaciones = _votaciones(conn)
    promesas = _promesas(conn)
    cruces = _cruces(conn)
    return {
        "meta": {
            "version_contrato": VERSION_CONTRATO,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "periodo": {"desde": "2023-08-17", "hasta": max((v["fecha"] for v in votaciones), default=None)},
            "recuentos": {"votaciones": len(votaciones), "promesas": len(promesas),
                          "veredictos": sum(c["nivel"] == "veredicto" for c in cruces)},
        },
        "partidos": partidos,
        "votaciones": votaciones,
        "promesas": promesas,
        "temas": _temas(promesas),
        "cruces": cruces,
        "coherencia": analisis.coherencia(conn),
        "gobierno": analisis.gobierno(conn, partidos),
        "finanzas": analisis.finanzas(raiz),
    }


ESQUEMA = Path(__file__).resolve().parents[2] / "schema" / "datos.schema.json"


def escribir(datos: dict, salida: Path) -> None:
    """Valida contra el contrato antes de escribir: un datos.json inválido nunca llega a la web."""
    jsonschema.validate(datos, json.loads(ESQUEMA.read_text(encoding="utf-8")))
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
