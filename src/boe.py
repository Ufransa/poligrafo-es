# src/boe.py
import xml.etree.ElementTree as ET

import requests

BOE_API_BASE = "https://www.boe.es/datosabiertos/api/boe/sumario"
TIMEOUT = 15
HEADERS = {"Accept": "application/json", "User-Agent": "PoligrafoES/1.0"}


def fetch_boe_sumario(date_str):
    """date_str: 'YYYYMMDD'. Returns parsed JSON dict or None."""
    try:
        r = requests.get(f"{BOE_API_BASE}/{date_str}", headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _as_list(field):
    """Normalize a field that can be a dict (single item) or a list to always be a list."""
    if isinstance(field, dict):
        return [field]
    if isinstance(field, list):
        return field
    return []


def extract_boe_items(sumario_data, sections=("1", "2")):
    """
    Extract all items from specified sections.
    Returns list of {identificador, titulo, url_xml, departamento, fecha}.
    """
    try:
        fecha = sumario_data["data"]["sumario"]["metadatos"]["fecha_publicacion"]
        diario_list = _as_list(sumario_data["data"]["sumario"]["diario"])
    except (KeyError, TypeError):
        return []

    results = []
    for diario in diario_list:
        for seccion in _as_list(diario.get("seccion")):
            if seccion.get("codigo") not in sections:
                continue
            for dpto in _as_list(seccion.get("departamento", [])):
                dpto_nombre = dpto.get("nombre", "")
                for epigrafe in _as_list(dpto.get("epigrafe", [])):
                    for item in _as_list(epigrafe.get("item", [])):
                        results.append({
                            "identificador": item.get("identificador", ""),
                            "titulo": item.get("titulo", ""),
                            "url_xml": item.get("url_xml", ""),
                            "departamento": dpto_nombre,
                            "fecha": fecha,
                        })
    return results


def fetch_boe_entry(url_xml):
    """
    Fetch BOE entry XML.
    Returns {rango, texto_preview} or None on error.
    texto_preview is the first 1000 chars of <texto> content.
    """
    try:
        r = requests.get(url_xml, timeout=TIMEOUT)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        root = ET.fromstring(r.text)
        rango = (root.findtext(".//rango") or "").strip()
        texto = (root.findtext(".//texto") or "").strip()
        return {
            "rango": rango,
            "texto_preview": texto[:1000],
        }
    except ET.ParseError:
        return None
