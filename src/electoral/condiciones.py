# src/electoral/condiciones.py
"""Condiciones jurídicas de una propuesta. Salen siempre de config/condiciones.json (escrita a mano y revisada por
Fran); el modelo solo elige claves de materia."""
import json
from pathlib import Path

CAMPOS = ("etiqueta", "explicacion", "norma", "url")


def cargar(raiz: Path) -> dict:
    return json.loads((raiz / "config" / "condiciones.json").read_text(encoding="utf-8"))


def resolver(materias: list[str], coste: bool, tabla: dict) -> dict:
    """Condiciones ordenadas de menos a más exigente; una clave desconocida no produce condición."""
    conocidas = sorted((tabla["materias"][m] | {"clave": m} for m in dict.fromkeys(materias) if m in tabla["materias"]),
                       key=lambda c: c["nivel"])
    condiciones = [{"clave": c["clave"], **{k: c[k] for k in CAMPOS}, "inviable": c["inviable"]} for c in conocidas]
    if coste:
        condiciones.append({"clave": "coste", **{k: tabla["coste"][k] for k in CAMPOS}, "inviable": False})
    return {"condiciones": condiciones, "inviable": any(c["inviable"] for c in condiciones)}
