#!/usr/bin/env python3
"""
data_spike_v2.py — PolígrafoES
Resuelve incógnitas pendientes del spike v1:
  1. PP y PSOE PDFs — URLs alternativas
  2. BOE url_xml — verificar endpoint real
  3. Congreso — scraping HTML para descubrir sesiones
Output: spike_v2_results.json
"""

import requests
import json
import re
import tempfile
import os

TIMEOUT = 20
UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_BOT     = "Mozilla/5.0 (compatible; PoligrafoES/spike)"
results = {}

def get(url, ua=UA_BOT, accept=None, referer=None):
    h = {"User-Agent": ua}
    if accept:
        h["Accept"] = accept
    if referer:
        h["Referer"] = referer
    return requests.get(url, headers=h, timeout=TIMEOUT, allow_redirects=True)

def try_pdf(url, ua=UA_BOT, referer=None):
    """Returns dict with download status, size, and whether it's a real PDF."""
    try:
        r = requests.get(url, headers={"User-Agent": ua, **({"Referer": referer} if referer else {})},
                         timeout=30, allow_redirects=True)
        is_pdf = r.content[:4] == b'%PDF'
        return {
            "status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "is_pdf": is_pdf,
            "size_kb": len(r.content) // 1024,
            "body_preview": r.text[:200] if not is_pdf else None
        }
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────────
# 1. PDFs — PP: alternativas a la URL /sites/default/files/ (404)
# ─────────────────────────────────────────────────────────────
PP_CANDIDATES = {
    "pp_storage":   "https://www.pp.es/storage/2023/07/programa_electoral_pp_23j_feijoo_2023.pdf",
    "pp_newtral":   "https://www.newtral.es/wp-content/uploads/2025/07/programa_electoral_pp_23j_feijoo_2023.pdf",
    "pp_elespanol": "https://s2.elespanol.com/2025/09/29/politica/programa_electoral_pp_23j_feijoo_2023.pdf",
    "pp_ppvalladolid": "https://ppvalladolid.es/wp-content/uploads/2023/07/programa_electoral_pp_23j_feijoo_2023.pdf",
}

pp_results = {}
for key, url in PP_CANDIDATES.items():
    pp_results[key] = {"url": url, **try_pdf(url, ua=UA_BROWSER)}

results["pp_pdf_candidates"] = pp_results

# ─────────────────────────────────────────────────────────────
# 2. PDFs — PSOE: psoe.es devuelve HTML, probar alternativas
# ─────────────────────────────────────────────────────────────
PSOE_CANDIDATES = {
    # Mismo URL pero con UA de navegador real y Referer
    "psoe_main_browserua": {
        "url": "https://www.psoe.es/media-content/2023/07/PROGRAMA_ELECTORAL-GENERALES-2023.pdf",
        "ua": UA_BROWSER,
        "referer": "https://www.psoe.es/transparencia/informacion-politica-organizativa/programa/"
    },
    # CDN alternativo (Contentful)
    "psoe_ctfassets": {
        "url": "https://assets.ctfassets.net/obkb3v0fkpml/7J6mGGOJSsTunmNaVUbYW4/ec29ffc51bf60e2ed4bf1ffc06ce46c9/Programa_electoral_PSOE_2023.pdf",
        "ua": UA_BROWSER,
        "referer": None
    },
    # Newtral (mismos que hospedan SUMAR)
    "psoe_newtral": {
        "url": "https://www.newtral.es/wp-content/uploads/2023/07/Programa_electoral_PSOE_23j_2023.pdf",
        "ua": UA_BROWSER,
        "referer": None
    },
}

psoe_results = {}
for key, cfg in PSOE_CANDIDATES.items():
    psoe_results[key] = {"url": cfg["url"], **try_pdf(cfg["url"], ua=cfg["ua"], referer=cfg.get("referer"))}

results["psoe_pdf_candidates"] = psoe_results

# ─────────────────────────────────────────────────────────────
# 3. BOE — verificar url_xml del sumario (endpoint real)
# La URL viene incluida en cada item del sumario.
# Probamos con un ID conocido del spike v1 (BOE de hoy).
# ─────────────────────────────────────────────────────────────
BOE_XML_URL = "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2026-10511"
try:
    r = get(BOE_XML_URL)
    results["boe_entry_xml"] = {
        "url": BOE_XML_URL,
        "status": r.status_code,
        "content_type": r.headers.get("content-type"),
        "body_preview": r.text[:600] if r.status_code == 200 else None
    }
except Exception as e:
    results["boe_entry_xml"] = {"error": str(e)}

# ─────────────────────────────────────────────────────────────
# 4. Congreso — scraping HTML /es/opendata/votaciones
# Objetivo: descubrir cómo están listadas las sesiones
# ─────────────────────────────────────────────────────────────
CONGRESO_OD_URL = "https://www.congreso.es/es/opendata/votaciones"
try:
    r = get(CONGRESO_OD_URL, ua=UA_BROWSER)
    html = r.text

    # Extraer todos los hrefs que apunten a /webpublica/opendata/votaciones/
    session_links = re.findall(
        r'href=["\']([^"\']*webpublica/opendata/votaciones[^"\']*)["\']', html
    )
    # También buscar links a CSV/ZIP bulk
    bulk_links = re.findall(
        r'href=["\']([^"\']*\.(csv|zip|json|xml)[^"\']*)["\']', html, re.IGNORECASE
    )
    # Cualquier patrón SesionNNN
    sesion_refs = re.findall(r'Sesion\d+', html)

    results["congreso_html_discovery"] = {
        "status": r.status_code,
        "html_size_kb": len(html) // 1024,
        "session_links": list(set(session_links))[:20],
        "bulk_links": bulk_links[:20],
        "sesion_refs_in_html": list(set(sesion_refs))[:20],
        "html_snippet": html[:1500]  # primeros 1500 chars para inspección manual
    }
except Exception as e:
    results["congreso_html_discovery"] = {"error": str(e)}

# ─────────────────────────────────────────────────────────────
# 5. Congreso — probar endpoint de descarga masiva/CSV si existe
# Algunas opendata tienen ZIP con todo el período legislativo
# ─────────────────────────────────────────────────────────────
BULK_CANDIDATES = [
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/votaciones.csv",
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/votaciones.json",
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/votaciones.zip",
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15.zip",
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15.csv",
]

bulk_results = {}
for url in BULK_CANDIDATES:
    key = url.split("Leg15")[-1] or "Leg15_root"
    try:
        r = requests.get(url, headers={"User-Agent": UA_BOT}, timeout=10, allow_redirects=True)
        bulk_results[key] = {
            "status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "size_kb": len(r.content) // 1024 if r.status_code == 200 else 0
        }
    except Exception as e:
        bulk_results[key] = {"error": str(e)}

results["congreso_bulk_candidates"] = bulk_results

# ─────────────────────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────────────────────
output_path = "spike_v2_results.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"✓ Resultados guardados en {output_path}")
print(f"  PP candidates tested:   {len(PP_CANDIDATES)}")
print(f"  PSOE candidates tested: {len(PSOE_CANDIDATES)}")
print(f"  BOE entry XML: section 3")
print(f"  Congreso HTML scraping: section 4")
print(f"  Congreso bulk candidates: {len(BULK_CANDIDATES)}")
