# tests/electoral/test_test_ciegas.py
"""Test a ciegas: selección, resumen neutral, neutralidad, revisión de Fran y exportación.
Ver docs/superpowers/specs/2026-10-30-test-a-ciegas-design.md."""
import json
import os
import sqlite3
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def _filas(db, sql, *args):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    filas = [dict(r) for r in conn.execute(sql, args)]
    conn.close()
    return filas


def _sembrar(cli, anio=2023, partido="PSOE", promesas=()):
    """Mete promesas ya extraídas: (texto, tema, procedimental). La extracción tiene sus propias pruebas."""
    cli("exportar")                                    # crea la base con su esquema
    conn = sqlite3.connect(cli.db)
    cur = conn.execute("INSERT INTO bloques (partido, anio, pagina, texto, url_programa, extraido) VALUES (?,?,?,?,?,1)",
                       (partido, anio, 1, " ".join(t for t, _, _ in promesas), "https://ejemplo.es/programa.pdf"))
    for texto, tema, proc in promesas:
        conn.execute("INSERT INTO promesas (bloque_id, partido, anio, pagina, texto, cita, tema, procedimental) "
                     "VALUES (?,?,?,?,?,?,?,?)", (cur.lastrowid, partido, anio, 1, texto, texto, tema, proc))
    conn.commit()
    conn.close()


VIVIENDA = [(f"Construiremos {n} mil viviendas públicas en alquiler.", "Vivienda", 0) for n in range(1, 6)]


def test_la_seleccion_respeta_temas_y_tope_por_partido(cli):
    _sembrar(cli, promesas=VIVIENDA + [("Bajaremos el IRPF a las rentas bajas.", "Fiscalidad", 0)])
    cli("test-seleccionar", "--anio", "2023", "--temas", "Vivienda", env=_env(LLM_FALSO_SELECCION="todos"))
    filas = _filas(cli.db, "SELECT partido, tema, COUNT(*) n FROM test_propuestas GROUP BY partido, tema")
    assert filas == [{"partido": "PSOE", "tema": "Vivienda", "n": 3}]


def test_la_seleccion_no_coge_promesas_de_procedimiento(cli):
    _sembrar(cli, promesas=[("Limitaremos el uso del real decreto-ley en vivienda.", "Vivienda", 1),
                            ("Construiremos viviendas públicas.", "Vivienda", 0)])
    cli("test-seleccionar", "--anio", "2023", "--temas", "Vivienda", env=_env(LLM_FALSO_SELECCION="todos"))
    textos = [f["texto"] for f in _filas(cli.db, "SELECT p.texto FROM test_propuestas t JOIN promesas p ON p.id = t.promesa_id")]
    assert textos == ["Construiremos viviendas públicas."]


def test_un_id_que_el_modelo_se_inventa_no_se_selecciona(cli):
    _sembrar(cli, promesas=VIVIENDA[:2])
    cli("test-seleccionar", "--anio", "2023", "--temas", "Vivienda", env=_env(LLM_FALSO_SELECCION="inventa"))
    ids = {p["id"] for p in _filas(cli.db, "SELECT id FROM promesas")}
    assert {f["promesa_id"] for f in _filas(cli.db, "SELECT promesa_id FROM test_propuestas")} <= ids


def test_sin_presupuesto_se_para_y_se_reanuda_sin_duplicar(cli):
    _sembrar(cli, promesas=VIVIENDA)
    cli("test-seleccionar", "--anio", "2023", "--temas", "Vivienda", "--tope", "0", env=_env())
    assert _filas(cli.db, "SELECT * FROM test_propuestas") == []
    assert _filas(cli.db, "SELECT paso FROM gasto") == [{"paso": "test-seleccionar"}]
    cli("test-seleccionar", "--anio", "2023", "--temas", "Vivienda", env=_env())
    cli("test-seleccionar", "--anio", "2023", "--temas", "Vivienda", env=_env())
    ids = [f["promesa_id"] for f in _filas(cli.db, "SELECT promesa_id FROM test_propuestas")]
    assert len(ids) == len(set(ids)) == 3
