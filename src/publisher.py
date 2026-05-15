import html
import json
import requests

VOTO_EMOJI = {
    "Sí": "✅",
    "No": "❌",
    "Abstención": "⚠️",
    "No vota": "➖",
}


def load_parties(config_path="config/parties.json"):
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def format_vote_alert(vote, parties):
    """
    vote: dict with session_number, numero_votacion, titulo, texto_expediente, fecha, group_votes
    parties: dict of {code: display_name}
    Returns: HTML string for Telegram (parse_mode=HTML)
    """
    lines = [
        f"🗳️ <b>Sesión {vote['session_number']} · Votación {vote['numero_votacion']}</b>",
        f"<b>{html.escape(vote['titulo'])}</b>",
    ]

    expediente = vote.get("texto_expediente", "").strip()
    if expediente:
        preview = html.escape(expediente[:200]) + ("…" if len(expediente) > 200 else "")
        lines.append(f"<i>{preview}</i>")

    lines.append("")

    for code, gv in sorted(vote["group_votes"].items()):
        emoji = VOTO_EMOJI.get(gv["voto"], "❓")
        name = parties.get(code, code)
        divided_note = " <i>(div.)</i>" if gv.get("divided") else ""
        lines.append(f"{emoji} {name}{divided_note}")

    lines.append("")
    lines.append(f"📅 {vote['fecha']}")

    text = "\n".join(lines)

    if len(text) > 4096:
        text = text[:4093] + "…"

    return text


def send_message(token, channel_id, text):
    """
    Send a message to a Telegram channel.
    Returns telegram message_id (int) on success, None on failure.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
    except requests.exceptions.RequestException:
        return None
    if r.status_code == 200 and r.json().get("ok"):
        return r.json()["result"]["message_id"]
    return None
