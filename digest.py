#!/usr/bin/env python3
"""
digest.py — PolígrafoES v2
Cron: lunes 10:30
Publica el digest semanal: plantilla pura sobre datos ya enriquecidos por el
fetcher. Sin llamadas LLM. Publica todo lo published=0 y lo marca — un lunes
fallido se recupera solo en el siguiente run.
"""
import html
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.db import (
    DEFAULT_DB, init_db, get_conn,
    get_votes_for_digest, get_boe_for_digest, get_validated_matches,
    get_vote_groups, mark_digest_published,
)
from src.publisher import load_parties, send_message

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL_ID")

TELEGRAM_LIMIT = 4096

_SENSE_ORDER = ["Sí", "No", "Abstención", "No vota"]
_SENSE_LABEL = {"Sí": "A favor", "No": "En contra",
                "Abstención": "Abstención", "No vota": "No votó"}
_SENSE_ICON = {"Sí": "✅", "No": "❌", "Abstención": "⚪", "No vota": "—"}
_RESULT_LABEL = {"aprobada": "✅ APROBADA", "rechazada": "❌ RECHAZADA"}


def format_vote_block(vote, parties):
    """
    vote: dict {titulo, resumen, que_cambia, resultado,
                groups: {code: {voto, divided}}, matches: [{party, text, page_start}]}
    Enriquecido → resumen en cristiano + resultado + consecuencia.
    Sin enriquecer → fallback al título oficial, sin inventar nada.
    """
    if vote.get("resumen"):
        result = _RESULT_LABEL.get(vote.get("resultado"), "")
        header = f"🗳️ <b>{html.escape(vote['resumen'])}</b>"
        if result:
            header += f" — {result}"
        lines = [header, html.escape(vote.get("que_cambia") or "")]
    else:
        titulo = vote["titulo"]
        short = html.escape(titulo[:120]) + ("…" if len(titulo) > 120 else "")
        lines = [f"🗳️ <b>{short}</b>"]

    by_sense = {}
    for code, gv in vote.get("groups", {}).items():
        name = parties.get(code, code)
        if gv.get("divided"):
            name += " (div.)"
        by_sense.setdefault(gv["voto"], []).append(name)
    for s in _SENSE_ORDER:
        if s in by_sense:
            icon = _SENSE_ICON[s]
            parties_str = " · ".join(by_sense[s])
            lines.append(f"{icon} {_SENSE_LABEL[s]}: {html.escape(parties_str)}")

    for m in vote.get("matches", []):
        excerpt = html.escape(m["text"][:200]) + ("…" if len(m["text"]) > 200 else "")
        lines.append(
            f"📋 <b>{html.escape(m['party'])}</b> en su programa (p.{m['page_start']}): <i>{excerpt}</i>"
        )

    return "\n".join(line for line in lines if line)


def format_boe_line(entry):
    text = entry.get("resumen") or entry["titulo"]
    short = html.escape(text[:160]) + ("…" if len(text) > 160 else "")
    url = f"https://www.boe.es/diario_boe/txt.php?id={entry['identificador']}"
    return f'· {short} · <a href="{url}">ver</a>'


def build_messages(header, blocks, footer, limit=TELEGRAM_LIMIT):
    """Empaqueta bloques en el mínimo de mensajes ≤ limit; header en el primero,
    footer al final de cada mensaje para que cada uno se sostenga solo."""
    messages = []
    current = header
    for block in blocks:
        candidate = current + "\n\n" + block
        if len(candidate) + len(footer) + 2 > limit:
            messages.append(current + "\n\n" + footer)
            current = block
        else:
            current = candidate
    messages.append(current + "\n\n" + footer)
    return messages


def run(dry_run=False, db_path=None):
    if not TOKEN or not CHANNEL:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID must be set in .env")
        sys.exit(1)

    db_path = db_path or DEFAULT_DB
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        parties = load_parties()
        vote_rows = get_votes_for_digest(conn)
        boe_rows = get_boe_for_digest(conn)

        print(f"Digest: {len(vote_rows)} votes, {len(boe_rows)} BOE entries pending.")
        if not vote_rows and not boe_rows:
            print("Nothing to digest this week.")
            return

        blocks = []
        for row in vote_rows:
            groups = {
                g["grupo_code"]: {"voto": g["voto"], "divided": bool(g["divided"])}
                for g in get_vote_groups(conn, row["id"])
            }
            vote = dict(row)
            vote["groups"] = groups
            vote["matches"] = [dict(m) for m in get_validated_matches(conn, row["id"])]
            blocks.append(format_vote_block(vote, parties))

        if boe_rows:
            boe_lines = ["📜 <b>BOE en cristiano</b>"]
            boe_lines += [format_boe_line(dict(r)) for r in boe_rows]
            blocks.append("\n".join(boe_lines))

        now = datetime.now()
        header = (
            f"📊 <b>Congreso — semana hasta el {now.day:02d}/{now.month:02d}/{now.year}</b>\n"
            f"{len(vote_rows)} votaciones · {len(boe_rows)} leyes BOE relevantes"
        )
        footer = "PolígrafoES"

        messages = build_messages(header, blocks, footer)

        sent_ids = []
        for i, text in enumerate(messages, 1):
            if dry_run:
                print(f"\n--- DRY RUN DIGEST (msg {i}/{len(messages)}) ---")
                print(text)
                print("--- END ---")
                sent_ids.append(0)
                continue
            msg_id = send_message(TOKEN, CHANNEL, text)
            if msg_id:
                sent_ids.append(msg_id)
                print(f"  Sent digest msg {i} -> Telegram msg {msg_id}")
            else:
                print(f"  WARN: Failed to send digest msg {i}")

        if dry_run:
            print("Dry run: items NOT marked as published.")
        elif sent_ids and len(sent_ids) == len(messages):
            mark_digest_published(
                conn,
                [r["id"] for r in vote_rows],
                [r["id"] for r in boe_rows],
                telegram_message_id=sent_ids[-1],
            )
            print("Marked items as published.")
        else:
            print("WARN: incomplete send; items remain pending for next run.")

        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
