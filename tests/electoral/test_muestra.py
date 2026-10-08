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
