#!/usr/bin/env python3
"""
Borra el historial del canal de Telegram. Irreversible.
El bot es administrador con can_delete_messages, así que no le aplica el límite
de 48 horas de la API.
"""
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL = os.environ["TELEGRAM_CHANNEL_ID"]


def run(hasta, dry_run=False):
    url = f"https://api.telegram.org/bot{TOKEN}/deleteMessage"
    borrados = 0
    for msg_id in range(1, hasta + 1):
        if dry_run:
            continue
        r = requests.post(url, json={"chat_id": CHANNEL, "message_id": msg_id}, timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            borrados += 1
        elif r.status_code == 429:
            espera = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(espera)
            continue
        time.sleep(0.1)
    print(f"Borrados {borrados} de {hasta} intentos.")


if __name__ == "__main__":
    hasta = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 260
    run(hasta, dry_run="--dry-run" in sys.argv)
