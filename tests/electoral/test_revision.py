"""Pruebas de los hallazgos de la revisión final (2026-10-07)."""
import os
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def _votacion(datos, vid):
    return next(v for v in datos["votaciones"] if v["id"] == vid)


# --- Hallazgo 1: votaciones parciales (enmiendas, puntos sueltos) ---

def test_votar_no_a_una_enmienda_no_es_cambiar_de_postura_sobre_la_ley(cli, zips):
    cli("descargar", "--zips", zips)
    datos = cli("exportar")
    assert _votacion(datos, "101-1")["subtipo"] == "parcial"
    for partido in ("PSOE", "Sumar"):
        pares = datos["coherencia"].get(partido, [])
        assert not [p for p in pares if "101-1" in (p["a_favor"], p["en_contra"])], partido


def test_puntos_sueltos_de_una_mocion_no_son_cambios_de_postura(cli, zips):
    cli("descargar", "--zips", zips)
    datos = cli("exportar")
    ids = {"101-6", "101-8", "164-13", "164-17"}
    for partido, pares in datos["coherencia"].items():
        assert not [p for p in pares if {p["a_favor"], p["en_contra"]} <= ids], partido


def test_las_votaciones_parciales_no_se_juzgan(cli, zips):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("juzgar", "--k", "3", env=_env())
    datos = cli("exportar")
    parciales = {v["id"] for v in datos["votaciones"] if v["subtipo"] == "parcial"}
    assert parciales and not [c for c in datos["cruces"] if c["votacion_id"] in parciales]


# --- Hallazgo 3: una enmienda aprobada no es una ley en el BOE ---

def test_una_enmienda_aprobada_no_aparece_en_gobierno_ni_enlaza_el_boe(cli, zips, tmp_path):
    import json
    cli("descargar", "--zips", zips)
    clave = _votacion(cli("exportar"), "101-20")["clave_iniciativa"]
    boe = tmp_path / "boe.json"
    boe.write_text(json.dumps({clave: "BOE-A-2025-00001"}), encoding="utf-8")   # la ley sí está en el BOE
    cli("fuentes", "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(boe))
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("juzgar", "--k", "3", env=_env())
    datos = cli("exportar")
    assert _votacion(datos, "101-20")["url_boe"] is None
    assert not [g for g in datos["gobierno"].get("PSOE", []) if g["votacion_id"] == "101-20"]


# --- Hallazgo 2: las ausencias no son votos ---

def test_una_ausencia_no_convierte_a_un_partido_en_dividido(cli, zips):
    cli("descargar", "--zips", zips)
    assert _votacion(cli("exportar"), "101-1")["votos"]["ERC"]["dividido"] is False


def test_un_partido_que_no_vota_no_aparece_como_si_hubiera_votado(cli, zips):
    cli("descargar", "--zips", zips)
    for v in cli("exportar")["votaciones"]:
        assert all(x["voto"] != "No vota" for x in v["votos"].values()), v["id"]
