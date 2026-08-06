#!/usr/bin/env python3
"""
import_programs.py — PolígrafoES
Load pre-extracted program chunks from data/program_chunks.json into the DB.
Run instead of bootstrap_programs.py on servers (no PDFs needed).
"""
import json
import os
import sys
from src.db import init_db, get_conn, insert_program_chunk

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "program_chunks.json")


def run(wipe=False):
    if not os.path.exists(DATA_FILE):
        print(f"ERROR: {DATA_FILE} not found.")
        return

    with open(DATA_FILE, encoding="utf-8") as f:
        chunks = json.load(f)

    init_db()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM program_chunks").fetchone()[0]
        if existing > 0 and not wipe:
            print(f"WARNING: {existing} chunks already in DB. Wipe first if re-importing "
                  f"(--wipe borra program_chunks y sus matches).")
            return
        if existing > 0:
            # Los matches apuntan a chunk_id: si se vacía la tabla sin ellos,
            # quedan colgando y get_validated_matches devolvería basura.
            conn.execute("DELETE FROM vote_program_matches")
            conn.execute("DELETE FROM program_chunks")
            conn.commit()
            print(f"Wiped {existing} chunks y sus matches.")

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
    run(wipe="--wipe" in sys.argv)
