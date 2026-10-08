"""Un «incumple» solo se afirma si una persona lo ha revisado (decisión del 2026-10-07).

Motivo: el juez solo ve el título de la iniciativa. Basta para saber qué ley se toca, no para qué; en la
revisión, 5 de 11 «incumple» eran la misma ley con otro objetivo o la iniciativa leída al revés.
"""
import json
import os
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env():
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), "LLM_FALSO_TODOS": "1",
            "LLM_FALSO_POSTURA": "en_contra"}


def _cargar(cli, zips, *extra):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("juzgar", "--k", "3", env=_env())
    return cli("exportar", *extra)


def test_un_incumple_sin_revisar_se_publica_como_juzga_tu(cli, zips, tmp_path):
    vacia = tmp_path / "revision.json"
    vacia.write_text('{"confirmados": []}', encoding="utf-8")
    incumple = [c for c in _cargar(cli, zips, "--revision", str(vacia))["cruces"] if c["veredicto"] == "incumple"]
    assert incumple and all(c["nivel"] == "juzga_tu" for c in incumple)


def test_un_incumple_confirmado_a_mano_es_veredicto_y_lo_dice(cli, zips, tmp_path):
    vacia = tmp_path / "vacia.json"
    vacia.write_text('{"confirmados": []}', encoding="utf-8")
    datos = _cargar(cli, zips, "--revision", str(vacia))
    # Candidato: un «incumple» que los jueces dieron unánime y directo (el falso siempre da «directa»).
    elegido = next(c for c in datos["cruces"] if c["veredicto"] == "incumple" and not c["dividido"])
    revision = tmp_path / "revision.json"
    revision.write_text(json.dumps({"confirmados": [{k: elegido[k] for k in ("votacion_id", "promesa_id", "partido")}
                                                    | {"veredicto": "incumple"}]}), encoding="utf-8")
    cruces = cli("exportar", "--revision", str(revision))["cruces"]
    clave = lambda c: (c["votacion_id"], c["promesa_id"], c["partido"])
    confirmados = [c for c in cruces if c["veredicto"] == "incumple" and c["nivel"] == "veredicto"]
    assert [clave(c) for c in confirmados] == [clave(elegido)]
    assert confirmados[0]["revisado_a_mano"] is True
    assert all(c["revisado_a_mano"] is False for c in cruces if clave(c) != clave(elegido))
