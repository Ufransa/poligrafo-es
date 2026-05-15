#!/usr/bin/env python3
"""
data_spike.py v4 — PolígrafoES
Output: spike_results.json
Ejecutar: python data_spike.py
"""

import requests
import json
import tempfile
import os
from datetime import date, timedelta

TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PoligrafoES/spike)"}
results = {}

def get(url, accept_xml=False, accept_json=False):
    h = dict(HEADERS)
    if accept_json:
        h["Accept"] = "application/json"
    if accept_xml:
        h["Accept"] = "application/xml"
    return requests.get(url, headers=h, timeout=TIMEOUT, allow_redirects=True)

def get_pdf(url):
    r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    if r.status_code == 200 and r.content[:4] == b'%PDF':
        return r.content
    return None

# ─────────────────────────────────────────────────────────────
# 1. CONGRESO — XML completo de una votación conocida
# Pregunta crítica: ¿incluye votos por grupo parlamentario?
# ─────────────────────────────────────────────────────────────
VOT_URL = "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion034/20240409/Votacion001/VOT_20240409210629.xml"
try:
    r = get(VOT_URL)
    results["congreso_vot_xml"] = {
        "status": r.status_code,
        "content_type": r.headers.get("content-type"),
        "full_xml": r.text if r.status_code == 200 else None,
        "error": None
    }
except Exception as e:
    results["congreso_vot_xml"] = {"status": None, "error": str(e)}

# ─────────────────────────────────────────────────────────────
# 2. CONGRESO — descubrimiento de índice de sesiones
# ─────────────────────────────────────────────────────────────
index_results = {}
INDEX_CANDIDATES = [
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/index.xml",
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/index.json",
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion001/",
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion001/index.xml",
    "https://www.congreso.es/webpublica/opendata/votaciones/Leg15/Sesion001/20231102/Votacion001/",
]
for url in INDEX_CANDIDATES:
    key = url.split("Leg15/")[-1].rstrip("/") or "Leg15/"
    try:
        r = get(url)
        index_results[key] = {
            "status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "body_preview": r.text[:500] if r.status_code == 200 else None
        }
    except Exception as e:
        index_results[key] = {"status": None, "error": str(e)}
results["congreso_index_discovery"] = index_results

# ─────────────────────────────────────────────────────────────
# 3. BOE — sumario completo de hoy
# ─────────────────────────────────────────────────────────────
for days_ago in range(0, 5):
    test_date = (date.today() - timedelta(days=days_ago)).strftime("%Y%m%d")
    try:
        r = get(f"https://www.boe.es/datosabiertos/api/boe/sumario/{test_date}", accept_json=True)
        if r.status_code == 200:
            results["boe_sumario"] = {
                "date": test_date,
                "status": 200,
                "data": r.json()
            }
            break
        results["boe_sumario"] = {"date": test_date, "status": r.status_code}
    except Exception as e:
        results["boe_sumario"] = {"date": test_date, "error": str(e)}

# ─────────────────────────────────────────────────────────────
# 4. BOE — formatos para entrada individual
# ─────────────────────────────────────────────────────────────
boe_id_results = {}
BOE_ID_CANDIDATES = [
    "https://www.boe.es/datosabiertos/api/boe/id/BOE-A-2023-14240",
    "https://www.boe.es/datosabiertos/api/boe/anuncio/BOE-A-2023-14240",
]
for url in BOE_ID_CANDIDATES:
    key = url.split("/api/")[-1]
    try:
        r = requests.get(url, headers={**HEADERS, "Accept": "application/xml"}, timeout=TIMEOUT)
        boe_id_results[key] = {
            "status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "body_preview": r.text[:600]
        }
    except Exception as e:
        boe_id_results[key] = {"status": None, "error": str(e)}
results["boe_id_formats"] = boe_id_results

# ─────────────────────────────────────────────────────────────
# 5. PROGRAMAS ELECTORALES — PDFs con text extraction
# ─────────────────────────────────────────────────────────────
PDF_URLS = {
    "PP":    "https://www.pp.es/sites/default/files/documentos/programa_electoral_pp_23j_feijoo_2023.pdf",
    "PP_alt1": "https://www.pp.es/sites/default/files/documentos/programa-electoral-pp-23j-feijoo-2023.pdf",
    "PP_alt2": "https://www.pp.es/sites/default/files/documentos/programa_pp_23j_2023.pdf",
    "PSOE":  "https://www.psoe.es/media-content/2023/07/PROGRAMA_ELECTORAL-GENERALES-2023.pdf",
    "PSOE_alt1": "https://assets.ctfassets.net/obkb3v0fkpml/7J6mGGOJSsTunmNaVUbYW4/ec29ffc51bf60e2ed4bf1ffc06ce46c9/Programa_electoral_PSOE_2023.pdf",
    "SUMAR": "https://www.newtral.es/wp-content/uploads/2023/07/Programa_electoral_sumar_23j_2023.pdf",
    "VOX":   "https://files.mediaset.es/file/2023/0707/15/programa-vox-completo-pdf.pdf",
}

pdf_results = {}
try:
    import pdfplumber

    for party, url in PDF_URLS.items():
        try:
            content = get_pdf(url)
            if content is None:
                r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
                pdf_results[party] = {
                    "url": url,
                    "downloaded": False,
                    "http_status": r.status_code,
                    "content_type": r.headers.get("content-type"),
                    "size_kb": len(r.content) // 1024
                }
                continue

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp.write(content)
            tmp.close()

            try:
                with pdfplumber.open(tmp.name) as pdf:
                    total_pages = len(pdf.pages)
                    samples = {}
                    for page_num in [0, 1, 4, 9, 14, 19]:
                        if page_num < total_pages:
                            text = (pdf.pages[page_num].extract_text() or "").strip()
                            samples[f"page_{page_num+1}"] = text[:300] if text else "(vacío)"
                    pdf_results[party] = {
                        "url": url,
                        "downloaded": True,
                        "size_kb": len(content) // 1024,
                        "total_pages": total_pages,
                        "text_samples": samples
                    }
            except Exception as e:
                pdf_results[party] = {"url": url, "downloaded": True,
                                       "extraction_error": str(e)}
            finally:
                os.unlink(tmp.name)

        except Exception as e:
            pdf_results[party] = {"url": url, "error": str(e)}

except ImportError:
    pdf_results["_error"] = "pdfplumber no instalado. pip install pdfplumber"

results["programas_electorales"] = pdf_results

# ─────────────────────────────────────────────────────────────
# OUTPUT — todo como JSON
# ─────────────────────────────────────────────────────────────
output_path = "spike_results.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"✓ Resultados guardados en {output_path}")
print(f"  Abre el archivo o pégalo en el chat.")
