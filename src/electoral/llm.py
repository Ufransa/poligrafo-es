# src/electoral/llm.py
"""Cliente de OpenRouter con tope de gasto. Ningún modelo de Anthropic (decisión de Fran)."""
import importlib.util
import json
import os
import threading
import time

import requests
from dotenv import load_dotenv

URL = "https://openrouter.ai/api/v1/chat/completions"
RAZONAMIENTO = {   # el razonamiento oculto se cobra como salida: apagado o al mínimo
    "deepseek/deepseek-v4-flash": {"enabled": False},
    "deepseek/deepseek-v4-pro": {"enabled": False},
    "openai/gpt-5-mini": {"effort": "minimal"},
    "openai/gpt-5-nano": {"effort": "minimal"},
}


class PresupuestoAgotado(Exception):
    pass


def _transporte_openrouter(clave):
    sesion = requests.Session()

    def enviar(body):
        for intento in range(3):
            r = sesion.post(URL, json=body, headers={"Authorization": f"Bearer {clave}"}, timeout=120)
            if r.status_code == 200:
                return r.json()
            time.sleep(3 * (intento + 1))
        return {"error": r.status_code}
    return enviar


def _transporte_falso(ruta):
    spec = importlib.util.spec_from_file_location("llm_falso", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.transporte


class LLM:
    def __init__(self, tope_usd: float, transporte=None):
        self.tope = tope_usd
        self.gastado = 0.0
        self._lock = threading.Lock()
        if transporte is None:
            falso = os.environ.get("ELECTORAL_LLM_FALSO")
            if falso:
                transporte = _transporte_falso(falso)
            else:
                load_dotenv()
                transporte = _transporte_openrouter(os.environ["OPENROUTER_API_KEY"])
        self._enviar = transporte

    def json(self, modelo: str, sistema: str, usuario: str, max_tokens: int = 1500):
        with self._lock:
            if self.gastado >= self.tope:
                raise PresupuestoAgotado(f"gastados {self.gastado:.4f} $ de {self.tope} $")
        body = {"model": modelo, "max_tokens": max_tokens, "temperature": 0,
                "response_format": {"type": "json_object"}, "usage": {"include": True},
                "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
        if modelo in RAZONAMIENTO:
            body["reasoning"] = RAZONAMIENTO[modelo]
        d = self._enviar(body)
        with self._lock:
            self.gastado += float((d.get("usage") or {}).get("cost") or 0)
        try:
            texto = d["choices"][0]["message"]["content"] or ""
            return json.loads(texto[texto.find("{"): texto.rfind("}") + 1])
        except (KeyError, IndexError, ValueError):
            return None
