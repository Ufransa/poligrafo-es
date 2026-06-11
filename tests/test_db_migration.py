import sqlite3
from src.db import init_db, get_conn


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_migration_adds_vote_columns(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    conn = get_conn(db)
    cols = _columns(conn, "votes")
    for col in ("a_favor", "en_contra", "abstenciones", "resultado",
                "resumen", "que_cambia", "enriched_at"):
        assert col in cols, f"missing column {col}"
    conn.close()


def test_migration_adds_boe_columns(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    conn = get_conn(db)
    cols = _columns(conn, "boe_entries")
    assert "resumen" in cols
    assert "enriched_at" in cols
    conn.close()


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    init_db(db)  # second run must not raise
    conn = get_conn(db)
    assert "resumen" in _columns(conn, "votes")
    conn.close()


def test_migration_purges_legacy_matches(tmp_path):
    """Simulate a pre-v2 DB with noise matches; migration must purge them once."""
    db = tmp_path / "legacy.db"
    # Build a pre-v2 schema by hand (votes without v2 columns)
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE votes (id INTEGER PRIMARY KEY, session_id INTEGER,
            vote_number INTEGER, titulo TEXT, texto_expediente TEXT, fecha TEXT,
            categories TEXT DEFAULT '[]', published INTEGER DEFAULT 0);
        CREATE TABLE program_chunks (id INTEGER PRIMARY KEY, party TEXT,
            category TEXT, page_start INTEGER, text TEXT);
        CREATE TABLE vote_program_matches (id INTEGER PRIMARY KEY,
            vote_id INTEGER, chunk_id INTEGER, party TEXT, score REAL);
    """)
    conn.execute("INSERT INTO vote_program_matches (vote_id, chunk_id, party, score) VALUES (1, 1, 'PP', 3.0)")
    conn.commit()
    conn.close()

    init_db(db)  # triggers migration

    conn = get_conn(db)
    count = conn.execute("SELECT COUNT(*) FROM vote_program_matches").fetchone()[0]
    assert count == 0, "legacy noise matches must be purged"
    conn.close()


def test_purge_only_runs_once(tmp_path):
    """Matches inserted AFTER the migration must survive a re-init."""
    db = tmp_path / "test.db"
    init_db(db)
    conn = get_conn(db)
    conn.execute("INSERT INTO sessions (session_number, session_date) VALUES (1, '20260611')")
    conn.execute("INSERT INTO votes (session_id, vote_number, titulo, texto_expediente, fecha) VALUES (1, 1, 't', 'e', 'f')")
    conn.execute("INSERT INTO program_chunks (party, category, page_start, text) VALUES ('PP', 'x', 1, 't')")
    conn.execute("INSERT INTO vote_program_matches (vote_id, chunk_id, party, score) VALUES (1, 1, 'PP', 2.0)")
    conn.commit()
    conn.close()

    init_db(db)  # re-init must NOT purge validated matches

    conn = get_conn(db)
    count = conn.execute("SELECT COUNT(*) FROM vote_program_matches").fetchone()[0]
    assert count == 1
    conn.close()
