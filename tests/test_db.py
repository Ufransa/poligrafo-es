import pytest
import json
from src.db import (
    init_db, get_conn,
    get_last_session_number, insert_session, insert_vote, insert_vote_groups,
    get_votes_for_digest, get_vote_groups, mark_digest_published,
    insert_boe_entry, get_boe_for_digest,
    insert_program_chunk, get_all_program_chunks,
    insert_vote_program_match, get_validated_matches,
    get_expedientes_for_digest,
)

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_conn(db_path)
    yield conn
    conn.close()


def test_fresh_db_has_zero_sessions(db):
    assert get_last_session_number(db) == 0


def test_insert_session_stores_and_retrieves(db):
    session_id = insert_session(db, 177, "20260430")
    assert session_id is not None
    assert get_last_session_number(db) == 177


def test_insert_duplicate_session_is_idempotent(db):
    id1 = insert_session(db, 177, "20260430")
    id2 = insert_session(db, 177, "20260430")
    assert id1 == id2
    assert get_last_session_number(db) == 177


def test_vote_and_groups_stored_correctly(db):
    session_id = insert_session(db, 177, "20260430")
    vote_id = insert_vote(db, session_id, 1, "Ley de vivienda", "Regularización alquileres", "30/4/2026")

    group_votes = {
        "GP":     {"voto": "No",  "total": 137, "divided": False},
        "GS":     {"voto": "Sí",  "total": 120, "divided": False},
        "GSUMAR": {"voto": "Sí",  "total": 31,  "divided": False},
        "GVOX":   {"voto": "No",  "total": 33,  "divided": False},
    }
    insert_vote_groups(db, vote_id, group_votes)

    rows = db.execute("SELECT grupo_code, voto FROM vote_groups WHERE vote_id=?", (vote_id,)).fetchall()
    result = {r["grupo_code"]: r["voto"] for r in rows}

    assert result["GP"] == "No"
    assert result["GS"] == "Sí"
    assert result["GSUMAR"] == "Sí"


def test_pending_votes_returned_for_digest(db):
    session_id = insert_session(db, 177, "20260430")
    insert_vote(db, session_id, 1, "Título", "Expediente", "30/4/2026")

    pending = get_votes_for_digest(db)
    assert len(pending) == 1


def test_mark_digest_published_removes_from_pending(db):
    session_id = insert_session(db, 177, "20260430")
    vote_id = insert_vote(db, session_id, 1, "Título", "Expediente", "30/4/2026")
    entry_id = insert_boe_entry(db, "BOE-A-2026-009", "T", "R", "D", "20260515", "https://...", ["empleo"], "")

    mark_digest_published(db, [vote_id], [entry_id], telegram_message_id=999)

    assert get_votes_for_digest(db) == []
    assert get_boe_for_digest(db) == []
    row = db.execute("SELECT * FROM published_messages WHERE type='weekly_digest'").fetchone()
    assert row["telegram_message_id"] == 999


def test_insert_boe_entry_stores_data(db):
    entry_id = insert_boe_entry(
        db,
        identificador="BOE-A-2026-001",
        titulo="Real Decreto de prueba",
        rango="Real Decreto",
        departamento="Ministerio de Hacienda",
        fecha="20260515",
        url_xml="https://www.boe.es/diario_boe/xml.php?id=BOE-A-2026-001",
        categories=["fiscalidad"],
        texto_preview="Texto de prueba fiscal.",
    )
    row = db.execute("SELECT * FROM boe_entries WHERE id=?", (entry_id,)).fetchone()
    assert row["identificador"] == "BOE-A-2026-001"
    assert json.loads(row["categories"]) == ["fiscalidad"]
    assert row["texto_preview"] == "Texto de prueba fiscal."


def test_insert_boe_entry_is_idempotent(db):
    insert_boe_entry(db, "BOE-A-2026-002", "Titulo", "Ley", "Dpto", "20260515", "https://...", [], "")
    insert_boe_entry(db, "BOE-A-2026-002", "Titulo", "Ley", "Dpto", "20260515", "https://...", [], "")
    count = db.execute(
        "SELECT COUNT(*) FROM boe_entries WHERE identificador='BOE-A-2026-002'"
    ).fetchone()[0]
    assert count == 1


def test_get_boe_for_digest_only_returns_categorized(db):
    insert_boe_entry(db, "BOE-A-2026-003", "Titulo fiscal", "Ley", "Dpto", "20260515", "https://...", ["fiscalidad"], "preview")
    insert_boe_entry(db, "BOE-A-2026-004", "Sin categoria", "Ley", "Dpto", "20260515", "https://...", [], "")
    rows = get_boe_for_digest(db)
    ids = [r["identificador"] for r in rows]
    assert "BOE-A-2026-003" in ids
    assert "BOE-A-2026-004" not in ids


def test_insert_program_chunk_stores_and_retrieves(db):
    insert_program_chunk(db, "PP", "vivienda", 5, "El partido propone medidas de vivienda asequible.")
    rows = get_all_program_chunks(db)
    assert len(rows) == 1
    assert rows[0]["party"] == "PP"
    assert rows[0]["category"] == "vivienda"
    assert rows[0]["page_start"] == 5
    assert "vivienda" in rows[0]["text"]


def test_get_all_program_chunks_returns_all(db):
    insert_program_chunk(db, "PP", "vivienda", 1, "texto vivienda")
    insert_program_chunk(db, "PSOE", "fiscalidad", 3, "texto fiscal")
    rows = get_all_program_chunks(db)
    assert len(rows) == 2
    parties = {r["party"] for r in rows}
    assert parties == {"PP", "PSOE"}


def test_validated_match_stored_with_page(db):
    session_id = insert_session(db, 1, "20260515")
    vote_id = insert_vote(db, session_id, 1, "Ley de vivienda", "texto", "15/5/2026")
    chunk_id = insert_program_chunk(db, "PP", "vivienda", 7, "propuesta vivienda")
    insert_vote_program_match(db, vote_id, chunk_id, "PP", 3.0,
                              "construir 100.000 viviendas públicas", "incumple")
    matches = get_validated_matches(db, vote_id)
    assert len(matches) == 1
    assert matches[0]["party"] == "PP"
    assert matches[0]["page_start"] == 7
    assert "viviendas públicas" in matches[0]["promesa"]
    assert matches[0]["veredicto"] == "incumple"


def test_match_sin_veredicto_no_se_devuelve(db):
    session_id = insert_session(db, 1, "20260515")
    vote_id = insert_vote(db, session_id, 1, "Ley de vivienda", "texto", "15/5/2026")
    chunk_id = insert_program_chunk(db, "PP", "vivienda", 7, "propuesta vivienda")
    insert_vote_program_match(db, vote_id, chunk_id, "PP", 3.0, "algo", None)
    assert get_validated_matches(db, vote_id) == []


def test_insert_vote_program_match_is_idempotent(db):
    session_id = insert_session(db, 1, "20260515")
    vote_id = insert_vote(db, session_id, 1, "Ley", "texto", "15/5/2026")
    chunk_id = insert_program_chunk(db, "PP", "vivienda", 1, "texto")
    insert_vote_program_match(db, vote_id, chunk_id, "PP", 2.0, "p", "cumple")
    insert_vote_program_match(db, vote_id, chunk_id, "PP", 2.0, "p", "cumple")
    matches = get_validated_matches(db, vote_id)
    assert len(matches) == 1


def test_get_expedientes_agrupa_parciales_bajo_su_sustantiva(tmp_path):
    from src.db import (init_db, get_conn, insert_session, insert_vote,
                        get_expedientes_for_digest)
    db = tmp_path / "e.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 192, "20260714")
    for n in range(1, 4):
        insert_vote(conn, sid, n, "Dictámenes", "Proyecto de Ley X", "14/7/2026",
                    titulo_subgrupo="Enmiendas presentadas por el Grupo Parlamentario VOX",
                    texto_subgrupo=f"Enmienda {n}.", clase="parcial",
                    expediente_key="proyecto de ley x")
    insert_vote(conn, sid, 54, "Dictámenes",
                "Votación del dictamen del Proyecto de Ley X", "14/7/2026",
                titulo_subgrupo="", texto_subgrupo="", clase="sustantiva",
                expediente_key="proyecto de ley x", resultado="aprobada")

    exps = get_expedientes_for_digest(conn)
    assert len(exps) == 1
    assert exps[0]["sustantiva"]["vote_number"] == 54
    assert len(exps[0]["parciales"]) == 3
    conn.close()


def test_expediente_sin_sustantiva_no_se_publica(tmp_path):
    from src.db import (init_db, get_conn, insert_session, insert_vote,
                        get_expedientes_for_digest)
    db = tmp_path / "e2.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 192, "20260714")
    insert_vote(conn, sid, 1, "Dictámenes", "Proyecto de Ley Y", "14/7/2026",
                titulo_subgrupo="Enmiendas presentadas por el GP VOX",
                texto_subgrupo="Enmienda 1.", clase="parcial",
                expediente_key="proyecto de ley y")
    assert get_expedientes_for_digest(conn) == []
    conn.close()
