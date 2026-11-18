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


def test_un_pdf_local_puede_enlazar_a_su_url_oficial(cli):
    # Webs que bloquean a los robots (Incapsula, 403): se baja a mano y se enlaza la fuente oficial, no file:///.
    oficial = "https://partido.example/programa-2026.pdf"
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), "--url", oficial, env=_env())
    cli("extraer", env=_env())
    psoe = [p for p in cli("exportar")["promesas"] if p["partido"] == "PSOE"]
    assert psoe and all(p["url_programa_pagina"].startswith(oficial + "#page=") for p in psoe)


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


def test_cada_partido_tiene_programa_de_2026_o_el_motivo(cli):
    partidos = cli("exportar")["partidos"]
    for p in partidos:
        assert bool(p.get("programa_2026")) != bool(p.get("sin_programa_2026")), p["id"]
    podemos = next(p for p in partidos if p["id"] == "Podemos")
    assert podemos["sin_programa_2026"] == "Solo publica un manifiesto breve, sin propuestas concretas."
    assert podemos["url_sin_programa_2026"] == "https://pazcasaytrabajo.es/"


def test_el_contrato_lleva_la_lista_de_temas(cli):
    meta = cli("exportar")["meta"]
    assert meta["version_contrato"] == "1.4.0"
    assert len(meta["temas"]) == 17 and meta["temas"][0] == "Vivienda"


def test_los_resumenes_de_2026_salen_en_castellano_aunque_el_programa_no_lo_este(cli):
    # Revisión del 2026-11-17: ~70 resúmenes de ERC, BNG y Compromís salían en catalán o gallego.
    env = _env(LLM_FALSO_CATALAN="1")
    cli("ingest-programa", "2026", "ERC", str(FIX / "programa_prueba.pdf"), env=env)
    cli("extraer", env=env)
    erc = [p for p in cli("exportar")["promesas"] if p["partido"] == "ERC"]
    assert erc and not any("habitatge" in p["texto"] for p in erc)
    assert any("vivienda" in p["texto"] for p in erc)
    assert all("habitatge" not in p["cita"] for p in erc)          # la cita sigue siendo literal
