#!/usr/bin/env python3
"""
bootstrap_programs.py — PolígrafoES
One-shot: download party PDFs, extract text chunks, store in DB.
Run once: python bootstrap_programs.py
WARNING: not idempotent — re-running inserts duplicate chunks. Wipe DB first or delete from program_chunks if re-running.
PSOE PDF is Cloudflare-protected — scrapling is used automatically if regular download fails.
"""
from src.db import init_db, get_conn, insert_program_chunk
from src.programs import PARTY_PDFS, download_pdf_bytes, extract_chunks
from src.matcher import load_categories


def run():
    init_db()
    conn = get_conn()
    categories = load_categories()

    try:
        for party, url in PARTY_PDFS.items():
            print(f"\nProcessing {party}...")
            pdf_bytes = download_pdf_bytes(url)

            if pdf_bytes is None and party == "PSOE":
                import os as _os
                local = _os.path.join(_os.path.dirname(__file__), "psoe_programa.pdf")
                if _os.path.exists(local):
                    print("  Using local psoe_programa.pdf...")
                    with open(local, "rb") as _f:
                        _content = _f.read()
                    if _content.startswith(b"%PDF"):
                        pdf_bytes = _content

            if pdf_bytes is None and party == "PSOE":
                print("  Regular download failed for PSOE, trying browser headers...")
                import requests as _req
                for _referer in ("https://www.psoe.es/", "https://www.google.com/"):
                    try:
                        _r = _req.get(url, timeout=(10, 120), headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                            "Referer": _referer,
                            "Accept": "application/pdf,*/*",
                        })
                        if _r.status_code == 200 and _r.content.startswith(b"%PDF"):
                            pdf_bytes = _r.content
                            break
                    except Exception:
                        pass

            if pdf_bytes is None and party == "PSOE":
                print("  Browser headers failed, trying scrapling...")
                try:
                    from scrapling.fetchers import StealthyFetcher
                    fetcher = StealthyFetcher()
                    page = fetcher.fetch(url)
                    raw = page.body if page else None
                    if raw and raw.startswith(b"%PDF"):
                        pdf_bytes = raw
                except Exception as e:
                    print(f"  scrapling failed: {e}")

            if pdf_bytes is None:
                print(f"  WARN: Could not download {party} PDF — skipping.")
                continue

            print(f"  Downloaded {len(pdf_bytes) // 1024}KB. Extracting chunks...")
            chunks = extract_chunks(pdf_bytes, party, categories)
            print(f"  {len(chunks)} categorized chunks extracted.")

            for chunk in chunks:
                insert_program_chunk(
                    conn,
                    party=chunk["party"],
                    category=chunk["category"],
                    page_start=chunk["page_start"],
                    text=chunk["text"],
                )

            print(f"  {party}: {len(chunks)} chunks stored.")

        total = conn.execute("SELECT COUNT(*) FROM program_chunks").fetchone()[0]
        print(f"\nDone. Total program chunks in DB: {total}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
