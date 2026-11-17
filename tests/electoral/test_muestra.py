import os
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def test_la_muestra_para_fran_trae_n_veredictos_con_su_cita_y_su_casilla(cli, zips, tmp_path):
    env = {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py")}
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=env)
    cli("extraer", env=env)
    cli("juzgar", "--k", "3", env=env)
    salida = tmp_path / "muestra.md"
    cli("muestra", "--n", "3", "--salida", str(salida))
    texto = salida.read_text(encoding="utf-8")
    assert texto.count("\n## ") == 3
    assert texto.count("- [ ] De acuerdo con") == 3
    assert "Cita literal (pág." in texto and "#page=" in texto


def test_la_muestra_de_promesas_es_reproducible_y_lleva_cita_y_pagina(cli, tmp_path):
    env = {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py")}
    cli("ingest-programa", "2026", "PSOE", str(FIX / "programa_prueba.pdf"), env=env)
    cli("extraer", env=env)
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    cli("muestra-promesas", "--anio", "2026", "--n", "2", "--salida", str(a))
    cli("muestra-promesas", "--anio", "2026", "--n", "2", "--salida", str(b))
    texto = a.read_text(encoding="utf-8")
    assert texto == b.read_text(encoding="utf-8")
    assert texto.count("\n## ") == 2 and "#page=" in texto and "- [ ] Bien" in texto
