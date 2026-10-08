# tests/electoral/test_contrato.py
import json
from pathlib import Path

import jsonschema

RAIZ = Path(__file__).resolve().parents[2]


def test_el_json_exportado_cumple_el_contrato_y_todo_cruce_apunta_a_algo_que_existe(cli, zips):
    cli("descargar", "--zips", zips)
    datos = cli("exportar")
    jsonschema.validate(datos, json.loads((RAIZ / "schema" / "datos.schema.json").read_text(encoding="utf-8")))
    ids_v = {v["id"] for v in datos["votaciones"]}
    ids_p = {p["id"] for p in datos["promesas"]}
    for c in datos["cruces"]:
        assert c["votacion_id"] in ids_v and c["promesa_id"] in ids_p


def test_un_json_que_rompe_el_contrato_no_se_escribe(cli, zips, tmp_path):
    import sqlite3
    import subprocess
    import sys
    cli("descargar", "--zips", zips)
    conn = sqlite3.connect(cli.db)
    conn.execute("UPDATE votaciones SET subtipo = 'inventado' WHERE rowid = 1")
    conn.commit(); conn.close()
    salida = tmp_path / "roto.json"
    r = subprocess.run([sys.executable, str(RAIZ / "electoral.py"), "exportar", "--db", str(cli.db), "--salida", str(salida)],
                       cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode != 0 and "ValidationError" in r.stderr
    assert not salida.exists()
