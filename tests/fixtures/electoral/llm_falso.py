# tests/fixtures/electoral/llm_falso.py
"""LLM falso para las pruebas. Reglas por contenido del mensaje del usuario."""
import json
import os
import re

COSTE = float(os.environ.get("LLM_FALSO_COSTE", "0.001"))
# Comportamiento de cada juez, configurable por entorno: "acuerdo" (3/3 directa), "dos" (2 de 3), "indirecta".
MODO = os.environ.get("LLM_FALSO_MODO", "acuerdo")
FALLA_JUEZ = os.environ.get("LLM_FALSO_FALLA", "")   # modelo que devuelve basura
PARTIDO_EQUIVOCADO = os.environ.get("LLM_FALSO_PARTIDO", "")   # el juez atribuye la promesa a otro partido
EXCEPCION = os.environ.get("LLM_FALSO_EXCEPCION", "")        # fallo de red al llamar a los jueces
POSTURA = os.environ.get("LLM_FALSO_POSTURA", "a_favor")    # postura de la promesa frente a la iniciativa


def _resp(obj):
    return {"choices": [{"message": {"content": json.dumps(obj, ensure_ascii=False)}}], "usage": {"cost": COSTE}}


def transporte(body):
    modelo = body["model"]
    usuario = body["messages"][1]["content"]
    if "FRAGMENTO:" in usuario:                       # extracción de promesas
        promesas = []
        for trozo in usuario.split("PROMESA:")[1:]:      # el bloque llega en una sola línea
            texto = re.sub(r"\[\[p\. \d+\]\]", "", trozo.split(" Hemos")[0]).strip()
            if texto:
                promesas.append({"promesa": texto, "cita": texto, "tema": "Vivienda" if "alquiler" in texto else "Instituciones y calidad democrática",
                                 "procedimental": "real decreto" in texto.lower()})
        if os.environ.get("LLM_FALSO_CITA_FALSA"):
            promesas.append({"promesa": "Promesa inventada", "cita": "Esta frase no aparece en ningún programa", "tema": "Vivienda", "procedimental": False})
        return _resp({"promesas": promesas})
    if EXCEPCION and "FRAGMENTO:" not in usuario:
        import requests
        raise requests.ConnectionError("red caída (simulada)")
    if os.environ.get("LLM_FALSO_FALLA_SI_VE_VOTO") and "SENTIDO DE VOTO" in usuario:
        return {"choices": [{"message": {"content": "no es json"}}], "usage": {"cost": COSTE}}
    if os.environ.get("LLM_FALSO_FALLA_SI_VE_DEVOLUCION") and "devoluci" in usuario.lower():
        return {"choices": [{"message": {"content": "no es json"}}], "usage": {"cost": COSTE}}
    if FALLA_JUEZ and modelo == FALLA_JUEZ:
        return {"choices": [{"message": {"content": "no es json"}}], "usage": {"cost": COSTE}}
    ids = re.findall(r"\[chunk_id=(\d+)\]", usuario)
    partidos = re.findall(r"Promesas del programa electoral de ([^:]+):", usuario)
    if os.environ.get("LLM_FALSO_TODOS"):          # un cruce por cada candidato, con su partido
        pares, actual = [], None
        for linea in usuario.split("\n"):
            m = re.match(r"Promesas del programa electoral de ([^:]+):", linea.strip())
            if m:
                actual = m.group(1)
            m = re.match(r"\[chunk_id=(\d+)\]", linea.strip())
            if m:
                pares.append((actual, int(m.group(1))))
        return _resp({"matches": [{"party": p, "chunk_id": i, "postura": POSTURA, "fuerza": "directa"} for p, i in pares]})
    if not ids:
        return _resp({"resumen": "", "que_cambia": "", "matches": []})
    fuerza = "directa"
    if MODO == "indirecta" or (MODO == "dos" and modelo == "google/gemini-2.5-flash-lite"):
        fuerza = "indirecta" if MODO == "indirecta" else None
    postura = None if fuerza is None else POSTURA
    return _resp({"resumen": "r", "que_cambia": "q", "matches": [
        {"party": PARTIDO_EQUIVOCADO or partidos[0], "chunk_id": int(ids[0]), "postura": postura, "fuerza": fuerza}]})
