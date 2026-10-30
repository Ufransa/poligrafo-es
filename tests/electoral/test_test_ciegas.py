# tests/electoral/test_test_ciegas.py
"""Test a ciegas: selección, resumen neutral, neutralidad, revisión de Fran y exportación.
Ver docs/superpowers/specs/2026-10-30-test-a-ciegas-design.md."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FIX = RAIZ / "tests" / "fixtures" / "electoral"


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


def _seleccionadas(cli, promesas=VIVIENDA[:2]):
    _sembrar(cli, promesas=promesas)
    cli("test-seleccionar", "--anio", "2023", "--temas", "Vivienda", env=_env())


def test_cada_propuesta_seleccionada_queda_resumida(cli):
    _seleccionadas(cli)
    cli("test-resumir", "--anio", "2023", env=_env())
    filas = _filas(cli.db, "SELECT resumen, concreta, materias, coste FROM test_propuestas")
    assert len(filas) == 2
    assert all(f["resumen"].startswith("Resumen neutral:") and f["concreta"] == 1 and f["coste"] == 0 for f in filas)


def test_una_materia_que_no_esta_en_la_tabla_se_descarta(cli):
    _seleccionadas(cli)
    cli("test-resumir", "--anio", "2023", env=_env(LLM_FALSO_MATERIAS='["ley_ordinaria", "inventada"]'))
    assert all(json.loads(f["materias"]) == ["ley_ordinaria"] for f in _filas(cli.db, "SELECT materias FROM test_propuestas"))


def test_resumir_dos_veces_no_vuelve_a_pagar(cli):
    _seleccionadas(cli)
    cli("test-resumir", "--anio", "2023", env=_env())
    cli("test-resumir", "--anio", "2023", env=_env())
    gasto = _filas(cli.db, "SELECT usd FROM gasto WHERE paso = 'test-resumir' ORDER BY id")
    assert gasto[0]["usd"] > 0 and gasto[1]["usd"] == 0


def _resumidas(cli):
    _seleccionadas(cli)
    cli("test-resumir", "--anio", "2023", env=_env())


def test_si_el_adivino_acierta_se_reescribe_dos_veces_y_se_marca(cli):
    _resumidas(cli)
    salida = cli("test-neutralidad", "--anio", "2023", env=_env(LLM_FALSO_ADIVINA="acierta"))
    filas = _filas(cli.db, "SELECT reescrituras, delata, adivinado FROM test_propuestas")
    assert filas and all(f["reescrituras"] == 2 and f["delata"] == 1 and f["adivinado"] == "PSOE" for f in filas)
    assert "acierto final: 2 de 2" in salida


def test_si_el_adivino_falla_no_se_toca(cli):
    _resumidas(cli)
    salida = cli("test-neutralidad", "--anio", "2023", env=_env(LLM_FALSO_ADIVINA="falla"))
    assert all(f["reescrituras"] == 0 and f["delata"] == 0 for f in _filas(cli.db, "SELECT * FROM test_propuestas"))
    assert "acierto final: 0 de 2" in salida


def test_el_adivino_solo_ve_el_resumen(cli):
    _resumidas(cli)
    cli("test-neutralidad", "--anio", "2023", env=_env(LLM_FALSO_ADIVINA="falla", LLM_FALSO_FALLA_SI_VE_PROGRAMA="1"))
    assert all(f["adivinado"] == "PP" for f in _filas(cli.db, "SELECT adivinado FROM test_propuestas"))


def _revision(cli, tmp_path, anio="2023"):
    md = tmp_path / "revision.md"
    cli("test-revision", "--anio", anio, "--salida", str(md))
    return md


def _marcar(md, n, casilla, corregido=None):
    """Marca una casilla en la tarjeta n (1, 2, ...) del fichero de revisión, como haría Fran."""
    cabecera, *tarjetas = md.read_text(encoding="utf-8").split("\n## ")
    tarjetas[n - 1] = tarjetas[n - 1].replace(f"- [ ] {casilla}", f"- [x] {casilla}")
    if corregido:
        tarjetas[n - 1] = tarjetas[n - 1].replace("Resumen corregido:", f"Resumen corregido: {corregido}")
    md.write_text("\n## ".join([cabecera, *tarjetas]), encoding="utf-8")


def _aprobar(cli, md, tmp_path, anio="2023", ok=True):
    destino = tmp_path / "test_ciegas.json"
    cmd = [sys.executable, str(RAIZ / "electoral.py"), "test-aprobar", "--anio", anio, "--revision", str(md),
           "--destino", str(destino), "--db", str(cli.db)]
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert (r.returncode == 0) == ok, r.stderr
    return json.loads(destino.read_text(encoding="utf-8"))[anio] if ok else r.stderr


def test_la_revision_lleva_resumen_condiciones_y_cita(cli, tmp_path):
    _resumidas(cli)
    texto = _revision(cli, tmp_path).read_text(encoding="utf-8")
    assert texto.count("\n## ") == 2
    assert "**Condiciones:** Ley ordinaria" in texto and "Resumen neutral:" in texto and "**Cita (p. 1):**" in texto


def test_sin_marca_no_se_publica(cli, tmp_path):
    _resumidas(cli)
    assert _aprobar(cli, _revision(cli, tmp_path), tmp_path) == []


def test_publicar_y_descartar(cli, tmp_path):
    _resumidas(cli)
    md = _revision(cli, tmp_path)
    _marcar(md, 1, "Publicar")
    _marcar(md, 2, "Descartar")
    aprobadas = _aprobar(cli, md, tmp_path)
    assert len(aprobadas) == 1 and aprobadas[0]["revisado_por"] == "Fran" and aprobadas[0]["promesa_2023_id"] is None


def test_el_resumen_corregido_sustituye_al_del_modelo(cli, tmp_path):
    _resumidas(cli)
    md = _revision(cli, tmp_path)
    _marcar(md, 1, "Publicar", corregido="Texto que escribe Fran.")
    assert _aprobar(cli, md, tmp_path)[0]["resumen"] == "Texto que escribe Fran."


def test_publicar_y_descartar_a_la_vez_es_un_error(cli, tmp_path):
    _resumidas(cli)
    md = _revision(cli, tmp_path)
    _marcar(md, 1, "Publicar")
    _marcar(md, 1, "Descartar")
    assert "id=" in _aprobar(cli, md, tmp_path, ok=False)


def test_el_cruce_2023_solo_se_guarda_si_fran_lo_confirma(cli, zips, tmp_path):
    env = _env(LLM_FALSO_TODOS="1")
    cli("descargar", "--zips", zips)
    for anio in ("2023", "2026"):
        cli("ingest-programa", anio, "PSOE", str(FIX / "programa_prueba.pdf"), env=env)
    cli("extraer", env=env)
    cli("juzgar", "--k", "3", env=env)
    cli("test-seleccionar", "--anio", "2026", "--temas", "Vivienda", env=env)
    cli("test-resumir", "--anio", "2026", env=env)
    md = _revision(cli, tmp_path, "2026")
    assert "**Posible cruce 2023:**" in md.read_text(encoding="utf-8")
    _marcar(md, 1, "Publicar")
    assert _aprobar(cli, md, tmp_path, "2026")[0]["promesa_2023_id"] is None
    _marcar(md, 1, "El cruce 2023 es la misma promesa")
    assert isinstance(_aprobar(cli, md, tmp_path, "2026")[0]["promesa_2023_id"], int)
