import json

import requests


def load_parties(config_path="config/parties.json"):
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


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
