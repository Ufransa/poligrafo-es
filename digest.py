#!/usr/bin/env python3
"""
digest.py — PolígrafoES
Cron: 10:30 Monday
Publishes weekly digest of votes and BOE entries from the past 7 days.
"""
import html
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from src.db import (
    init_db, get_conn,
    get_published_votes_since, get_published_boe_entries_since, get_vote_groups_for_votes,
)
from src.publisher import load_parties, send_message

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL_ID")

_VOTO_EMOJI = {"Sí": "✅", "No": "❌", "Abstención": "⚠️", "No vota": "➖"}
_DIGEST_PARTIES = [
    ("GP",     "PP"),
    ("GS",     "PS"),
    ("GSUMAR", "SU"),
    ("GVOX",   "VX"),
]


def _vote_line(vote_row, groups):
    titulo = vote_row["titulo"]
    title_short = html.escape(titulo[:55]) + ("…" if len(titulo) > 55 else "")
    parts = []
    for code, abbr in _DIGEST_PARTIES:
        voto = groups.get(code)
        if voto:
            emoji = _VOTO_EMOJI.get(voto, "❓")
            parts.append(f"{abbr}{emoji}")
    return f"· {title_short}  {'  '.join(parts)}"


def _boe_line(entry):
    titulo = entry["titulo"]
    title_short = html.escape(titulo[:60]) + ("…" if len(titulo) > 60 else "")
    cats_raw = entry["categories"]
    cats = json.loads(cats_raw) if isinstance(cats_raw, str) else cats_raw
    cat_str = " · ".join(cats[:2]) if cats else ""
    boe_id = entry["identificador"]
    url = f"https://www.boe.es/diario_boe/txt.php?id={boe_id}"
    line = f"· {title_short}"
    if cat_str:
        line += f" — {cat_str}"
    line += f' · <a href="{url}">ver</a>'
    return line


def format_digest(votes, vote_groups_map, boe_entries, week_start, parties):
    """
    Format weekly digest.
    Returns a string if it fits in 4096 chars, or a list of two strings if it needs splitting.
    """
    header = (
        f"📊 <b>Semana del {week_start}</b>\n"
        f"{len(votes)} votaciones · {len(boe_entries)} leyes BOE relevantes"
    )
    footer = "PolígrafoES · datos sin editar"

    vote_lines = []
    if votes:
        vote_lines.append("\n🗳️ <b>VOTACIONES</b>")
        for row in votes:
            groups = vote_groups_map.get(row["id"], {})
            vote_lines.append(_vote_line(row, groups))

    boe_lines = []
    if boe_entries:
        boe_lines.append("\n📜 <b>BOE RELEVANTE</b>")
        for entry in boe_entries:
            boe_lines.append(_boe_line(entry))

    full = "\n".join([header] + vote_lines + boe_lines + ["", footer])

    if len(full) <= 4096:
        return full

    # Split: votes message + BOE message
    msg1_parts = [header] + vote_lines + ["", footer]
    msg2_parts = [f"📜 <b>BOE RELEVANTE — semana del {week_start}</b>"] + boe_lines[1:] + ["", footer]
    msg1 = "\n".join(msg1_parts)
    msg2 = "\n".join(msg2_parts)

    if len(msg1) > 4096:
        msg1 = msg1[:4093] + "…"
    if len(msg2) > 4096:
        msg2 = msg2[:4093] + "…"

    return [msg1, msg2]


def run(dry_run=False):
    if not TOKEN or not CHANNEL:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID must be set in .env")
        sys.exit(1)

    init_db()
    conn = get_conn()
    try:
        parties = load_parties()
        since_iso = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        week_start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%d/%m/%Y")

        votes = get_published_votes_since(conn, since_iso)
        boe_entries = get_published_boe_entries_since(conn, since_iso)

        print(f"Digest: {len(votes)} votes, {len(boe_entries)} BOE entries since {week_start}.")

        if not votes and not boe_entries:
            print("Nothing to digest this week.")
            return

        vote_ids = [row["id"] for row in votes]
        vote_groups_map = get_vote_groups_for_votes(conn, vote_ids)

        result = format_digest(votes, vote_groups_map, boe_entries, week_start, parties)
        messages = [result] if isinstance(result, str) else result

        for i, text in enumerate(messages, 1):
            if dry_run:
                print(f"\n--- DRY RUN DIGEST (msg {i}/{len(messages)}) ---")
                print(text)
                print("--- END ---")
                continue
            msg_id = send_message(TOKEN, CHANNEL, text)
            if msg_id:
                print(f"  Sent digest msg {i} -> Telegram msg {msg_id}")
            else:
                print(f"  WARN: Failed to send digest msg {i}")

        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
