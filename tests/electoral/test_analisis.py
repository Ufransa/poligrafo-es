# tests/electoral/test_analisis.py
import json
import os
import sqlite3
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def test_un_partido_que_cambia_de_postura_en_la_misma_ley_aparece_en_coherencia(cli, zips):
    cli("descargar", "--zips", zips)
    conn = sqlite3.connect(cli.db)
    clave = conn.execute("SELECT clave_iniciativa FROM votaciones WHERE subtipo = 'devolucion' LIMIT 1").fetchone()[0]
    vid = conn.execute("SELECT id FROM votaciones WHERE subtipo = 'devolucion' LIMIT 1").fetchone()[0]
    # Una votación final inventada de la misma ley en la que Vox vota Sí tras haber pedido devolverla
    conn.execute("INSERT INTO votaciones (id, fecha, sesion, numero, tipo, subtipo, es_convalidacion, expediente, texto_subgrupo, clave_iniciativa, resultado, a_favor, en_contra, abstenciones, excluida_tramite, url_xml, url_sesion) "
                 "VALUES ('999-1', '2025-12-01', 999, 1, 'Dictámenes de Comisiones sobre iniciativas legislativas.', 'normal', 0, 'x', '', ?, 'aprobada', 200, 100, 0, 0, 'u', 'u')", (clave,))
    conn.execute("INSERT INTO votos_partido VALUES ('999-1', 'Vox', 'Sí', 0)")
    conn.commit(); conn.close()
    pares = cli("exportar")["coherencia"].get("Vox", [])
    assert any(p["clave_iniciativa"] == clave and vid in (p["a_favor"], p["en_contra"]) for p in pares)


def test_un_decreto_ley_derogado_no_sale_en_lo_que_hizo_gobernando(cli, zips):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("juzgar", "--k", "3", env=_env())
    assert cli("exportar")["gobierno"].get("PSOE"), "sin decretos convalidados la prueba no mide nada"
    conn = sqlite3.connect(cli.db)
    conn.execute("UPDATE votaciones SET resultado = 'rechazada' WHERE es_convalidacion = 1")
    conn.commit(); conn.close()
    gob = cli("exportar")["gobierno"].get("PSOE", [])
    rechazadas = {v["id"] for v in cli("exportar")["votaciones"] if v["resultado"] == "rechazada"}
    assert not [g for g in gob if g["votacion_id"] in rechazadas]


def test_solo_los_partidos_de_gobierno_tienen_bloque_de_gobierno(cli, zips):
    cli("descargar", "--zips", zips)
    gob = cli("exportar")["gobierno"]
    assert set(gob) <= {"PSOE", "Sumar", "Podemos"}


def test_cada_cifra_de_finanzas_lleva_su_pagina_y_su_informe(cli):
    fin = cli("exportar")["finanzas"]
    assert fin
    for partido, f in fin.items():
        assert f["url_informe"].startswith("https://")
        assert f["pagina"] > 0 and f["gasto_justificado_eur"] > 0
