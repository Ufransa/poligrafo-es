# tests/test_digest.py — digest v2 (formato legible)
from digest import format_vote_block, format_boe_line, build_messages

PARTIES = {"GP": "PP", "GS": "PSOE", "GSUMAR": "Sumar", "GVOX": "Vox"}

ENRICHED_VOTE = {
    "titulo": "Proposición de Ley Orgánica de medidas en materia de salario mínimo",
    "resumen": "Subida del SMI a 1.250€",
    "que_cambia": "Se acepta tramitar la ley; aún no es definitiva.",
    "resultado": "aprobada",
    "groups": {
        "GS": {"voto": "Sí", "divided": False},
        "GSUMAR": {"voto": "Sí", "divided": False},
        "GP": {"voto": "No", "divided": False},
        "GVOX": {"voto": "No", "divided": True},
    },
    "matches": [
        {"party": "PSOE", "text": "Subiremos el SMI hasta el 60% del salario medio", "page_start": 45},
    ],
}

RAW_VOTE = {
    "titulo": "Toma en consideración de la Proposición de Ley X",
    "resumen": None, "que_cambia": None, "resultado": None,
    "groups": {"GP": {"voto": "No", "divided": False}},
    "matches": [],
}


def test_enriched_vote_shows_resumen_and_resultado():
    block = format_vote_block(ENRICHED_VOTE, PARTIES)
    assert "Subida del SMI a 1.250€" in block
    assert "✅ APROBADA" in block
    assert "aún no es definitiva" in block


def test_parties_grouped_by_sense_with_full_names():
    block = format_vote_block(ENRICHED_VOTE, PARTIES)
    assert "A favor: PSOE, Sumar" in block
    assert "En contra: PP, Vox (div.)" in block
    assert "GS" not in block  # nada de siglas crípticas


def test_validated_match_rendered_with_page():
    block = format_vote_block(ENRICHED_VOTE, PARTIES)
    assert "📋" in block
    assert "PSOE" in block
    assert "p.45" in block


def test_unenriched_vote_falls_back_to_titulo():
    block = format_vote_block(RAW_VOTE, PARTIES)
    assert "Toma en consideración" in block
    assert "APROBADA" not in block  # sin resultado no se inventa nada


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
