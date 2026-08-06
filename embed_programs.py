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

        # Una fila por (texto, categoría) hace que el mismo texto aparezca hasta
        # 12 veces. Vectorizar por texto único y repartir el vector evita
        # multiplicar por 4 el trabajo, que en la Orange Pi son horas.
        por_texto = {}
        for row in pendientes:
            por_texto.setdefault(row["text"], []).append(row["id"])

        textos = list(por_texto)
        print(f"{len(pendientes)} filas pendientes ({len(textos)} textos únicos).")
        for i in range(0, len(textos), LOTE):
            lote = textos[i:i + LOTE]
            vectores = embed_texts(lote, "passage: ")
            for texto, vector in zip(lote, vectores):
                blob = to_blob(vector)
                for chunk_id in por_texto[texto]:
                    set_chunk_embedding(conn, chunk_id, blob)
            print(f"  {min(i + LOTE, len(textos))}/{len(textos)}")
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
