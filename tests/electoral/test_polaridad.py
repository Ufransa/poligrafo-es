"""El juez solo dice si la promesa está a favor o en contra de la iniciativa; el veredicto lo calcula el código.

Motivo (revisión del 2026-10-07): 4 de 11 «incumple» eran al revés. Vox prometió suprimir las oficinas de la
Agenda 2030 y votó No a impulsarla, y el juez lo daba como incumplimiento.
"""
import os
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), "LLM_FALSO_TODOS": "1", **extra}


def _cargar(cli, zips, **env):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env(**env))
    cli("extraer", env=_env(**env))
    cli("juzgar", "--k", "3", env=_env(**env))
    return cli("exportar")


def _veredictos(datos):
    tipos = {v["id"]: v for v in datos["votaciones"]}
    return [(tipos[c["votacion_id"]], c) for c in datos["cruces"] if c["nivel"] == "veredicto"]


def test_promesa_en_contra_y_voto_no_es_cumplir(cli, zips):
    pares = [(v, c) for v, c in _veredictos(_cargar(cli, zips, LLM_FALSO_POSTURA="en_contra"))
             if v["subtipo"] == "normal" and c["voto"] == "No"]
    assert pares and all(c["veredicto"] == "cumple" for _, c in pares)


def test_promesa_en_contra_y_voto_si_es_incumplir(cli, zips):
    datos = _cargar(cli, zips, LLM_FALSO_POSTURA="en_contra")
    tipos = {v["id"]: v for v in datos["votaciones"]}
    pares = [(tipos[c["votacion_id"]], c) for c in datos["cruces"]]
    pares = [(v, c) for v, c in pares
             if v["subtipo"] == "normal" and c["voto"] == "Sí"]
    assert pares and all(c["veredicto"] == "incumple" for _, c in pares)


def test_en_una_devolucion_votar_no_es_apoyar_la_ley(cli, zips):
    pares = [(v, c) for v, c in _veredictos(_cargar(cli, zips, LLM_FALSO_POSTURA="a_favor"))
             if v["subtipo"] == "devolucion" and c["voto"] == "No"]
    assert pares and all(c["veredicto"] == "cumple" for _, c in pares)


def test_una_abstencion_nunca_da_veredicto(cli, zips):
    datos = _cargar(cli, zips)
    assert datos["cruces"], "sin cruces la prueba no mide nada"
    assert not [c for c in datos["cruces"] if c["voto"] == "Abstención"]


def test_un_texto_alternativo_no_se_juzga(cli, zips):
    datos = _cargar(cli, zips)
    alternativos = {v["id"] for v in datos["votaciones"] if v["subtipo"] == "texto_alternativo"}
    assert datos["cruces"], "sin cruces la prueba no mide nada"
    assert alternativos and not [c for c in datos["cruces"] if c["votacion_id"] in alternativos]


def test_el_juez_no_ve_como_voto_cada_partido(cli, zips):
    """Si el juez viera el voto, podría acomodar la postura al voto. El falso devuelve basura si lo ve."""
    datos = _cargar(cli, zips, LLM_FALSO_FALLA_SI_VE_VOTO="1")
    assert datos["cruces"]


def test_en_una_devolucion_el_juez_solo_ve_el_proyecto(cli, zips):
    """Si ve la enmienda, la confunde con la iniciativa y da la postura al revés (medido con deepseek)."""
    pares = [(v, c) for v, c in _veredictos(_cargar(cli, zips, LLM_FALSO_FALLA_SI_VE_DEVOLUCION="1"))
             if v["subtipo"] == "devolucion"]
    assert pares
