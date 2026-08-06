# tests/test_digest.py — digest v3 (una ficha por ley)
from digest import format_expediente_block, format_boe_line, build_messages

PARTIES = {"GP": "PP", "GS": "PSOE", "GSUMAR": "Sumar", "GVOX": "Vox"}

GRUPOS_LARGOS = {"Enmiendas presentadas por el Grupo Parlamentario Junts per Catalunya": "Junts"}

EXPEDIENTE = {
    "sustantiva": {
        "titulo": "Dictámenes de Comisiones sobre iniciativas legislativas.",
        "resumen": "Ley de discapacidad: más accesibilidad, autonomía y dependencia",
        "que_cambia": "Ya es ley: amplía prestaciones y accesibilidad universal.",
        "resultado": "aprobada", "a_favor": 179, "en_contra": 33,
    },
    "parciales": [
        {"titulo_subgrupo": "Enmiendas presentadas por el Grupo Parlamentario Junts per Catalunya",
         "texto_subgrupo": "Enmienda 174.", "resultado": "rechazada"},
        {"titulo_subgrupo": "Enmiendas presentadas por el Grupo Parlamentario Junts per Catalunya",
         "texto_subgrupo": "Enmienda 178.", "resultado": "rechazada"},
    ],
    "groups": {
        "GS": {"voto": "Sí", "divided": False},
        "GP": {"voto": "Abstención", "divided": False},
        "GVOX": {"voto": "No", "divided": False},
    },
    "matches": [
        {"party": "PP", "promesa": "blindar por ley el apoyo a la discapacidad",
         "veredicto": "incumple", "page_start": 30},
    ],
}


def test_ficha_muestra_resultado_real_con_totales():
    block = format_expediente_block(EXPEDIENTE, PARTIES, GRUPOS_LARGOS)
    assert "APROBADA" in block
    assert "179" in block and "33" in block
    assert "RECHAZADA" not in block


def test_ficha_agrega_las_enmiendas_en_una_linea():
    block = format_expediente_block(EXPEDIENTE, PARTIES, GRUPOS_LARGOS)
    assert "2 enmiendas" in block
    assert "Junts 2" in block
    assert "Enmienda 174" not in block  # el detalle no se publica


def test_ficha_publica_veredicto_no_extracto_crudo(monkeypatch):
    import digest as digest_mod
    monkeypatch.setattr(digest_mod, "PUBLICAR_VEREDICTOS", True)
    block = format_expediente_block(EXPEDIENTE, PARTIES, GRUPOS_LARGOS)
    assert "blindar por ley" in block
    assert "Incoherente" in block


def test_la_ficha_no_cita_numero_de_pagina(monkeypatch):
    """
    page_start es el índice del trozo de texto, NO la página del PDF (VOX llega
    a 59 en un programa de ~40 páginas). Publicar "p.30" mandaba al lector a una
    página que no existe.
    """
    import digest as digest_mod
    monkeypatch.setattr(digest_mod, "PUBLICAR_VEREDICTOS", True)
    block = format_expediente_block(EXPEDIENTE, PARTIES, GRUPOS_LARGOS)
    assert "p.30" not in block
    assert "p." not in block


def test_match_sin_veredicto_no_se_publica(monkeypatch):
    import digest as digest_mod
    monkeypatch.setattr(digest_mod, "PUBLICAR_VEREDICTOS", True)
    exp = {**EXPEDIENTE, "matches": [
        {"party": "PSOE", "promesa": "algo", "veredicto": None, "page_start": 10}]}
    block = format_expediente_block(exp, PARTIES, GRUPOS_LARGOS)
    assert "PSOE" not in block.split("Absten")[-1]


def test_ficha_agrupa_los_votos_por_sentido():
    block = format_expediente_block(EXPEDIENTE, PARTIES, GRUPOS_LARGOS)
    assert "A favor: PSOE" in block
    assert "Abstención: PP" in block
    assert "En contra: Vox" in block


def test_ficha_sin_enmiendas_no_menciona_enmiendas():
    exp = {**EXPEDIENTE, "parciales": []}
    block = format_expediente_block(exp, PARTIES, GRUPOS_LARGOS)
    assert "enmiendas" not in block


def test_boe_line_uses_resumen_when_available():
    line = format_boe_line({"resumen": "Ayudas al alquiler joven de hasta 250€/mes",
                            "titulo": "Real Decreto 123/2026, de 9 de junio, por el que...",
                            "identificador": "BOE-A-2026-1"})
    assert "Ayudas al alquiler joven" in line
    assert "Real Decreto 123/2026" not in line
    assert "BOE-A-2026-1" in line  # link al BOE


def test_boe_line_falls_back_to_titulo():
    line = format_boe_line({"resumen": None,
                            "titulo": "Real Decreto 123/2026, de 9 de junio",
                            "identificador": "BOE-A-2026-1"})
    assert "Real Decreto 123/2026" in line


def test_build_messages_single_when_short():
    msgs = build_messages("header", ["bloque1", "bloque2"], "footer")
    assert len(msgs) == 1
    assert msgs[0].startswith("header")
    assert msgs[0].endswith("footer")


def test_build_messages_splits_at_limit():
    big_block = "x" * 3000
    msgs = build_messages("header", [big_block, big_block], "footer", limit=4096)
    assert len(msgs) == 2
    assert all(len(m) <= 4096 for m in msgs)


def test_dry_run_does_not_mark_published(tmp_path, monkeypatch):
    from src.db import init_db, get_conn, insert_session, insert_vote, get_votes_for_digest
    import digest as digest_mod

    db = tmp_path / "t.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 1, "20260611")
    insert_vote(conn, sid, 1, "Ley X", "texto", "11/6/2026")
    conn.close()

    monkeypatch.setattr(digest_mod, "TOKEN", "t")
    monkeypatch.setattr(digest_mod, "CHANNEL", "c")
    digest_mod.run(dry_run=True, db_path=db)

    conn = get_conn(db)
    assert len(get_votes_for_digest(conn)) == 1  # sigue pendiente para el lunes
    conn.close()


def test_envio_parcial_marca_solo_lo_enviado(tmp_path, monkeypatch):
    from src.db import init_db, get_conn, insert_session, insert_vote, get_votes_for_digest
    import digest as digest_mod

    db = tmp_path / "p.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 1, "20260714")
    for n in (1, 2):
        insert_vote(conn, sid, n, "Ley", f"Proyecto de Ley {n}", "14/7/2026",
                    clase="sustantiva", expediente_key=f"proyecto de ley {n}",
                    resultado="aprobada")
    conn.close()

    enviados = [11, None]  # el segundo bloque falla
    monkeypatch.setattr(digest_mod, "TOKEN", "t")
    monkeypatch.setattr(digest_mod, "CHANNEL", "c")
    monkeypatch.setattr(digest_mod, "send_message", lambda *a, **k: enviados.pop(0))
    monkeypatch.setattr(digest_mod.time, "sleep", lambda s: None)
    digest_mod.run(db_path=db)

    conn = get_conn(db)
    pendientes = get_votes_for_digest(conn)
    assert len(pendientes) == 1  # el que falló sigue pendiente, el otro no vuelve
    conn.close()


def test_no_publica_veredictos_cuando_el_flag_esta_apagado(monkeypatch):
    """El juez aún da veredictos contradictorios; hasta que se afine, no salen."""
    import digest as digest_mod
    monkeypatch.setattr(digest_mod, "PUBLICAR_VEREDICTOS", False)
    block = format_expediente_block(EXPEDIENTE, PARTIES, GRUPOS_LARGOS)
    assert "blindar por ley" not in block
    assert "Incoherente" not in block
    assert "APROBADA" in block  # el resto de la ficha sigue intacto


def test_ficha_muestra_la_fecha_de_la_votacion():
    """Dos expedientes homonimos solo se distinguen por fecha y totales."""
    exp = {**EXPEDIENTE, "sustantiva": {**EXPEDIENTE["sustantiva"], "fecha": "14/7/2026"}}
    block = format_expediente_block(exp, PARTIES, GRUPOS_LARGOS)
    assert "14/7/2026" in block
