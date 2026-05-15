#!/usr/bin/env python3
"""
fetcher.py — PolígrafoES
Cron: 21:00 diario
Descubre nuevas sesiones del Congreso, parsea votos, publica en Telegram.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from src.db import init_db, get_conn, get_last_session_number, insert_session, insert_vote, insert_vote_groups, get_unpublished_votes, get_vote_groups, mark_vote_published
from src.congreso import fetch_opendata_html, discover_latest_session, download_session_zip, parse_vote_xml
from src.publisher import load_parties, format_vote_alert, send_message

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL_ID")


def run(dry_run=False):
    if not TOKEN or not CHANNEL:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID must be set in .env")
        sys.exit(1)

    init_db()
    conn = get_conn()
    try:
        parties = load_parties()

        # 1. Discover latest session
        print("Fetching Congreso opendata page…")
        html = fetch_opendata_html()
        session_num, zip_url, session_date = discover_latest_session(html)

        if session_num is None:
            print("No session found on opendata page.")
            return

        last = get_last_session_number(conn)
        print(f"Latest session on web: {session_num} | Last processed: {last}")

        if session_num <= last:
            print("No new sessions. Nothing to do.")
            return

        # 2. Download and parse session ZIP
        print(f"New session {session_num} ({session_date}). Downloading ZIP…")
        xml_files = download_session_zip(zip_url)
        print(f"  {len(xml_files)} vote files found.")

        session_id = insert_session(conn, session_num, session_date, zip_url=zip_url)

        for filename, xml_str in xml_files:
            try:
                vote = parse_vote_xml(xml_str)
            except Exception as e:
                print(f"  WARN: Could not parse {filename}: {e}")
                continue

            vote_id = insert_vote(
                conn,
                session_id,
                vote["numero_votacion"],
                vote["titulo"],
                vote["texto_expediente"],
                vote["fecha"],
            )
            insert_vote_groups(conn, vote_id, vote["group_votes"])
            print(f"  Stored vote {vote['numero_votacion']}: {vote['titulo'][:60]}")

        # 3. Publish unpublished votes
        unpublished = get_unpublished_votes(conn)
        print(f"\n{len(unpublished)} votes to publish.")

        for row in unpublished:
            vote_id = row["id"]
            group_rows = get_vote_groups(conn, vote_id)

            vote_data = {
                "session_number": row["session_number"],
                "numero_votacion": row["vote_number"],
                "titulo": row["titulo"],
                "texto_expediente": row["texto_expediente"],
                "fecha": row["fecha"],
                "zip_url": row["zip_url"],
                "group_votes": {
                    g["grupo_code"]: {
                        "voto": g["voto"],
                        "total": g["total_diputados"],
                        "divided": bool(g["divided"]),
                    }
                    for g in group_rows
                },
            }

            text = format_vote_alert(vote_data, parties)

            if dry_run:
                print("\n--- DRY RUN MESSAGE ---")
                print(text)
                print("--- END ---")
                mark_vote_published(conn, vote_id, telegram_message_id=0)
                continue

            msg_id = send_message(TOKEN, CHANNEL, text)
            if msg_id:
                mark_vote_published(conn, vote_id, telegram_message_id=msg_id)
                print(f"  Published vote {vote_data['numero_votacion']} -> Telegram msg {msg_id}")
            else:
                print(f"  WARN: Failed to send vote {vote_data['numero_votacion']}")

        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
