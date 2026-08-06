#!/usr/bin/env python3
"""
digest.py — PolígrafoES v2
Cron: lunes 10:30
Publica el digest semanal: plantilla pura sobre datos ya enriquecidos por el
fetcher. Sin llamadas LLM. Publica todo lo published=0 y lo marca — un lunes
fallido se recupera solo en el siguiente run.
"""
import collections
import html
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.db import (
    DEFAULT_DB, init_db, get_conn,
    get_expedientes_for_digest, get_boe_for_digest, get_validated_matches,
    get_vote_groups, mark_votes_published, mark_boe_published,
)
from src.publisher import (load_parties, load_parties_largo, send_message,
                           THROTTLE_SECONDS)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL_ID")

TELEGRAM_LIMIT = 4096

_SENSE_ORDER = ["Sí", "No", "Abstención", "No vota"]
_SENSE_LABEL = {"Sí": "A favor", "No": "En contra",
                "Abstención": "Abstención", "No vota": "No votó"}
_SENSE_ICON = {"Sí": "✅", "No": "❌", "Abstención": "⚪", "No vota": "—"}
_RESULT_LABEL = {"aprobada": "✅ APROBADA", "rechazada": "❌ RECHAZADA"}


_VEREDICTO_TEXTO = {
    "cumple": "Coherente con su programa.",
    "incumple": "Incoherente con su programa.",
}

# El juez emitía veredictos contradictorios porque el prompt no le decía cómo
# había votado cada partido (dry-run del 2026-08-04: misma promesa de Sumar,
# mismo sentido de voto, "coherente" en una ficha e "incoherente" en la
# siguiente). Corregido y validado sobre los 16 expedientes de julio: 6
# veredictos, todos defendibles, y silencio en 11 de 16.
PUBLICAR_VEREDICTOS = True


def format_expediente_block(exp, parties, grupos_largos):
    """Una ficha por ley: qué se votó, cómo acabó, quién votó qué."""
    sus = exp["sustantiva"]
    lines = []

    titulo = sus.get("resumen") or (sus["titulo"] or "")[:120]
    lines.append(f"🗳️ <b>{html.escape(titulo)}</b>")

    resultado = _RESULT_LABEL.get(sus.get("resultado"), "")
    if resultado:
        totales = ""
        if sus.get("a_favor") is not None and sus.get("en_contra") is not None:
            totales = f" ({sus['a_favor']} a favor / {sus['en_contra']} en contra)"
        # La fecha distingue dos expedientes con el mismo título oficial, que el
        # Congreso vota más de una vez (p.ej. los objetivos de estabilidad).
        fecha = f" · {sus['fecha']}" if sus.get("fecha") else ""
        lines.append(f"{resultado}{totales}{fecha}")
    if sus.get("que_cambia"):
        lines.append(html.escape(sus["que_cambia"]))

    lines.append("")
    by_sense = {}
    for code, gv in exp.get("groups", {}).items():
        name = parties.get(code, code)
        if gv.get("divided"):
            name += " (div.)"
        by_sense.setdefault(gv["voto"], []).append(name)
    for s in _SENSE_ORDER:
        if s in by_sense:
            lines.append(
                f"{_SENSE_ICON[s]} {_SENSE_LABEL[s]}: "
                f"{html.escape(' · '.join(by_sense[s]))}"
            )

    parciales = exp.get("parciales") or []
    if parciales:
        por_grupo = collections.Counter(
            grupos_largos.get(p["titulo_subgrupo"], p["titulo_subgrupo"])
            for p in parciales
        )
        detalle = " · ".join(f"{g} {n}" for g, n in por_grupo.most_common())
        lines.append("")
        lines.append(f"🔎 {len(parciales)} enmiendas votadas antes del texto final.")
        lines.append(f"   {html.escape(detalle)}")

    veredictos = [m for m in exp.get("matches", []) if m.get("veredicto")] \
        if PUBLICAR_VEREDICTOS else []
    if veredictos:
        lines.append("")
        for m in veredictos:
            # Sin referencia de página: page_start es el índice del trozo de
            # texto, no la página del PDF, así que citarlo mandaba al lector a
            # buscar en una página que no existe.
            lines.append(
                f"📋 <b>{html.escape(m['party'])}</b> prometió: "
                f"<i>{html.escape(m['promesa'])}</i> → "
                f"{_VEREDICTO_TEXTO[m['veredicto']]}"
            )

    return "\n".join(lines)


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
        grupos_largos = load_parties_largo()
        expedientes = get_expedientes_for_digest(conn)
        boe_rows = get_boe_for_digest(conn)

        print(f"Digest: {len(expedientes)} expedientes, {len(boe_rows)} BOE pendientes.")
        if not expedientes and not boe_rows:
            print("Nothing to digest this week.")
            return

        # Un mensaje por expediente: cada uno se marca en cuanto sale.
        for exp in expedientes:
            # get_expedientes_for_digest devuelve sqlite3.Row, que no tiene .get()
            sus = dict(exp["sustantiva"])
            exp["sustantiva"] = sus
            exp["parciales"] = [dict(p) for p in exp["parciales"]]
            exp["groups"] = {
                g["grupo_code"]: {"voto": g["voto"], "divided": bool(g["divided"])}
                for g in get_vote_groups(conn, sus["id"])
            }
            exp["matches"] = [dict(m) for m in get_validated_matches(conn, sus["id"])]
            texto = format_expediente_block(exp, parties, grupos_largos)

            if dry_run:
                print(f"\n--- DRY RUN expediente {sus['id']} ---\n{texto}\n--- END ---")
                continue

            msg_id = send_message(TOKEN, CHANNEL, texto)
            if msg_id:
                ids = [sus["id"]] + [p["id"] for p in exp["parciales"]]
                mark_votes_published(conn, ids, msg_id)
                print(f"  Sent expediente {sus['id']} -> msg {msg_id}")
            else:
                print(f"  WARN: falló el envío del expediente {sus['id']}; sigue pendiente")
            time.sleep(THROTTLE_SECONDS)

        if boe_rows:
            boe_lines = ["📜 <b>BOE — normas con rango de ley</b>"]
            boe_lines += [format_boe_line(dict(r)) for r in boe_rows]
            for texto in build_messages("", ["\n".join(boe_lines)], "PolígrafoES"):
                if dry_run:
                    print(f"\n--- DRY RUN BOE ---\n{texto}\n--- END ---")
                    continue
                msg_id = send_message(TOKEN, CHANNEL, texto)
                if msg_id:
                    mark_boe_published(conn, [r["id"] for r in boe_rows], msg_id)
                    print(f"  Sent bloque BOE ({len(boe_rows)} normas) -> msg {msg_id}")
                else:
                    print("  WARN: falló el envío del bloque BOE; sigue pendiente")
                time.sleep(THROTTLE_SECONDS)

        if dry_run:
            print("\nDry run: nada marcado como publicado.")
        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
