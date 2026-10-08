# tests/electoral/test_programas.py
import os
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def test_cada_promesa_lleva_cita_pagina_y_enlace_a_esa_pagina(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    datos = cli("exportar")
    psoe = [p for p in datos["promesas"] if p["partido"] == "PSOE"]
    assert len(psoe) == 2
    alquiler = next(p for p in psoe if "alquiler" in p["texto"])
    assert alquiler["pagina"] == 1 and alquiler["cita"]
    assert alquiler["url_programa_pagina"].endswith("#page=1")


def test_las_promesas_de_procedimiento_no_se_exportan(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    assert not any("real decreto" in p["texto"].lower() for p in cli("exportar")["promesas"])


def test_el_reparto_por_temas_suma_cien(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    temas = cli("exportar")["temas"]["PSOE"]["2023"]
    assert abs(sum(temas.values()) - 100) < 0.5


def test_un_partido_sin_programa_aparece_con_su_motivo_y_sin_promesas(cli):
    datos = cli("exportar")
    podemos = next(p for p in datos["partidos"] if p["id"] == "Podemos")
    assert "Sumar" in podemos["sin_programa"]
    assert not [p for p in datos["promesas"] if p["partido"] == "Podemos"]


def test_si_se_agota_el_presupuesto_la_extraccion_se_reanuda_sin_duplicar(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", "--tope", "0", env=_env())          # tope 0: se para antes de la primera llamada
    assert cli("exportar")["promesas"] == []
    cli("extraer", env=_env())
    textos = [p["texto"] for p in cli("exportar")["promesas"]]
    assert len(textos) == len(set(textos)) == 2
