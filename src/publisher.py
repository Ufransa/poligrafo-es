import json
import time

import requests

TELEGRAM_MAX_RETRIES = 3
THROTTLE_SECONDS = 4


def load_parties(config_path="config/parties.json"):
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def normalizar_grupo(titulo_subgrupo):
    """
    El XML alterna el mismo grupo con y sin punto final ("...VOX" y "...VOX."),
    así que la clave del mapa se normaliza en ambos lados.
    """
    return " ".join((titulo_subgrupo or "").split()).rstrip(".").lower()


class _MapaGrupos(dict):
    """dict cuyo .get() normaliza la clave antes de buscarla."""

    def get(self, clave, defecto=None):
        return super().get(normalizar_grupo(clave), defecto)

    def __contains__(self, clave):
        return super().__contains__(normalizar_grupo(clave))


def load_parties_largo(config_path="config/grupos_enmienda.json"):
    """Nombres largos de grupo tal como vienen en TituloSubGrupo → etiqueta corta."""
    with open(config_path, encoding="utf-8") as f:
        crudo = json.load(f)
    return _MapaGrupos({normalizar_grupo(k): v for k, v in crudo.items()})


def send_message(token, channel_id, text, max_retries=TELEGRAM_MAX_RETRIES, sleep=time.sleep):
    """
    Envía un mensaje al canal. Devuelve el message_id o None.

    Ante 429 respeta el retry_after que indica Telegram y reintenta. Cualquier
    otro error se registra con su cuerpo: el silencio de la versión anterior
    ocultó seis semanas de rate limiting.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": channel_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    for intento in range(1, max_retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=15)
        except requests.exceptions.RequestException as e:
            print(f"  WARN: error de red al enviar (intento {intento}/{max_retries}): {e}")
            if intento == max_retries:
                return None
            sleep(THROTTLE_SECONDS)
            continue

        if r.status_code == 200 and r.json().get("ok"):
            return r.json()["result"]["message_id"]

        if r.status_code == 429:
            espera = r.json().get("parameters", {}).get("retry_after", THROTTLE_SECONDS)
            print(f"  Rate limit: esperando {espera}s (intento {intento}/{max_retries})")
            if intento == max_retries:
                return None
            sleep(espera)
            continue

        print(f"  WARN: Telegram devolvió {r.status_code}: {str(r.json())[:300]}")
        return None
    return None
