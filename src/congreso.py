import re
import zipfile
import io
import xml.etree.ElementTree as ET
from collections import Counter

import requests

BASE_URL = "https://www.congreso.es"
OPENDATA_URL = f"{BASE_URL}/es/opendata/votaciones"
TIMEOUT = 20
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def aggregate_group_votes(raw_votes):
    """
    raw_votes: list of {'grupo': str, 'voto': str}
    Returns: {grupo_code: {'voto': str, 'total': int, 'divided': bool}}
    """
    groups = {}
    for rv in raw_votes:
        g = rv["grupo"]
        if not g:
            continue
        if g not in groups:
            groups[g] = Counter()
        groups[g][rv["voto"]] += 1

    result = {}
    for g, counter in groups.items():
        total = sum(counter.values())
        dominant, dominant_count = counter.most_common(1)[0]
        divided = (total - dominant_count) / total > 0.10
        result[g] = {
            "voto": dominant,
            "total": total,
            "divided": divided,
        }
    return result


def parse_vote_xml(xml_str):
    """Parse a VOT_*.xml string. Returns a dict with vote metadata + aggregated group votes."""
    root = ET.fromstring(xml_str)
    info = root.find("Informacion")
    totals = root.find("Totales")

    raw_votes = [
        {"grupo": v.findtext("Grupo", "").strip(), "voto": v.findtext("Voto", "").strip()}
        for v in root.findall(".//Votacion")
    ]

    return {
        "sesion": int(info.findtext("Sesion", 0)),
        "numero_votacion": int(info.findtext("NumeroVotacion", 0)),
        "fecha": info.findtext("Fecha", "").strip(),
        "titulo": info.findtext("Titulo", "").strip(),
        "texto_expediente": info.findtext("TextoExpediente", "").strip(),
        "a_favor": int(totals.findtext("AFavor", 0)),
        "en_contra": int(totals.findtext("EnContra", 0)),
        "abstenciones": int(totals.findtext("Abstenciones", 0)),
        "group_votes": aggregate_group_votes(raw_votes),
    }


def discover_latest_session(html):
    """
    Scrape the Congreso HTML page and return (session_number, zip_url, session_date).
    Returns (None, None, None) if nothing found.
    """
    pattern = r'(/webpublica/opendata/votaciones/Leg\d+/Sesion(\d+)/(\d{8})/VOT_[^"\']+\.zip)'
    matches = re.findall(pattern, html)
    if not matches:
        return None, None, None

    matches.sort(key=lambda m: int(m[1]), reverse=True)
    path, session_str, date_str = matches[0]
    return int(session_str), BASE_URL + path, date_str


def fetch_opendata_html():
    r = requests.get(OPENDATA_URL, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def download_session_zip(zip_url):
    """
    Download a session ZIP. Returns list of (filename, xml_content) for all .xml files inside.
    """
    r = requests.get(zip_url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    results = []
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".xml"):
                raw = zf.read(name)
                try:
                    content = raw.decode("utf-8")
                except UnicodeDecodeError:
                    content = raw.decode("iso-8859-1", errors="replace")
                results.append((name, content))
    return results
