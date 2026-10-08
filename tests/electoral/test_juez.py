# tests/electoral/test_juez.py
import os
import sqlite3
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def _preparar(cli, zips, **env):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env(**env))
    cli("extraer", env=_env(**env))


def test_tres_jueces_de_acuerdo_con_relacion_directa_dan_veredicto(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env())
    cruces = cli("exportar")["cruces"]
    # Solo «cumple»: un «incumple» necesita además revisión a mano (test_revision_manual).
    cumple = [c for c in cruces if c["partido"] == "PSOE" and not c["dividido"] and c["veredicto"] == "cumple"]
    assert cumple and all(c["nivel"] == "veredicto" for c in cumple)
    assert all(len(c["jueces"]) == 3 for c in cruces)


def test_dos_de_tres_se_quedan_en_juzga_tu(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env(LLM_FALSO_MODO="dos"))
    cruces = cli("exportar")["cruces"]
    assert cruces and {c["nivel"] for c in cruces} == {"juzga_tu"}


def test_relacion_indirecta_nunca_es_veredicto(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env(LLM_FALSO_MODO="indirecta"))
    assert all(c["nivel"] == "juzga_tu" for c in cli("exportar")["cruces"])


def test_las_votaciones_de_tramite_no_se_juzgan(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env())
    datos = cli("exportar")
    tramite = {v["id"] for v in datos["votaciones"] if v["excluida_tramite"]}
    assert not [c for c in datos["cruces"] if c["votacion_id"] in tramite]


def test_un_partido_que_vota_dividido_nunca_recibe_veredicto(cli, zips):
    _preparar(cli, zips)
    conn = sqlite3.connect(cli.db)
    conn.execute("UPDATE votos_partido SET dividido = 1 WHERE partido = 'PSOE'")
    conn.commit(); conn.close()
    cli("juzgar", "--k", "3", env=_env())
    assert all(c["nivel"] == "juzga_tu" for c in cli("exportar")["cruces"] if c["partido"] == "PSOE")


def test_un_juez_que_falla_deja_el_expediente_pendiente_y_se_reanuda(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env(LLM_FALSO_FALLA="openai/gpt-5-mini"))
    assert cli("exportar")["cruces"] == []                     # nada a medio juzgar
    cli("juzgar", "--k", "3", env=_env())
    cruces = cli("exportar")["cruces"]
    claves = [(c["votacion_id"], c["promesa_id"]) for c in cruces]
    assert cruces and len(claves) == len(set(claves))


def test_si_se_agota_el_presupuesto_no_se_publica_nada_a_medias(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", "--tope", "0.002", env=_env(LLM_FALSO_COSTE="0.001"))
    parcial = cli("exportar")["cruces"]
    cli("juzgar", "--k", "3", env=_env())
    completo = cli("exportar")["cruces"]
    assert len(completo) >= len(parcial)
    assert all(len(c["jueces"]) == 3 for c in parcial + completo)
