import pytest
import sqlite3
import json
from pathlib import Path
from src.db import init_db, get_conn, get_last_session_number, insert_session, insert_vote, insert_vote_groups, get_unpublished_votes, mark_vote_published

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
