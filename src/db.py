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


_VOTE_V2_COLUMNS = {
    "a_favor": "INTEGER",
    "en_contra": "INTEGER",
    "abstenciones": "INTEGER",
    "resultado": "TEXT",
    "resumen": "TEXT",
    "que_cambia": "TEXT",
    "enriched_at": "TEXT",
}
_BOE_V2_COLUMNS = {
    "resumen": "TEXT",
    "enriched_at": "TEXT",
}
_VOTE_V3_COLUMNS = {
    "titulo_subgrupo": "TEXT",
    "texto_subgrupo": "TEXT",
    "clase": "TEXT",
    "expediente_key": "TEXT",
}


def _migrate(conn):
    """Añade columnas v2/v3 si faltan. La primera vez purga los matches legacy
    (ruido del umbral de 2 keywords, ~713 por voto)."""
    vote_cols = {r[1] for r in conn.execute("PRAGMA table_info(votes)")}
    first_time = "resumen" not in vote_cols
    for col, ctype in _VOTE_V2_COLUMNS.items():
        if col not in vote_cols:
            conn.execute(f"ALTER TABLE votes ADD COLUMN {col} {ctype}")
    boe_cols = {r[1] for r in conn.execute("PRAGMA table_info(boe_entries)")}
    for col, ctype in _BOE_V2_COLUMNS.items():
        if col not in boe_cols:
            conn.execute(f"ALTER TABLE boe_entries ADD COLUMN {col} {ctype}")
    for col, ctype in _VOTE_V3_COLUMNS.items():
        if col not in vote_cols:
            conn.execute(f"ALTER TABLE votes ADD COLUMN {col} {ctype}")
    if first_time:
        conn.execute("DELETE FROM vote_program_matches")
    conn.commit()


def init_db(db_path=DEFAULT_DB):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    _migrate(conn)
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


def insert_vote(conn, session_id, vote_number, titulo, texto_expediente, fecha,
                categories=None, a_favor=None, en_contra=None,
                abstenciones=None, resultado=None):
    conn.execute(
        """INSERT OR IGNORE INTO votes
           (session_id, vote_number, titulo, texto_expediente, fecha, categories,
            a_favor, en_contra, abstenciones, resultado)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (session_id, vote_number, titulo, texto_expediente, fecha,
         json.dumps(categories or []), a_favor, en_contra, abstenciones, resultado)
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


def get_votes_for_digest(conn):
    """Todo voto aún no publicado (el digest publica y marca)."""
    return conn.execute(
        """SELECT v.*, s.session_number
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


def mark_digest_published(conn, vote_ids, boe_ids, telegram_message_id):
    now = datetime.now(timezone.utc).isoformat()
    for vid in vote_ids:
        conn.execute("UPDATE votes SET published=1 WHERE id=?", (vid,))
    for bid in boe_ids:
        conn.execute("UPDATE boe_entries SET published=1 WHERE id=?", (bid,))
    conn.execute(
        "INSERT INTO published_messages (type, ref_id, telegram_message_id, sent_at)"
        " VALUES ('weekly_digest', NULL, ?, ?)",
        (telegram_message_id, now),
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


def get_boe_for_digest(conn):
    return conn.execute(
        "SELECT * FROM boe_entries WHERE published=0 AND categories != '[]' ORDER BY fecha, id"
    ).fetchall()


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


def get_validated_matches(conn, vote_id):
    """Matches validados por el juez LLM, con texto y página del programa."""
    return conn.execute(
        """SELECT vm.party, pc.text, pc.page_start
           FROM vote_program_matches vm
           JOIN program_chunks pc ON vm.chunk_id = pc.id
           WHERE vm.vote_id = ?
           ORDER BY vm.party""",
        (vote_id,),
    ).fetchall()


def get_unenriched_votes(conn):
    """Votos pendientes de enriquecer. Excluye published=1 para no quemar
    API en votos pre-v2 ya emitidos como alertas."""
    return conn.execute(
        """SELECT v.*, s.session_number FROM votes v
           JOIN sessions s ON v.session_id = s.id
           WHERE v.enriched_at IS NULL AND v.published = 0
           ORDER BY v.id"""
    ).fetchall()


def set_vote_enrichment(conn, vote_id, resumen, que_cambia):
    conn.execute(
        "UPDATE votes SET resumen=?, que_cambia=?, enriched_at=? WHERE id=?",
        (resumen, que_cambia, datetime.now(timezone.utc).isoformat(), vote_id),
    )
    conn.commit()


def get_unenriched_boe_entries(conn):
    return conn.execute(
        """SELECT * FROM boe_entries
           WHERE enriched_at IS NULL AND published = 0 AND categories != '[]'
           ORDER BY id"""
    ).fetchall()


def set_boe_enrichment(conn, entry_id, resumen):
    conn.execute(
        "UPDATE boe_entries SET resumen=?, enriched_at=? WHERE id=?",
        (resumen, datetime.now(timezone.utc).isoformat(), entry_id),
    )
    conn.commit()


