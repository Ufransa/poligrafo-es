#!/usr/bin/env python3
"""
embed_programs.py — one-off
Vectoriza los chunks de programa electoral que aún no tienen embedding.
Idempotente: re-ejecutarlo solo procesa lo que falte.
"""
from src.db import init_db, get_conn, set_chunk_embedding
from src.embeddings import embed_texts, to_blob

LOTE = 64


def run():
    init_db()
    conn = get_conn()
    try:
        pendientes = conn.execute(
            "SELECT id, text FROM program_chunks WHERE embedding IS NULL"
        ).fetchall()
        print(f"{len(pendientes)} chunks pendientes de vectorizar.")
        for i in range(0, len(pendientes), LOTE):
            lote = pendientes[i:i + LOTE]
            vectores = embed_texts([r["text"] for r in lote], "passage: ")
            for row, vector in zip(lote, vectores):
                set_chunk_embedding(conn, row["id"], to_blob(vector))
            print(f"  {min(i + LOTE, len(pendientes))}/{len(pendientes)}")
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
