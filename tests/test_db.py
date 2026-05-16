import pytest
import sqlite3
import json
from pathlib import Path
from src.db import (
    init_db, get_conn,
    get_last_session_number, insert_session, insert_vote, insert_vote_groups,
    get_unpublished_votes, get_vote_groups, mark_vote_published,
    insert_boe_entry, get_unpublished_boe_entries, mark_boe_published,
    insert_program_chunk, get_all_program_chunks,
    insert_vote_program_match, get_vote_program_matches,
    get_published_votes_since, get_published_boe_entries_since, get_vote_groups_for_votes,
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


def test_unpublished_votes_returned_before_mark(db):
    session_id = insert_session(db, 177, "20260430")
    insert_vote(db, session_id, 1, "Título", "Expediente", "30/4/2026")

    unpublished = get_unpublished_votes(db)
    assert len(unpublished) == 1


def test_mark_published_removes_from_unpublished(db):
    session_id = insert_session(db, 177, "20260430")
    vote_id = insert_vote(db, session_id, 1, "Título", "Expediente", "30/4/2026")
    mark_vote_published(db, vote_id, telegram_message_id=999)

    unpublished = get_unpublished_votes(db)
    assert len(unpublished) == 0


def test_insert_boe_entry_stores_data(db):
    import json
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


def test_get_unpublished_boe_entries_only_returns_categorized(db):
    insert_boe_entry(db, "BOE-A-2026-003", "Titulo fiscal", "Ley", "Dpto", "20260515", "https://...", ["fiscalidad"], "preview")
    insert_boe_entry(db, "BOE-A-2026-004", "Sin categoria", "Ley", "Dpto", "20260515", "https://...", [], "")
    rows = get_unpublished_boe_entries(db)
    ids = [r["identificador"] for r in rows]
    assert "BOE-A-2026-003" in ids
    assert "BOE-A-2026-004" not in ids


def test_mark_boe_published_updates_flag(db):
    entry_id = insert_boe_entry(db, "BOE-A-2026-005", "T", "R", "D", "20260515", "https://...", ["empleo"], "")
    mark_boe_published(db, entry_id, telegram_message_id=99)
    row = db.execute("SELECT published FROM boe_entries WHERE id=?", (entry_id,)).fetchone()
    assert row["published"] == 1


def test_insert_program_chunk_stores_and_retrieves(db):
    chunk_id = insert_program_chunk(db, "PP", "vivienda", 5, "El partido propone medidas de vivienda asequible.")
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


def test_insert_vote_program_match_stores_data(db):
    session_id = insert_session(db, 1, "20260515")
    vote_id = insert_vote(db, session_id, 1, "Ley de vivienda", "texto", "15/5/2026")
    chunk_id = insert_program_chunk(db, "PP", "vivienda", 1, "propuesta vivienda")
    insert_vote_program_match(db, vote_id, chunk_id, "PP", score=3.0)
    matches = get_vote_program_matches(db, vote_id)
    assert len(matches) == 1
    assert matches[0]["party"] == "PP"
    assert matches[0]["score"] == 3.0


def test_insert_vote_program_match_is_idempotent(db):
    session_id = insert_session(db, 1, "20260515")
    vote_id = insert_vote(db, session_id, 1, "Ley", "texto", "15/5/2026")
    chunk_id = insert_program_chunk(db, "PP", "vivienda", 1, "texto")
    insert_vote_program_match(db, vote_id, chunk_id, "PP", score=2.0)
    insert_vote_program_match(db, vote_id, chunk_id, "PP", score=2.0)
    matches = get_vote_program_matches(db, vote_id)
    assert len(matches) == 1


def test_get_published_votes_since_returns_only_matching_rows(db):
    sid = insert_session(db, 10, "2024-01-15")
    vid = insert_vote(db, sid, 1, "Test vote", "", "")
    insert_vote_groups(db, vid, {"GP": {"voto": "Si", "total": 10, "divided": False}})
    mark_vote_published(db, vid, telegram_message_id=999)
    # mark_vote_published inserts a published_message row with the current timestamp.
    # Update it to a known past timestamp for deterministic testing.
    db.execute(
        "UPDATE published_messages SET sent_at=? WHERE ref_id=? AND type='vote_alert'",
        ("2024-01-14T10:00:00", vid)
    )
    db.commit()
    rows = get_published_votes_since(db, "2024-01-15T00:00:00")
    assert rows == []
    rows2 = get_published_votes_since(db, "2024-01-13T00:00:00")
    assert len(rows2) == 1
    assert rows2[0]["titulo"] == "Test vote"


def test_get_published_boe_entries_since_returns_only_matching(db):
    entry_id = insert_boe_entry(db, "BOE-A-2024-001", "Ley de prueba", "Ley", "Dpto", "20240115", None, ["Fiscal"], "")
    mark_boe_published(db, entry_id, telegram_message_id=999)
    db.execute(
        "UPDATE published_messages SET sent_at = ? WHERE ref_id = ? AND type = ?",
        ("2024-01-15T09:00:00", entry_id, "boe_alert")
    )
    db.commit()
    rows = get_published_boe_entries_since(db, "2024-01-16T00:00:00")
    assert rows == []
    rows2 = get_published_boe_entries_since(db, "2024-01-14T00:00:00")
    assert len(rows2) == 1
    assert rows2[0]["identificador"] == "BOE-A-2024-001"


def test_get_vote_groups_for_votes_groups_by_vote_id(db):
    sid = insert_session(db, 11, "2024-01-16")
    vid1 = insert_vote(db, sid, 1, "Vote A", "", "")
    vid2 = insert_vote(db, sid, 2, "Vote B", "", "")
    insert_vote_groups(db, vid1, {"GP": {"voto": "Si", "total": 10, "divided": False},
                                   "GS": {"voto": "No", "total": 5, "divided": False}})
    insert_vote_groups(db, vid2, {"GP": {"voto": "No", "total": 8, "divided": False}})
    result = get_vote_groups_for_votes(db, [vid1, vid2])
    assert result[vid1] == {"GP": "Si", "GS": "No"}
    assert result[vid2] == {"GP": "No"}
    assert get_vote_groups_for_votes(db, []) == {}
