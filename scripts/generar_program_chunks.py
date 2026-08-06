#!/usr/bin/env python3
"""
Regenera data/program_chunks.json desde los PDF de PARTY_PDFS.

Se ejecuta en el PC, no en la Pi: pdfplumber sobre 8 programas es pesado y el
resultado viaja en el repo (por eso existe import_programs.py en el servidor).

Uso: python scripts/generar_program_chunks.py [--solo PP,PSOE]
"""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from src.matcher import load_categories
from src.programs import PARTY_PDFS, extract_chunks

SALIDA = Path(__file__).resolve().parent.parent / "data" / "program_chunks.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def descargar(url):
    r = requests.get(url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise ValueError(f"no es un PDF ({len(r.content)} bytes)")
    return r.content


def run(solo=None):
    categories = load_categories()
    todos = []
    resumen = []

    for party, url in PARTY_PDFS.items():
        if solo and party not in solo:
            continue
        print(f"{party}...", flush=True)
        try:
            pdf_bytes = descargar(url)
        except Exception as e:
            print(f"  ERROR: {e}")
            resumen.append((party, 0, 0, "FALLO"))
            continue

        chunks = extract_chunks(pdf_bytes, party, categories)
        textos = {c["text"] for c in chunks}
        paginas = {c["page_start"] for c in chunks}
        todos.extend(chunks)
        resumen.append((party, len(textos), len(chunks), f"p.1-{max(paginas) if paginas else 0}"))
        print(f"  {len(textos)} textos únicos, {len(chunks)} filas, "
              f"páginas {min(paginas, default=0)}-{max(paginas, default=0)}")

    if any(r[3] == "FALLO" for r in resumen):
        print("\nAbortado: algún programa falló y el JSON quedaría incompleto.")
        return 1

    SALIDA.write_text(json.dumps(todos, ensure_ascii=False), encoding="utf-8")
    print(f"\nEscrito {SALIDA} — {len(todos)} filas")
    print(f"{'partido':10} {'textos':>7} {'filas':>7}  páginas")
    for party, textos, filas, pags in resumen:
        print(f"{party:10} {textos:>7} {filas:>7}  {pags}")
    return 0


if __name__ == "__main__":
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    sys.exit(run(solo))
