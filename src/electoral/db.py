# src/electoral/db.py
import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS zips (nombre TEXT PRIMARY KEY, url TEXT, fecha TEXT);
CREATE TABLE IF NOT EXISTS votaciones (
    id TEXT PRIMARY KEY,            -- "<sesion>-<numero>"
    fecha TEXT, sesion INTEGER, numero INTEGER,
    tipo TEXT, subtipo TEXT, es_convalidacion INTEGER,
    expediente TEXT, texto_subgrupo TEXT, clave_iniciativa TEXT,
    resultado TEXT, a_favor INTEGER, en_contra INTEGER, abstenciones INTEGER,
    excluida_tramite INTEGER, url_xml TEXT, url_sesion TEXT
);
CREATE TABLE IF NOT EXISTS votos_partido (
    votacion_id TEXT, partido TEXT, voto TEXT, dividido INTEGER,
    PRIMARY KEY (votacion_id, partido)
);
CREATE TABLE IF NOT EXISTS bloques (
    id INTEGER PRIMARY KEY, partido TEXT, anio INTEGER, pagina INTEGER, texto TEXT,
    url_programa TEXT, extraido INTEGER DEFAULT 0,
    UNIQUE (partido, anio, pagina, texto)
);
CREATE TABLE IF NOT EXISTS promesas (
    id INTEGER PRIMARY KEY, bloque_id INTEGER, partido TEXT, anio INTEGER, pagina INTEGER,
    texto TEXT, cita TEXT, tema TEXT, procedimental INTEGER, embedding BLOB
);
CREATE TABLE IF NOT EXISTS juicios (
    votacion_id TEXT PRIMARY KEY, completo INTEGER DEFAULT 0, respuestas TEXT
);
CREATE TABLE IF NOT EXISTS cruces (
    votacion_id TEXT, promesa_id INTEGER, partido TEXT, nivel TEXT, veredicto TEXT, jueces TEXT,
    PRIMARY KEY (votacion_id, promesa_id)
);
CREATE TABLE IF NOT EXISTS gasto (id INTEGER PRIMARY KEY, fecha TEXT, paso TEXT, usd REAL);
CREATE TABLE IF NOT EXISTS avisos (
    votacion_id TEXT, promesa_id INTEGER, partido TEXT, fecha TEXT,
    PRIMARY KEY (votacion_id, promesa_id, partido)
);
"""


def conectar(ruta: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(ruta, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(ESQUEMA)
    for col in ("url_bocg", "url_boe"):
        try:
            conn.execute(f"ALTER TABLE votaciones ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.execute("CREATE TABLE IF NOT EXISTS boe (clave TEXT PRIMARY KEY, identificador TEXT)")
    return conn
