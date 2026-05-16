#!/usr/bin/env python3
"""
import_programs.py — PolígrafoES
Load pre-extracted program chunks from data/program_chunks.json into the DB.
Run instead of bootstrap_programs.py on servers (no PDFs needed).
"""
import json
import os
from src.db import init_db, get_conn, insert_program_chunk

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "program_chunks.json")


def run():
    if not os.path.exists(DATA_FILE):
        print(f"ERROR: {DATA_FILE} not found.")
        return

    with open(DATA_FILE, encoding="utf-8") as f:
        chunks = json.load(f)

    init_db()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM program_chunks").fetchone()[0]
        if existing > 0:
            print(f"WARNING: {existing} chunks already in DB. Wipe first if re-importing.")
            return

        for c in chunks:
            insert_program_chunk(conn, party=c["party"], category=c["category"],
                                 page_start=c["page_start"], text=c["text"])

        total = conn.execute("SELECT COUNT(*) FROM program_chunks").fetchone()[0]
        print(f"Imported {total} program chunks.")
        for row in conn.execute("SELECT party, COUNT(*) FROM program_chunks GROUP BY party").fetchall():
            print(f"  {row[0]}: {row[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
