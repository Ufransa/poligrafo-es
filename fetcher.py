#!/usr/bin/env python3
"""
fetcher.py — PolígrafoES v2
Cron: 21:00 diario
Descubre nuevas sesiones del Congreso y el sumario BOE del día, y enriquece
cada item con Haiku 4.5 (resumen llano + juez de matches). NO publica nada:
la publicación es exclusiva del digest semanal (digest.py, lunes 10:30).
"""
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from src.db import (
    init_db, get_conn,
    get_last_session_number, insert_session, insert_vote, insert_vote_groups,
    insert_boe_entry, get_all_program_chunks,
    insert_vote_program_match,
    get_unenriched_votes, set_vote_enrichment,
    get_unenriched_boe_entries, set_boe_enrichment,
)
from src.congreso import (
    fetch_opendata_html, discover_latest_session, download_session_zip,
    parse_vote_xml, compute_resultado, classify_vote, expediente_key,
)
from src.boe import fetch_boe_sumario, extract_boe_items, fetch_boe_entry
from src.matcher import categorize_text, load_categories, top_candidates_per_party
from src.llm import enrich_vote, summarize_boe


def enrich_pending(conn):
    """Enriquece con LLM todos los items pendientes (enriched_at IS NULL).
    Un fallo en un item no detiene el resto: queda NULL y se reintenta mañana."""
    all_chunks = get_all_program_chunks(conn)

    for row in get_unenriched_votes(conn):
        try:
            vote_text = row["titulo"] + " " + (row["texto_expediente"] or "")
            candidates = top_candidates_per_party(vote_text, all_chunks)
            enrichment = enrich_vote(
                {"titulo": row["titulo"], "texto_expediente": row["texto_expediente"] or ""},
                candidates,
            )
            score_by_chunk = {
                c["chunk_id"]: c["score"]
                for cands in candidates.values() for c in cands
            }
            for m in enrichment.matches:
                insert_vote_program_match(
                    conn, row["id"], m.chunk_id, m.party,
                    score_by_chunk.get(m.chunk_id, 0),
                )
            set_vote_enrichment(conn, row["id"], enrichment.resumen, enrichment.que_cambia)
            print(f"  Enriched vote {row['id']}: {enrichment.resumen}")
        except Exception as e:
            print(f"  WARN: enrichment failed for vote {row['id']}: {e}")

    for row in get_unenriched_boe_entries(conn):
        try:
            resumen = summarize_boe(
                {
                    "titulo": row["titulo"],
                    "rango": row["rango"],
                    "departamento": row["departamento"],
                    "texto_preview": row["texto_preview"],
                }
            )
            set_boe_enrichment(conn, row["id"], resumen)
            print(f"  Enriched BOE {row['identificador']}: {resumen[:60]}")
        except Exception as e:
            print(f"  WARN: enrichment failed for BOE {row['identificador']}: {e}")


def run():
    init_db()
    conn = get_conn()
    try:
        categories = load_categories()

        # 1. Descubrir última sesión del Congreso
        print("Fetching Congreso opendata page...")
        html_page = fetch_opendata_html()
        session_num, zip_url, session_date = discover_latest_session(html_page)

        if session_num is None:
            print("No session found on opendata page.")
        else:
            last = get_last_session_number(conn)
            print(f"Latest session on web: {session_num} | Last processed: {last}")

            if session_num > last:
                print(f"New session {session_num} ({session_date}). Downloading ZIP...")
                xml_files = download_session_zip(zip_url)
                print(f"  {len(xml_files)} vote files found.")

                session_id = insert_session(conn, session_num, session_date, zip_url=zip_url)

                for filename, xml_str in xml_files:
                    try:
                        vote = parse_vote_xml(xml_str)
                    except Exception as e:
                        print(f"  WARN: Could not parse {filename}: {e}")
                        continue

                    vote_cats = categorize_text(
                        vote["titulo"] + " " + vote["texto_expediente"], categories
                    )
                    vote_id = insert_vote(
                        conn,
                        session_id,
                        vote["numero_votacion"],
                        vote["titulo"],
                        vote["texto_expediente"],
                        vote["fecha"],
                        categories=vote_cats,
                        a_favor=vote["a_favor"],
                        en_contra=vote["en_contra"],
                        abstenciones=vote["abstenciones"],
                        resultado=compute_resultado(vote["a_favor"], vote["en_contra"]),
                        titulo_subgrupo=vote["titulo_subgrupo"],
                        texto_subgrupo=vote["texto_subgrupo"],
                        clase=classify_vote(vote["titulo_subgrupo"]),
                        expediente_key=expediente_key(vote["texto_expediente"]),
                    )
                    insert_vote_groups(conn, vote_id, vote["group_votes"])
                    print(f"  Stored vote {vote['numero_votacion']}: {vote['titulo'][:60]}")
            else:
                print("No new sessions. Nothing to do.")

        # 2. Ingesta BOE del día
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        print(f"\nFetching BOE sumario for {today}...")
        sumario_data = fetch_boe_sumario(today)

        if sumario_data is None:
            print("  BOE not available for today (holiday or weekend).")
        else:
            items = extract_boe_items(sumario_data)
            print(f"  {len(items)} items in sections I+II.")

            for item in items:
                try:
                    entry_info = fetch_boe_entry(item["url_xml"])
                    rango = entry_info["rango"] if entry_info else ""
                    texto_preview = entry_info["texto_preview"] if entry_info else ""

                    cats = categorize_text(item["titulo"] + " " + texto_preview, categories)
                    insert_boe_entry(
                        conn,
                        identificador=item["identificador"],
                        titulo=item["titulo"],
                        rango=rango,
                        departamento=item["departamento"],
                        fecha=item["fecha"],
                        url_xml=item["url_xml"],
                        categories=cats,
                        texto_preview=texto_preview,
                    )
                except Exception as e:
                    print(f"  WARN: Could not process BOE item {item.get('identificador')}: {e}")
                    continue

        # 3. Enriquecimiento LLM (items nuevos + reintentos de días fallidos)
        print("\nEnriching pending items...")
        enrich_pending(conn)

        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
