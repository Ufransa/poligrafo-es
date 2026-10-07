# src/electoral/fuentes.py
"""Enlaces a las fuentes oficiales de cada votación."""
import difflib
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

from src.electoral.votaciones import clave_iniciativa

CABECERAS = {"User-Agent": "PoligrafoES/1.0"}
# Verificado el 2026-10-07: la API de legislación consolidada del BOE busca por título y devuelve el
# identificador (p. ej. "Real Decreto-ley 3/2026" → BOE-A-2026-2548).
API_BOE = "https://www.boe.es/datosabiertos/api/legislacion-consolidada?query="


def cargar_iniciativas(origen: str | None) -> list[dict]:
    if origen:
        return json.loads(Path(origen).read_text(encoding="utf-8"))
    html = requests.get("https://www.congreso.es/es/opendata/iniciativas", headers=CABECERAS, timeout=30).text
    todas = []
    for path in sorted(set(re.findall(r"/webpublica/opendata/iniciativas/[A-Za-z]+__\d+\.json", html))):
        todas += requests.get("https://www.congreso.es" + path, headers=CABECERAS, timeout=60).json()
    return todas


def url_bocg(expediente: str, iniciativas: list[dict]) -> str | None:
    clave = clave_iniciativa(expediente)
    objetos = [clave_iniciativa(x.get("OBJETO", "")) for x in iniciativas]
    m = difflib.get_close_matches(clave[:250], [o[:250] for o in objetos], n=1, cutoff=0.75)
    if not m:
        return None
    x = iniciativas[[o[:250] for o in objetos].index(m[0])]
    enlaces = (x.get("ENLACESBOCG") or "").split()
    return enlaces[0].split("#")[0] if enlaces else None


def es_final_aprobada(v) -> bool:
    """Solo lo que acaba en el BOE: convalidaciones de decretos-ley y leyes aprobadas en su votación final."""
    if v["subtipo"] != "normal":
        return False
    final = v["es_convalidacion"] or v["tipo"].startswith(("Dictámenes de Comisiones sobre iniciativas", "Enmiendas del Senado"))
    return bool(final) and v["resultado"] == "aprobada"


def url_boe(v, boe: dict) -> str | None:
    if not es_final_aprobada(v):
        return None
    ident = boe.get(v["clave_iniciativa"])
    return f"https://www.boe.es/buscar/act.php?id={ident}" if ident else None


def resolver_boe(clave: str) -> str | None:
    """Identificador BOE de un decreto-ley o una ley a partir de su clave de iniciativa. None si no aparece."""
    m = re.match(r"real decreto-ley (\d+/\d{4})", clave)
    if m:
        consulta, rangos = f'titulo:"Real Decreto-ley {m.group(1)}"', ("Real Decreto-ley",)
    else:
        resto = re.sub(r"^(proyecto|proposición) de ley( orgánica)?\s*", "", clave).strip(" .")
        if len(resto) < 15:
            return None
        consulta, rangos = f'titulo:"{resto}"', ("Ley", "Ley Orgánica")
    q = json.dumps({"query": {"query_string": {"query": consulta}}}, ensure_ascii=False)
    try:
        r = requests.get(API_BOE + quote(q), headers={**CABECERAS, "Accept": "application/json"}, timeout=30)
        datos = r.json().get("data") or []
    except (requests.RequestException, ValueError):
        return None
    finally:
        time.sleep(0.5)
    for d in datos:
        if (d.get("rango") or {}).get("texto") in rangos:
            return d.get("identificador")
    return None
