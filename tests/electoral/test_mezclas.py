# tests/electoral/test_mezclas.py
"""Normas que mezclan asuntos (ómnibus) y enmiendas sueltas del Senado: el voto puede deberse a otra parte
(Fran, 2026-10-31)."""
import json
import os
import sqlite3
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"
ID_BOE = "BOE-A-2026-2548"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def _juzgado(cli, zips):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("juzgar", "--k", "3", env=_env())


def _firme(datos):
    """Una votación con un «cumple» firme del PSOE."""
    return next(c["votacion_id"] for c in datos["cruces"]
                if c["partido"] == "PSOE" and c["nivel"] == "veredicto" and c["veredicto"] == "cumple")


def _cambiar(cli, vid, **campos):
    conn = sqlite3.connect(cli.db)
    for k, val in campos.items():
        conn.execute(f"UPDATE votaciones SET {k} = ? WHERE id = ?", (val, vid))
    conn.commit()
    conn.close()


def test_una_enmienda_suelta_del_senado_nunca_es_veredicto(cli, zips):
    _juzgado(cli, zips)
    vid = _firme(cli("exportar"))
    _cambiar(cli, vid, tipo="Enmiendas del Senado.",
             expediente="Proposición de Ley para la mejora de la protección de las personas donantes en vivo.\nVotación de la enmienda.")
    cruces = [c for c in cli("exportar")["cruces"] if c["votacion_id"] == vid]
    assert cruces and all(c["nivel"] == "juzga_tu" for c in cruces)


def test_la_votacion_de_conjunto_tras_el_senado_si_puede_ser_veredicto(cli, zips):
    _juzgado(cli, zips)
    vid = _firme(cli("exportar"))
    _cambiar(cli, vid, tipo="Enmiendas del Senado.", expediente="Votación de conjunto del Proyecto de Ley Orgánica de vivienda.")
    assert any(c["nivel"] == "veredicto" for c in cli("exportar")["cruces"] if c["votacion_id"] == vid)


def test_un_titulo_que_confiesa_la_mezcla_lleva_nota(cli, zips):
    _juzgado(cli, zips)
    vid = _firme(cli("exportar"))
    _cambiar(cli, vid, expediente="Real Decreto-ley 3/2026, de 3 de febrero, para la revalorización de las pensiones "
                                  "públicas y otras medidas urgentes en materia de Seguridad Social.")
    vots = {v["id"]: v for v in cli("exportar")["votaciones"]}
    assert "título" in vots[vid]["mezcla"]["motivo"]
    assert all(v["mezcla"] is None for v in vots.values() if "otras medidas" not in v["expediente"])


def _con_norma(cli, zips, tmp_path, mezcla):
    _juzgado(cli, zips)
    vid = _firme(cli("exportar"))
    _cambiar(cli, vid, clave_iniciativa="real decreto-ley 3/2026", es_convalidacion=1,
             expediente="Real Decreto-ley 3/2026, de 3 de febrero, de revalorización de las pensiones públicas.")
    boe = tmp_path / "boe.json"
    boe.write_text(json.dumps({"real decreto-ley 3/2026": ID_BOE}), encoding="utf-8")
    texto = tmp_path / "texto.json"
    texto.write_text(json.dumps({ID_BOE: [
        "Artículo 1. Revalorización de las pensiones. Las pensiones se revalorizan un 2,8 %.",
        "Disposición final primera. Cesión de un palacio en París al Gobierno Vasco."]}), encoding="utf-8")
    env = _env(ELECTORAL_BOE_TEXTO_FALSO=str(texto), LLM_FALSO_MEZCLA="1" if mezcla else "")
    salida = cli("mezclas", "--boe", str(boe), env=env)
    return vid, salida, boe, env


def test_el_modelo_detecta_lo_que_no_tiene_que_ver_con_el_titulo(cli, zips, tmp_path):
    vid, salida, _, _ = _con_norma(cli, zips, tmp_path, mezcla=True)
    v = next(v for v in cli("exportar")["votaciones"] if v["id"] == vid)
    assert "palacio" in v["mezcla"]["motivo"]
    assert "1 de 1 normas mezclan asuntos" in salida


def test_si_el_modelo_no_ve_mezcla_no_hay_nota(cli, zips, tmp_path):
    vid, salida, _, _ = _con_norma(cli, zips, tmp_path, mezcla=False)
    assert next(v for v in cli("exportar")["votaciones"] if v["id"] == vid)["mezcla"] is None
    assert "0 de 1 normas mezclan asuntos" in salida


def test_una_norma_ya_mirada_no_se_vuelve_a_pagar(cli, zips, tmp_path):
    _, _, boe, env = _con_norma(cli, zips, tmp_path, mezcla=True)
    cli("mezclas", "--boe", str(boe), env=env)
    gasto = [r[0] for r in sqlite3.connect(cli.db).execute("SELECT usd FROM gasto WHERE paso = 'mezclas' ORDER BY id")]
    assert gasto[0] > 0 and gasto[1] == 0
