# tests/fixtures/electoral/llm_falso.py
"""LLM falso para las pruebas. Reglas por contenido del mensaje del usuario."""
import json
import os
import re

COSTE = float(os.environ.get("LLM_FALSO_COSTE", "0.001"))
# Comportamiento de cada juez, configurable por entorno: "acuerdo" (3/3 directa), "dos" (2 de 3), "indirecta".
MODO = os.environ.get("LLM_FALSO_MODO", "acuerdo")
FALLA_JUEZ = os.environ.get("LLM_FALSO_FALLA", "")   # modelo que devuelve basura


def _resp(obj):
    return {"choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}], "usage": {"cost": COSTE}}


def transporte(body):
    modelo = body["model"]
    usuario = body["messages"][1]["content"]
    if "FRAGMENTO:" in usuario:                       # extracción de promesas
        promesas = []
        for trozo in usuario.split("PROMESA:")[1:]:      # el bloque llega en una sola línea
            texto = trozo.split(" Hemos")[0].strip()
            if texto:
                promesas.append({"promesa": texto, "cita": texto, "tema": "Vivienda" if "alquiler" in texto else "Instituciones y calidad democrática",
                                 "procedimental": "real decreto" in texto.lower()})
        return _resp({"promesas": promesas})
    if FALLA_JUEZ and modelo == FALLA_JUEZ:
        return {"choices": [{"message": {"content": "no es json"}}], "usage": {"cost": COSTE}}
    ids = re.findall(r"\[chunk_id=(\d+)\]", usuario)
    partidos = re.findall(r"Promesas del programa electoral de ([^:]+):", usuario)
    if not ids:
        return _resp({"resumen": "", "que_cambia": "", "matches": []})
    fuerza = "directa"
    if MODO == "indirecta" or (MODO == "dos" and modelo == "google/gemini-2.5-flash-lite"):
        fuerza = "indirecta" if MODO == "indirecta" else None
    veredicto = None if fuerza is None else "cumple"
    return _resp({"resumen": "r", "que_cambia": "q", "matches": [
        {"party": partidos[0], "chunk_id": int(ids[0]), "promesa": "p", "veredicto": veredicto, "fuerza": fuerza}]})
