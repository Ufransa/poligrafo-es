import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

DEFAULT_DB = Path(__file__).parent.parent / "poligrafo.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    session_number INTEGER UNIQUE,
    session_date TEXT,
    zip_url TEXT,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),
    vote_number INTEGER,
    titulo TEXT,
    texto_expediente TEXT,
    fecha TEXT,
    categories TEXT DEFAULT '[]',
    published INTEGER DEFAULT 0,
    UNIQUE(session_id, vote_number)
);

CREATE TABLE IF NOT EXISTS vote_groups (
    id INTEGER PRIMARY KEY,
    vote_id INTEGER REFERENCES votes(id),
    grupo_code TEXT,
    voto TEXT,
    total_diputados INTEGER,
    divided INTEGER DEFAULT 0,
    UNIQUE(vote_id, grupo_code)
);

CREATE TABLE IF NOT EXISTS boe_entries (
    id INTEGER PRIMARY KEY,
    identificador TEXT UNIQUE,
    titulo TEXT,
    rango TEXT,
    departamento TEXT,
    fecha TEXT,
    url_xml TEXT,
    categories TEXT DEFAULT '[]',
    texto_preview TEXT,
    published INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS program_chunks (
    id INTEGER PRIMARY KEY,
    party TEXT,
    category TEXT,
    page_start INTEGER,
    text TEXT
);

CREATE TABLE IF NOT EXISTS vote_program_matches (
    id INTEGER PRIMARY KEY,
    vote_id INTEGER REFERENCES votes(id),
    chunk_id INTEGER REFERENCES program_chunks(id),
    party TEXT,
    score REAL,
    UNIQUE(vote_id, chunk_id, party)
);

CREATE TABLE IF NOT EXISTS published_messages (
    id INTEGER PRIMARY KEY,
    type TEXT,
    ref_id INTEGER,
    telegram_message_id INTEGER,
    sent_at TEXT
);
"""


def init_db(db_path=DEFAULT_DB):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def get_conn(db_path=DEFAULT_DB):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_last_session_number(conn):
    row = conn.execute("SELECT MAX(session_number) FROM sessions").fetchone()
    return row[0] or 0


def insert_session(conn, session_number, session_date, zip_url=None):
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_number, session_date, zip_url, processed_at) VALUES (?,?,?,?)",
        (session_number, session_date, zip_url, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    row = conn.execute("SELECT id FROM sessions WHERE session_number=?", (session_number,)).fetchone()
    return row["id"]


def insert_vote(conn, session_id, vote_number, titulo, texto_expediente, fecha, categories=None):
    conn.execute(
        "INSERT OR IGNORE INTO votes (session_id, vote_number, titulo, texto_expediente, fecha, categories) VALUES (?,?,?,?,?,?)",
        (session_id, vote_number, titulo, texto_expediente, fecha, json.dumps(categories or []))
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM votes WHERE session_id=? AND vote_number=?", (session_id, vote_number)
    ).fetchone()
    return row["id"]


def insert_vote_groups(conn, vote_id, group_votes):
    """group_votes: {code: {'voto': str, 'total': int, 'divided': bool}}"""
    for code, data in group_votes.items():
        conn.execute(
            "INSERT OR REPLACE INTO vote_groups (vote_id, grupo_code, voto, total_diputados, divided) VALUES (?,?,?,?,?)",
            (vote_id, code, data["voto"], data.get("total", 0), int(data.get("divided", False)))
        )
    conn.commit()


def get_unpublished_votes(conn):
    return conn.execute(
        """SELECT v.*, s.session_number, s.zip_url
           FROM votes v
           JOIN sessions s ON v.session_id = s.id
           WHERE v.published = 0
           ORDER BY s.session_number, v.vote_number"""
    ).fetchall()


def get_vote_groups(conn, vote_id):
    return conn.execute(
        "SELECT grupo_code, voto, total_diputados, divided FROM vote_groups WHERE vote_id=?",
        (vote_id,)
    ).fetchall()


def mark_vote_published(conn, vote_id, telegram_message_id):
    conn.execute("UPDATE votes SET published=1 WHERE id=?", (vote_id,))
    conn.execute(
        "INSERT INTO published_messages (type, ref_id, telegram_message_id, sent_at) VALUES ('vote_alert',?,?,?)",
        (vote_id, telegram_message_id, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()


def insert_boe_entry(conn, identificador, titulo, rango, departamento, fecha, url_xml, categories, texto_preview):
    conn.execute(
        """INSERT OR IGNORE INTO boe_entries
           (identificador, titulo, rango, departamento, fecha, url_xml, categories, texto_preview)
           VALUES (?,?,?,?,?,?,?,?)""",
        (identificador, titulo, rango, departamento, fecha, url_xml,
         json.dumps(categories or []), texto_preview or "")
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM boe_entries WHERE identificador=?", (identificador,)
    ).fetchone()
    return row["id"]


def get_unpublished_boe_entries(conn):
    return conn.execute(
        "SELECT * FROM boe_entries WHERE published=0 AND categories != '[]' ORDER BY fecha, id"
    ).fetchall()


def mark_boe_published(conn, entry_id, telegram_message_id):
    conn.execute("UPDATE boe_entries SET published=1 WHERE id=?", (entry_id,))
    conn.execute(
        "INSERT INTO published_messages (type, ref_id, telegram_message_id, sent_at) VALUES ('boe_alert',?,?,?)",
        (entry_id, telegram_message_id, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()


def insert_program_chunk(conn, party, category, page_start, text):
    conn.execute(
        "INSERT INTO program_chunks (party, category, page_start, text) VALUES (?,?,?,?)",
        (party, category, page_start, text),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_all_program_chunks(conn):
    return conn.execute(
        "SELECT id, party, category, page_start, text FROM program_chunks"
    ).fetchall()


def insert_vote_program_match(conn, vote_id, chunk_id, party, score):
    conn.execute(
        """INSERT OR IGNORE INTO vote_program_matches (vote_id, chunk_id, party, score)
           VALUES (?,?,?,?)""",
        (vote_id, chunk_id, party, score),
    )
    conn.commit()


def get_vote_program_matches(conn, vote_id):
    """Returns matches ordered by score desc, each row has party, score, text."""
    return conn.execute(
        """SELECT vm.party, vm.score, pc.text
           FROM vote_program_matches vm
           JOIN program_chunks pc ON vm.chunk_id = pc.id
           WHERE vm.vote_id = ?
           ORDER BY vm.score DESC""",
        (vote_id,),
    ).fetchall()


def get_published_votes_since(conn, since_iso):
    return conn.execute("""SELECT v.id, v.titulo, v.fecha, v.vote_number,
                                  s.session_number, s.session_date
                           FROM votes v
                           JOIN sessions s ON v.session_id = s.id
                           JOIN published_messages pm ON pm.ref_id = v.id AND pm.type = 'vote_alert'
                           WHERE pm.sent_at >= ?
                           ORDER BY s.session_number, v.vote_number""", (since_iso,)).fetchall()


def get_published_boe_entries_since(conn, since_iso):
    return conn.execute("""SELECT be.id, be.identificador, be.titulo, be.categories, be.fecha
                           FROM boe_entries be
                           JOIN published_messages pm ON pm.ref_id = be.id AND pm.type = 'boe_alert'
                           WHERE pm.sent_at >= ?
                           ORDER BY be.fecha, be.id""", (since_iso,)).fetchall()


def get_vote_groups_for_votes(conn, vote_ids):
    if not vote_ids:
        return {}
    vote_ids = list(vote_ids)
    placeholders = ",".join("?" * len(vote_ids))
    rows = conn.execute(
        f"SELECT vote_id, grupo_code, voto FROM vote_groups WHERE vote_id IN ({placeholders})",
        vote_ids).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["vote_id"], {})[row["grupo_code"]] = row["voto"]
    return result
