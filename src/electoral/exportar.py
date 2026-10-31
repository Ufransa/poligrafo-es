# src/electoral/exportar.py
import json
import os
import sys

import jsonschema
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.electoral import analisis, mezclas

VERSION_CONTRATO = "1.3.0"


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
            "mezcla": mezclas.nota(conn, v),
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


def _cruces(conn, confirmados: set) -> list[dict]:
    """El nivel se recalcula aquí con el voto y el «dividido» actuales: corregir los datos de votos no deja
    veredictos obsoletos."""
    from src.electoral import juez
    salida = []
    for c in conn.execute("""SELECT c.*, vp.voto, vp.dividido, v.subtipo, v.tipo, v.expediente FROM cruces c
                             JOIN votos_partido vp ON vp.votacion_id = c.votacion_id AND vp.partido = c.partido
                             JOIN votaciones v ON v.id = c.votacion_id AND v.excluida_tramite = 0
                             ORDER BY c.votacion_id, c.partido"""):
        jueces = json.loads(c["jueces"])
        if any(r and "postura" not in r for r in jueces.values()):
            continue                           # juicio del modelo antiguo (veredicto directo): se rehace al juzgar
        res = juez.nivel({m: ((r["postura"], r["fuerza"]) if r else None) for m, r in jueces.items()},
                         bool(c["dividido"]), analisis.postura(c["subtipo"], c["voto"]))
        if not res:
            continue
        if res[0] == "veredicto" and mezclas.enmienda_suelta_del_senado(c["tipo"], c["expediente"]):
            res = ("juzga_tu", res[1])         # por una enmienda suelta se cuelan asuntos ajenos a la ley
        clave = (c["votacion_id"], c["promesa_id"], c["partido"], res[1])
        revisado = clave in confirmados
        # Un incumple solo se afirma revisado a mano: el juez ve el titulo, no el contenido de la iniciativa.
        pendiente = res == ("veredicto", "incumple") and not revisado
        if pendiente:
            res = ("juzga_tu", "incumple")
        salida.append({"votacion_id": c["votacion_id"], "promesa_id": c["promesa_id"], "partido": c["partido"],
                       "voto": c["voto"], "dividido": bool(c["dividido"]), "nivel": res[0],
                       "veredicto": res[1], "revisado_a_mano": revisado and res[0] == "veredicto", "pendiente_revision": pendiente,
                       "jueces": jueces})
    return salida


def _confirmados(ruta: Path) -> set:
    """Cruces que una persona ha revisado y confirmado: config/revision_manual.json."""
    if not ruta.exists():
        return set()
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return {(x["votacion_id"], x["promesa_id"], x["partido"], x["veredicto"]) for x in datos["confirmados"]}


def _test(conn, raiz: Path, ruta: Path, anio: int, partidos: list, votaciones: list, cruces: list) -> list[dict]:
    """Propuestas del test a ciegas aprobadas por Fran (config/test_ciegas.json), con sus condiciones y, si Fran
    confirmó el cruce, el veredicto firme más reciente de esa promesa en 2023."""
    from src.electoral import condiciones
    if not ruta.exists():
        return []
    aprobadas = json.loads(ruta.read_text(encoding="utf-8")).get(str(anio), [])
    tabla = condiciones.cargar(raiz)
    nombres = {p["id"]: p["nombre"] for p in partidos}
    vots = {v["id"]: v for v in votaciones}
    salida = []
    for a in aprobadas:
        p = conn.execute("SELECT p.*, b.url_programa FROM promesas p JOIN bloques b ON b.id = p.bloque_id WHERE p.id = ?",
                         (a["promesa_id"],)).fetchone()
        if p is None:
            print(f"aviso: la propuesta aprobada {a['promesa_id']} ya no está en la base; no se publica", file=sys.stderr)
            continue
        if p["partido"] not in nombres:
            # ValueError y no SystemExit: la noche lo captura y lo deja en la salud que vigila ARGUS.
            raise ValueError(f"El partido {p['partido']} no está en config/partidos_electoral.json: añádelo antes de publicar")
        firmes = sorted((c for c in cruces if c["promesa_id"] == a.get("promesa_2023_id") and c["nivel"] == "veredicto"),
                        key=lambda c: vots[c["votacion_id"]]["fecha"])
        cruce = None
        if firmes:
            v = vots[firmes[-1]["votacion_id"]]
            cruce = {"veredicto": firmes[-1]["veredicto"], "votacion_id": v["id"], "expediente": v["expediente"],
                     "fecha": v["fecha"], "url_sesion": v["url_sesion"]}
        cond = condiciones.resolver(a["materias"], a["coste"], tabla)
        salida.append({"id": p["id"], "tema": p["tema"], "resumen": a["resumen"], "concreta": a["concreta"],
                       "condiciones": cond["condiciones"], "inviable": cond["inviable"],
                       "partido": p["partido"], "partido_nombre": nombres[p["partido"]], "cita": p["cita"],
                       "pagina": p["pagina"], "url_programa_pagina": f"{p['url_programa']}#page={p['pagina']}",
                       "cruce_2023": cruce})
    return salida


def construir(conn, raiz: Path, revision: Path | None = None, test_ciegas: Path | None = None,
              test_anio: int = 2026) -> dict:
    partidos = json.loads((raiz / "config" / "partidos_electoral.json").read_text(encoding="utf-8"))
    votaciones = _votaciones(conn)
    promesas = _promesas(conn)
    cruces = _cruces(conn, _confirmados(revision or raiz / "config" / "revision_manual.json"))
    test_ciegas = test_ciegas or Path(os.environ.get("ELECTORAL_TEST_CIEGAS") or raiz / "config" / "test_ciegas.json")
    test = _test(conn, raiz, test_ciegas, test_anio, partidos, votaciones, cruces)
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
        "test": test,
    }


ESQUEMA = Path(__file__).resolve().parents[2] / "schema" / "datos.schema.json"


def escribir(datos: dict, salida: Path) -> None:
    """Valida contra el contrato antes de escribir: un datos.json inválido nunca llega a la web."""
    jsonschema.validate(datos, json.loads(ESQUEMA.read_text(encoding="utf-8")))
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
