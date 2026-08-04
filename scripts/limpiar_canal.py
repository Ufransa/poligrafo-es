#!/usr/bin/env python3
"""
Borra el historial del canal de Telegram. Irreversible.

OJO: el límite de 48 horas de la Bot API se aplica igualmente aunque el bot sea
administrador con can_delete_messages (verificado 2026-08-04: los mensajes de
más de 48h devuelven "message can't be deleted" y uno recién enviado se borra
sin problema). Para limpiar histórico antiguo hay que hacerlo desde el cliente.
"""
import collections
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
    motivos = collections.Counter()
    for msg_id in range(1, hasta + 1):
        if dry_run:
            continue
        r = requests.post(url, json={"chat_id": CHANNEL, "message_id": msg_id}, timeout=15)
        cuerpo = r.json()
        if r.status_code == 200 and cuerpo.get("ok"):
            borrados += 1
        elif r.status_code == 429:
            espera = cuerpo.get("parameters", {}).get("retry_after", 5)
            time.sleep(espera)
            continue
        else:
            # Un recuento de fallos sin el motivo no dice nada: agrupar por
            # descripción para ver de un vistazo si es permisos, antigüedad o
            # que el mensaje sencillamente no existe.
            motivos[cuerpo.get("description", f"HTTP {r.status_code}")] += 1
        time.sleep(0.1)
    print(f"Borrados {borrados} de {hasta} intentos.")
    for motivo, n in motivos.most_common():
        print(f"  {n} x {motivo}")


if __name__ == "__main__":
    hasta = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 260
    run(hasta, dry_run="--dry-run" in sys.argv)
