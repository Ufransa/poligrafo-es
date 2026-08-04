"""
End-to-end sobre el ZIP real de la sesión 192 (14/7/2026).
Regresión del fallo original: 56 votaciones producían 49 mensajes contradictorios
que decían que la ley de discapacidad fue RECHAZADA. Se aprobó, 179-33.
"""
import zipfile
from pathlib import Path

import pytest

from src.congreso import (parse_vote_xml, compute_resultado, classify_vote,
                          expediente_key, decode_vote_xml)
from src.db import (init_db, get_conn, insert_session, insert_vote, insert_vote_groups,
                    get_expedientes_for_digest, get_vote_groups)
from digest import format_expediente_block
from src.publisher import load_parties, load_parties_largo

FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "sesion192.zip"


@pytest.fixture
def db_sesion192(tmp_path):
    """Ingesta completa del ZIP real, sin LLM ni red."""
    db = tmp_path / "e2e.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 192, "20260714")
    with zipfile.ZipFile(FIXTURE_ZIP) as zf:
        for name in sorted(n for n in zf.namelist() if n.endswith(".xml")):
            # El XML del Congreso no es UTF-8: usar el mismo decodificador que producción.
            v = parse_vote_xml(decode_vote_xml(zf.read(name)))
            vid = insert_vote(
                conn, sid, v["numero_votacion"], v["titulo"], v["texto_expediente"],
                v["fecha"], categories=["social"],
                a_favor=v["a_favor"], en_contra=v["en_contra"],
                abstenciones=v["abstenciones"],
                resultado=compute_resultado(v["a_favor"], v["en_contra"]),
                titulo_subgrupo=v["titulo_subgrupo"], texto_subgrupo=v["texto_subgrupo"],
                clase=classify_vote(v["titulo_subgrupo"]),
                expediente_key=expediente_key(v["texto_expediente"]),
            )
            insert_vote_groups(conn, vid, v["group_votes"])
    yield conn
    conn.close()


def test_56_votaciones_producen_7_fichas(db_sesion192):
    assert len(get_expedientes_for_digest(db_sesion192)) == 7


def _ficha_discapacidad(conn):
    parties, largos = load_parties(), load_parties_largo()
    for exp in get_expedientes_for_digest(conn):
        if "discapacidad" not in exp["expediente_key"]:
            continue
        sus = dict(exp["sustantiva"])
        exp["sustantiva"] = sus
        exp["parciales"] = [dict(p) for p in exp["parciales"]]
        exp["groups"] = {g["grupo_code"]: {"voto": g["voto"], "divided": bool(g["divided"])}
                         for g in get_vote_groups(conn, sus["id"])}
        exp["matches"] = []
        return exp, format_expediente_block(exp, parties, largos)
    raise AssertionError("la ley de discapacidad no aparece en el digest")


def test_la_ley_de_discapacidad_sale_como_aprobada(db_sesion192):
    _, ficha = _ficha_discapacidad(db_sesion192)
    assert "APROBADA" in ficha
    assert "RECHAZADA" not in ficha
    assert "179 a favor / 33 en contra" in ficha


def test_la_ley_de_discapacidad_sale_en_una_sola_ficha(db_sesion192):
    fichas = [e for e in get_expedientes_for_digest(db_sesion192)
              if "discapacidad" in e["expediente_key"]]
    assert len(fichas) == 1


def test_las_49_parciales_no_generan_ficha_propia(db_sesion192):
    exp, ficha = _ficha_discapacidad(db_sesion192)
    assert len(exp["parciales"]) == 49
    assert "49 enmiendas" in ficha
    assert "Enmienda 270" not in ficha


def test_la_abstencion_del_pp_aparece_en_la_ficha(db_sesion192):
    _, ficha = _ficha_discapacidad(db_sesion192)
    assert "Abstención: PP" in ficha
    assert "En contra: Vox" in ficha


def test_todos_los_grupos_de_la_sesion_estan_mapeados(db_sesion192):
    """Un grupo sin mapear sale con su nombre largo entero y afea la ficha."""
    exp, _ = _ficha_discapacidad(db_sesion192)
    largos = load_parties_largo()
    sin_mapear = {p["titulo_subgrupo"] for p in exp["parciales"]
                  if p["titulo_subgrupo"] and p["titulo_subgrupo"] not in largos}
    assert sin_mapear == set()
