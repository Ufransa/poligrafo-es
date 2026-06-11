# PolígrafoES v2 — Digest Legible Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Digest semanal comprensible: resúmenes en español llano vía Haiku 4.5 generados al ingestar, matcher con juez LLM (adiós a los 713 matches/voto), alertas diarias eliminadas.

**Architecture:** El fetcher diario enriquece cada item nuevo con una llamada a Claude Haiku 4.5 (structured outputs + Pydantic) y guarda el resultado en SQLite. El digest del lunes es una plantilla pura sobre datos ya enriquecidos: publica todo lo `published=0` y lo marca, sin ventanas de fechas ni dependencia de la API. El keyword matcher pasa a ser pre-filtro (top-5 chunks por partido); el LLM valida o descarta.

**Tech Stack:** Python 3.11+, SQLite (stdlib), `anthropic` SDK (modelo `claude-haiku-4-5`), `pydantic`, pytest. Spec: `docs/superpowers/specs/2026-06-11-digest-legible-v2-design.md`.

**Working dir:** `D:\1.Fran\DEV\poligrafo-es` (todos los comandos se ejecutan desde aquí).

---

### Task 1: Migración de esquema + purga de matches

**Files:**
- Modify: `src/db.py`
- Test: `tests/test_db_migration.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db_migration.py`:

```python
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
    conn.execute("INSERT INTO program_chunks (party, category, page_start, text) VALUES ('PP', 'x', 1, 't')")
    conn.execute("INSERT INTO vote_program_matches (vote_id, chunk_id, party, score) VALUES (1, 1, 'PP', 2.0)")
    conn.commit()
    conn.close()

    init_db(db)  # re-init must NOT purge validated matches

    conn = get_conn(db)
    count = conn.execute("SELECT COUNT(*) FROM vote_program_matches").fetchone()[0]
    assert count == 1
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db_migration.py -v`
Expected: FAIL (columns missing — `assert col in cols` fails).

- [ ] **Step 3: Implement the migration in `src/db.py`**

After the `SCHEMA` constant, add:

```python
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


def _migrate_v2(conn):
    """Añade columnas v2 si faltan. La primera vez purga los matches legacy
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
    if first_time:
        conn.execute("DELETE FROM vote_program_matches")
    conn.commit()
```

Replace `init_db` with:

```python
def init_db(db_path=DEFAULT_DB):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    _migrate_v2(conn)
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db_migration.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Run the full suite (regression)**

Run: `python -m pytest -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/db.py tests/test_db_migration.py
git commit -m "feat(db): migracion v2 con columnas de enriquecimiento y purga de matches legacy"
```

---

### Task 2: Resultado de la votación desde Totales

**Files:**
- Modify: `src/congreso.py` (añadir `compute_resultado`)
- Modify: `src/db.py:108-117` (`insert_vote` acepta totales y resultado)
- Test: `tests/test_congreso.py` (añadir), `tests/test_db_migration.py` (añadir)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_congreso.py`:

```python
def test_compute_resultado_aprobada():
    from src.congreso import compute_resultado
    assert compute_resultado(a_favor=310, en_contra=33) == "aprobada"


def test_compute_resultado_rechazada():
    from src.congreso import compute_resultado
    assert compute_resultado(a_favor=33, en_contra=310) == "rechazada"


def test_compute_resultado_empate_es_rechazada():
    # En el Congreso un empate no aprueba (art. 88 Reglamento: votaciones de desempate aparte)
    from src.congreso import compute_resultado
    assert compute_resultado(a_favor=100, en_contra=100) == "rechazada"


def test_fixture_totals_parsed():
    vote = parse_vote_xml(FIXTURE_XML)
    assert vote["a_favor"] > 0 or vote["en_contra"] > 0
```

Append to `tests/test_db_migration.py`:

```python
def test_insert_vote_stores_totals_and_resultado(tmp_path):
    from src.db import insert_session, insert_vote
    db = tmp_path / "test.db"
    init_db(db)
    conn = get_conn(db)
    sid = insert_session(conn, 200, "20260611")
    vid = insert_vote(conn, sid, 1, "Título", "Expediente", "11/6/2026",
                      categories=["vivienda"],
                      a_favor=200, en_contra=140, abstenciones=10,
                      resultado="aprobada")
    row = conn.execute("SELECT * FROM votes WHERE id=?", (vid,)).fetchone()
    assert row["a_favor"] == 200
    assert row["en_contra"] == 140
    assert row["abstenciones"] == 10
    assert row["resultado"] == "aprobada"
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_congreso.py tests/test_db_migration.py -v`
Expected: FAIL (`compute_resultado` no existe; `insert_vote` no acepta `a_favor`).

- [ ] **Step 3: Implement**

In `src/congreso.py`, after `aggregate_group_votes`:

```python
def compute_resultado(a_favor, en_contra):
    """Resultado de la votación según los totales oficiales del XML."""
    return "aprobada" if a_favor > en_contra else "rechazada"
```

In `src/db.py`, replace `insert_vote` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_congreso.py tests/test_db_migration.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/congreso.py src/db.py tests/test_congreso.py tests/test_db_migration.py
git commit -m "feat(congreso): resultado aprobada/rechazada desde totales del xml"
```

---

### Task 3: Matcher como pre-filtro top-5 por partido

**Files:**
- Modify: `src/matcher.py`
- Test: `tests/test_matcher.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_matcher.py`:

```python
from src.matcher import top_candidates_per_party


def _chunk(cid, party, text, page=1):
    return {"id": cid, "party": party, "text": text, "page_start": page}


VOTE_TEXT = "Proposición de ley sobre vivienda y alquiler asequible para jóvenes"


def test_returns_dict_keyed_by_party():
    chunks = [
        _chunk(1, "PP", "garantizar vivienda y alquiler asequible jóvenes"),
        _chunk(2, "PSOE", "vivienda alquiler asequible para todos los jóvenes"),
    ]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert set(result.keys()) == {"PP", "PSOE"}


def test_caps_at_five_candidates_per_party():
    chunks = [
        _chunk(i, "PP", f"vivienda alquiler asequible jóvenes propuesta {i}")
        for i in range(1, 9)
    ]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert len(result["PP"]) == 5


def test_candidates_sorted_by_score_desc():
    chunks = [
        _chunk(1, "PP", "vivienda"),  # 1 keyword compartida
        _chunk(2, "PP", "vivienda alquiler asequible jóvenes"),  # 4 compartidas
    ]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert result["PP"][0]["chunk_id"] == 2
    assert result["PP"][0]["score"] > result["PP"][1]["score"]


def test_zero_score_chunks_excluded():
    chunks = [_chunk(1, "VOX", "pesca fluvial trucha sostenible")]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert "VOX" not in result


def test_candidate_carries_page_start():
    chunks = [_chunk(7, "PSOE", "vivienda alquiler asequible", page=45)]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert result["PSOE"][0]["page_start"] == 45
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_matcher.py -v`
Expected: FAIL (`ImportError: cannot import name 'top_candidates_per_party'`).

- [ ] **Step 3: Implement in `src/matcher.py`**

Append after `find_program_matches`:

```python
def top_candidates_per_party(vote_text, chunks, per_party=5):
    """
    Pre-filtro para el juez LLM: top-N chunks por partido por score de keywords.
    vote_text: str (titulo + texto_expediente)
    chunks: iterable de dicts/Rows con {id, party, text, page_start}
    Returns: {party: [{chunk_id, party, score, text, page_start}, ...]} orden score desc
    """
    vote_kws = _keywords(vote_text)
    if not vote_kws:
        return {}

    seen = set()
    by_party = {}
    for chunk in chunks:
        key = (chunk["id"], chunk["party"])
        if key in seen:
            continue
        seen.add(key)
        score = len(vote_kws & _keywords(chunk["text"]))
        if score < 1:
            continue
        by_party.setdefault(chunk["party"], []).append({
            "chunk_id": chunk["id"],
            "party": chunk["party"],
            "score": score,
            "text": chunk["text"],
            "page_start": chunk["page_start"],
        })

    return {
        party: sorted(cands, key=lambda c: -c["score"])[:per_party]
        for party, cands in by_party.items()
    }
```

(`find_program_matches` se elimina en Task 5 cuando el fetcher deje de usarla.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_matcher.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/matcher.py tests/test_matcher.py
git commit -m "feat(matcher): pre-filtro top-5 candidatos por partido para el juez llm"
```

---

### Task 4: Módulo LLM (`src/llm.py`)

**Files:**
- Create: `src/llm.py`
- Modify: `requirements.txt`
- Test: `tests/test_llm.py` (create)

- [ ] **Step 1: Add dependencies**

`requirements.txt` becomes:

```
requests==2.32.3
python-dotenv==1.0.1
pytest==8.2.0
pytest-mock==3.14.0
pdfplumber
anthropic
pydantic
```

Run: `pip install anthropic pydantic`

- [ ] **Step 2: Write the failing tests**

Create `tests/test_llm.py`:

```python
from src.llm import enrich_vote, summarize_boe, VoteEnrichment, PartyMatch, BoeSummary


class FakeResponse:
    def __init__(self, parsed):
        self.parsed_output = parsed


class FakeMessages:
    def __init__(self, parsed):
        self._parsed = parsed
        self.last_kwargs = None

    def parse(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeResponse(self._parsed)


class FakeClient:
    def __init__(self, parsed):
        self.messages = FakeMessages(parsed)


VOTE = {"titulo": "Subida del SMI", "texto_expediente": "Se eleva el salario mínimo..."}
CANDIDATES = {
    "PSOE": [{"chunk_id": 10, "party": "PSOE", "score": 4,
              "text": "Subiremos el SMI hasta el 60% del salario medio", "page_start": 45}],
    "VOX": [{"chunk_id": 20, "party": "VOX", "score": 2,
             "text": "Reforma fiscal integral", "page_start": 12}],
}


def test_enrich_vote_returns_enrichment():
    parsed = VoteEnrichment(
        resumen="Subida del salario mínimo",
        que_cambia="El SMI sube si completa el trámite.",
        matches=[PartyMatch(party="PSOE", chunk_id=10)],
    )
    client = FakeClient(parsed)
    result = enrich_vote(VOTE, CANDIDATES, client=client)
    assert result.resumen == "Subida del salario mínimo"
    assert result.matches[0].chunk_id == 10


def test_enrich_vote_drops_hallucinated_chunk_ids():
    parsed = VoteEnrichment(
        resumen="x", que_cambia="y",
        matches=[
            PartyMatch(party="PSOE", chunk_id=10),    # real
            PartyMatch(party="VOX", chunk_id=999),    # inventado por el modelo
            PartyMatch(party="PP", chunk_id=None),    # sin match → fuera
        ],
    )
    client = FakeClient(parsed)
    result = enrich_vote(VOTE, CANDIDATES, client=client)
    assert [m.chunk_id for m in result.matches] == [10]


def test_enrich_vote_prompt_contains_chunk_ids_and_model():
    parsed = VoteEnrichment(resumen="x", que_cambia="y", matches=[])
    client = FakeClient(parsed)
    enrich_vote(VOTE, CANDIDATES, client=client)
    kwargs = client.messages.last_kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    user_content = kwargs["messages"][0]["content"]
    assert "chunk_id=10" in user_content
    assert "chunk_id=20" in user_content
    assert "Subida del SMI" in user_content


def test_summarize_boe_returns_string():
    client = FakeClient(BoeSummary(resumen="Nuevas ayudas al alquiler joven de hasta 250€/mes"))
    entry = {"titulo": "Real Decreto 123/2026...", "rango": "Real Decreto",
             "departamento": "Ministerio de Vivienda", "texto_preview": "..."}
    result = summarize_boe(entry, client=client)
    assert result == "Nuevas ayudas al alquiler joven de hasta 250€/mes"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.llm'`).

- [ ] **Step 4: Implement `src/llm.py`**

```python
"""
src/llm.py — PolígrafoES
Enriquecimiento con Claude Haiku 4.5: resúmenes en español llano y juez de
relevancia voto↔programa. Structured outputs vía Pydantic.
"""
from typing import Optional

import anthropic
from pydantic import BaseModel

MODEL = "claude-haiku-4-5"


class PartyMatch(BaseModel):
    party: str
    chunk_id: Optional[int]  # None si ningún extracto del partido es pertinente


class VoteEnrichment(BaseModel):
    resumen: str
    que_cambia: str
    matches: list[PartyMatch]


class BoeSummary(BaseModel):
    resumen: str


_SYSTEM_VOTE = """Eres el redactor de PolígrafoES, una herramienta personal que traduce \
votaciones del Congreso de los Diputados a español llano. Tu lector es un ciudadano \
informado sin formación jurídica.

FORMAT RULES (no negociables):
- resumen: máximo 12 palabras. Qué se vota, en cristiano. Sin jerga parlamentaria \
("toma en consideración", "proposición de ley orgánica"...). Si es un trámite y no \
una ley definitiva, no lo digas aquí (va en que_cambia).
- que_cambia: 1 o 2 frases. La consecuencia práctica: qué cambia si sale adelante, \
o qué se ha rechazado. Si es solo un paso del trámite, dilo ("se acepta tramitarla; \
aún no es ley").
- matches: por cada partido del que recibas extractos, devuelve el chunk_id del ÚNICO \
extracto que se pronuncia sobre la materia concreta que se vota, o null si ninguno lo \
hace. Compartir vocabulario NO es pronunciarse. En caso de duda, null.
- Neutralidad absoluta: describe, no opines ni califiques."""

_SYSTEM_BOE = """Eres el redactor de PolígrafoES. Resumes entradas del BOE para un \
ciudadano sin formación jurídica.

FORMAT RULES (no negociables):
- resumen: una sola frase (máximo 25 palabras) en español llano con la consecuencia \
práctica de la norma. Sin números de expediente ni jerga legal.
- Neutralidad absoluta: describe, no opines."""


def _client():
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY del entorno


def enrich_vote(vote, candidates, client=None):
    """
    vote: dict con 'titulo' y 'texto_expediente'.
    candidates: {party: [{chunk_id, score, text, page_start}, ...]} (pre-filtro del matcher).
    Returns: VoteEnrichment con matches filtrados a chunk_ids realmente candidatos.
    """
    client = client or _client()

    parts = [
        "VOTACIÓN:",
        f"Título oficial: {vote['titulo']}",
        f"Expediente: {(vote.get('texto_expediente') or '')[:1500]}",
    ]
    valid_ids = set()
    for party, cands in candidates.items():
        parts.append(f"\nExtractos del programa electoral de {party}:")
        for c in cands:
            valid_ids.add(c["chunk_id"])
            parts.append(f"[chunk_id={c['chunk_id']}] (p.{c['page_start']}) {c['text'][:600]}")
    if not candidates:
        parts.append("\n(No hay extractos de programas candidatos para esta votación.)")

    response = client.messages.parse(
        model=MODEL,
        max_tokens=2048,
        system=_SYSTEM_VOTE,
        messages=[{"role": "user", "content": "\n".join(parts)}],
        output_format=VoteEnrichment,
    )
    enrichment = response.parsed_output
    enrichment.matches = [m for m in enrichment.matches if m.chunk_id in valid_ids]
    return enrichment


def summarize_boe(entry, client=None):
    """entry: dict con titulo, rango, departamento, texto_preview. Returns: str."""
    client = client or _client()
    prompt = (
        f"Título: {entry['titulo']}\n"
        f"Rango: {entry.get('rango', '')}\n"
        f"Departamento: {entry.get('departamento', '')}\n"
        f"Texto (inicio): {(entry.get('texto_preview') or '')[:1200]}"
    )
    response = client.messages.parse(
        model=MODEL,
        max_tokens=512,
        system=_SYSTEM_BOE,
        messages=[{"role": "user", "content": prompt}],
        output_format=BoeSummary,
    )
    return response.parsed_output.resumen
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llm.py tests/test_llm.py requirements.txt
git commit -m "feat(llm): enriquecimiento haiku 4.5 con structured outputs y juez de matches"
```

---

### Task 5: Fetcher v2 — enriquecer al ingestar, sin alertas

**Files:**
- Modify: `fetcher.py` (reescritura de secciones 3-5)
- Modify: `src/db.py` (helpers de enriquecimiento; borrar funciones de alertas)
- Modify: `src/matcher.py` (borrar `find_program_matches`)
- Test: `tests/test_fetcher_enrichment.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fetcher_enrichment.py`:

```python
import pytest
from src.db import (
    init_db, get_conn, insert_session, insert_vote, insert_boe_entry,
    insert_program_chunk, get_unenriched_votes, get_unenriched_boe_entries,
)
from src.llm import VoteEnrichment, PartyMatch
import fetcher


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    c = get_conn(db)
    yield c
    c.close()


def _seed_vote(conn, published=0):
    sid = insert_session(conn, 300, "20260611")
    vid = insert_vote(conn, sid, 1, "Proposición de Ley de vivienda",
                      "alquiler asequible jóvenes", "11/6/2026",
                      a_favor=200, en_contra=140, abstenciones=10, resultado="aprobada")
    conn.execute("UPDATE votes SET published=? WHERE id=?", (published, vid))
    conn.commit()
    return vid


def test_unenriched_votes_excludes_already_published(conn):
    _seed_vote(conn, published=1)  # voto pre-v2 ya publicado como alerta
    sid = insert_session(conn, 301, "20260612")
    vid_new = insert_vote(conn, sid, 1, "Otra ley", "texto", "12/6/2026")
    rows = get_unenriched_votes(conn)
    assert [r["id"] for r in rows] == [vid_new]


def test_enrich_pending_stores_summary_and_matches(conn, monkeypatch):
    vid = _seed_vote(conn)
    cid = insert_program_chunk(conn, "PSOE", "vivienda", 45,
                               "vivienda alquiler asequible jóvenes garantizado")

    def fake_enrich(vote, candidates, client=None):
        return VoteEnrichment(resumen="Ley de vivienda", que_cambia="Cambia X.",
                              matches=[PartyMatch(party="PSOE", chunk_id=cid)])

    monkeypatch.setattr(fetcher, "enrich_vote", fake_enrich)
    fetcher.enrich_pending(conn)

    row = conn.execute("SELECT * FROM votes WHERE id=?", (vid,)).fetchone()
    assert row["resumen"] == "Ley de vivienda"
    assert row["enriched_at"] is not None
    matches = conn.execute("SELECT * FROM vote_program_matches WHERE vote_id=?", (vid,)).fetchall()
    assert len(matches) == 1
    assert matches[0]["chunk_id"] == cid


def test_enrich_failure_leaves_item_pending(conn, monkeypatch):
    vid = _seed_vote(conn)

    def boom(vote, candidates, client=None):
        raise RuntimeError("api caída")

    monkeypatch.setattr(fetcher, "enrich_vote", boom)
    fetcher.enrich_pending(conn)  # no debe lanzar

    row = conn.execute("SELECT * FROM votes WHERE id=?", (vid,)).fetchone()
    assert row["enriched_at"] is None  # se reintenta en el siguiente run


def test_enrich_boe_stores_summary(conn, monkeypatch):
    eid = insert_boe_entry(conn, "BOE-A-2026-1", "Real Decreto de ayudas",
                           "Real Decreto", "Min. Vivienda", "2026-06-11",
                           "http://x", ["vivienda"], "texto preview")

    monkeypatch.setattr(fetcher, "summarize_boe",
                        lambda entry, client=None: "Ayudas al alquiler joven")
    fetcher.enrich_pending(conn)

    row = conn.execute("SELECT * FROM boe_entries WHERE id=?", (eid,)).fetchone()
    assert row["resumen"] == "Ayudas al alquiler joven"
    assert row["enriched_at"] is not None


def test_uncategorized_boe_not_enriched(conn, monkeypatch):
    eid = insert_boe_entry(conn, "BOE-A-2026-2", "Nombramientos varios",
                           "Orden", "Presidencia", "2026-06-11",
                           "http://x", [], "")
    called = []
    monkeypatch.setattr(fetcher, "summarize_boe",
                        lambda entry, client=None: called.append(1) or "x")
    fetcher.enrich_pending(conn)
    assert called == []
```

Nota: en el primer test elimina la línea `vid_new = ...` (artefacto de redacción); el test queda: sembrar un voto `published=1`, sembrar otro nuevo, y comprobar que `get_unenriched_votes` solo devuelve el nuevo.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetcher_enrichment.py -v`
Expected: FAIL (`get_unenriched_votes` no existe; `fetcher.enrich_pending` no existe).

- [ ] **Step 3: Add DB helpers in `src/db.py`**

Delete these functions (alert-era, ya sin llamadores tras este task):
`get_unpublished_votes`, `mark_vote_published`, `get_unpublished_boe_entries`,
`mark_boe_published`, `get_published_votes_since`, `get_published_boe_entries_since`.

Add:

```python
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
```

- [ ] **Step 4: Rewrite `fetcher.py`**

Replace the whole file with:

```python
#!/usr/bin/env python3
"""
fetcher.py — PolígrafoES v2
Cron: 21:00 diario
Descubre nuevas sesiones del Congreso y el sumario BOE del día, y enriquece
cada item con Haiku 4.5 (resumen llano + juez de matches). NO publica nada:
la publicación es exclusiva del digest semanal (digest.py, lunes 10:30).
"""
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from src.db import (
    init_db, get_conn,
    get_last_session_number, insert_session, insert_vote, insert_vote_groups,
    insert_boe_entry, get_all_program_chunks,
    insert_vote_program_match,
    get_unenriched_votes, set_vote_enrichment,
    get_unenriched_boe_entries, set_boe_enrichment,
)
from src.congreso import (
    fetch_opendata_html, discover_latest_session, download_session_zip,
    parse_vote_xml, compute_resultado,
)
from src.boe import fetch_boe_sumario, extract_boe_items, fetch_boe_entry
from src.matcher import categorize_text, load_categories, top_candidates_per_party
from src.llm import enrich_vote, summarize_boe


def enrich_pending(conn):
    """Enriquece con LLM todos los items pendientes (enriched_at IS NULL).
    Un fallo en un item no detiene el resto: queda NULL y se reintenta mañana."""
    all_chunks = get_all_program_chunks(conn)

    for row in get_unenriched_votes(conn):
        try:
            vote_text = row["titulo"] + " " + (row["texto_expediente"] or "")
            candidates = top_candidates_per_party(vote_text, all_chunks)
            enrichment = enrich_vote(
                {"titulo": row["titulo"], "texto_expediente": row["texto_expediente"] or ""},
                candidates,
            )
            score_by_chunk = {
                c["chunk_id"]: c["score"]
                for cands in candidates.values() for c in cands
            }
            for m in enrichment.matches:
                insert_vote_program_match(
                    conn, row["id"], m.chunk_id, m.party,
                    score_by_chunk.get(m.chunk_id, 0),
                )
            set_vote_enrichment(conn, row["id"], enrichment.resumen, enrichment.que_cambia)
            print(f"  Enriched vote {row['id']}: {enrichment.resumen}")
        except Exception as e:
            print(f"  WARN: enrichment failed for vote {row['id']}: {e}")

    for row in get_unenriched_boe_entries(conn):
        try:
            resumen = summarize_boe(
                {
                    "titulo": row["titulo"],
                    "rango": row["rango"],
                    "departamento": row["departamento"],
                    "texto_preview": row["texto_preview"],
                }
            )
            set_boe_enrichment(conn, row["id"], resumen)
            print(f"  Enriched BOE {row['identificador']}: {resumen[:60]}")
        except Exception as e:
            print(f"  WARN: enrichment failed for BOE {row['identificador']}: {e}")


def run():
    init_db()
    conn = get_conn()
    try:
        categories = load_categories()

        # 1. Descubrir última sesión del Congreso
        print("Fetching Congreso opendata page...")
        html_page = fetch_opendata_html()
        session_num, zip_url, session_date = discover_latest_session(html_page)

        if session_num is None:
            print("No session found on opendata page.")
        else:
            last = get_last_session_number(conn)
            print(f"Latest session on web: {session_num} | Last processed: {last}")

            if session_num > last:
                print(f"New session {session_num} ({session_date}). Downloading ZIP...")
                xml_files = download_session_zip(zip_url)
                print(f"  {len(xml_files)} vote files found.")

                session_id = insert_session(conn, session_num, session_date, zip_url=zip_url)

                for filename, xml_str in xml_files:
                    try:
                        vote = parse_vote_xml(xml_str)
                    except Exception as e:
                        print(f"  WARN: Could not parse {filename}: {e}")
                        continue

                    vote_cats = categorize_text(
                        vote["titulo"] + " " + vote["texto_expediente"], categories
                    )
                    vote_id = insert_vote(
                        conn,
                        session_id,
                        vote["numero_votacion"],
                        vote["titulo"],
                        vote["texto_expediente"],
                        vote["fecha"],
                        categories=vote_cats,
                        a_favor=vote["a_favor"],
                        en_contra=vote["en_contra"],
                        abstenciones=vote["abstenciones"],
                        resultado=compute_resultado(vote["a_favor"], vote["en_contra"]),
                    )
                    insert_vote_groups(conn, vote_id, vote["group_votes"])
                    print(f"  Stored vote {vote['numero_votacion']}: {vote['titulo'][:60]}")
            else:
                print("No new sessions. Nothing to do.")

        # 2. Ingesta BOE del día
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        print(f"\nFetching BOE sumario for {today}...")
        sumario_data = fetch_boe_sumario(today)

        if sumario_data is None:
            print("  BOE not available for today (holiday or weekend).")
        else:
            items = extract_boe_items(sumario_data)
            print(f"  {len(items)} items in sections I+II.")

            for item in items:
                try:
                    entry_info = fetch_boe_entry(item["url_xml"])
                    rango = entry_info["rango"] if entry_info else ""
                    texto_preview = entry_info["texto_preview"] if entry_info else ""

                    cats = categorize_text(item["titulo"] + " " + texto_preview, categories)
                    insert_boe_entry(
                        conn,
                        identificador=item["identificador"],
                        titulo=item["titulo"],
                        rango=rango,
                        departamento=item["departamento"],
                        fecha=item["fecha"],
                        url_xml=item["url_xml"],
                        categories=cats,
                        texto_preview=texto_preview,
                    )
                except Exception as e:
                    print(f"  WARN: Could not process BOE item {item.get('identificador')}: {e}")
                    continue

        # 3. Enriquecimiento LLM (items nuevos + reintentos de días fallidos)
        print("\nEnriching pending items...")
        enrich_pending(conn)

        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
```

In `src/matcher.py`, delete `find_program_matches` (ya sin llamadores).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetcher_enrichment.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Full suite (digest.py aún importa funciones borradas — se arregla en Task 6; si peta la collection de algún test antiguo, anótalo y sigue)**

Run: `python -m pytest -v`
Expected: tests de Tasks 1-5 PASS. (digest.py no tiene tests todavía, no debería romper collection.)

- [ ] **Step 7: Commit**

```bash
git add fetcher.py src/db.py src/matcher.py tests/test_fetcher_enrichment.py
git commit -m "feat(fetcher): enriquecimiento llm al ingestar y eliminacion de alertas diarias"
```

---

### Task 6: Digest v2 — formato legible

**Files:**
- Modify: `digest.py` (reescritura)
- Modify: `src/db.py` (helpers de digest)
- Modify: `src/publisher.py` (borrar formatters de alertas)
- Test: `tests/test_digest.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_digest.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_digest.py -v`
Expected: FAIL (`ImportError: cannot import name 'format_vote_block'`).

- [ ] **Step 3: Add digest DB helpers in `src/db.py`**

```python
def get_votes_for_digest(conn):
    """Todo voto aún no publicado (el digest publica y marca)."""
    return conn.execute(
        """SELECT v.*, s.session_number FROM votes v
           JOIN sessions s ON v.session_id = s.id
           WHERE v.published = 0
           ORDER BY s.session_number, v.vote_number"""
    ).fetchall()


def get_boe_for_digest(conn):
    return conn.execute(
        """SELECT * FROM boe_entries
           WHERE published = 0 AND categories != '[]'
           ORDER BY fecha, id"""
    ).fetchall()


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
```

Also delete `get_vote_program_matches` (sustituida por `get_validated_matches`).

- [ ] **Step 4: Rewrite `digest.py`**

```python
#!/usr/bin/env python3
"""
digest.py — PolígrafoES v2
Cron: lunes 10:30
Publica el digest semanal: plantilla pura sobre datos ya enriquecidos por el
fetcher. Sin llamadas LLM. Publica todo lo published=0 y lo marca — un lunes
fallido se recupera solo en el siguiente run.
"""
import html
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.db import (
    init_db, get_conn,
    get_votes_for_digest, get_boe_for_digest, get_validated_matches,
    get_vote_groups, mark_digest_published,
)
from src.publisher import load_parties, send_message

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL_ID")

TELEGRAM_LIMIT = 4096

_SENSE_ORDER = ["Sí", "No", "Abstención", "No vota"]
_SENSE_LABEL = {"Sí": "A favor", "No": "En contra",
                "Abstención": "Abstención", "No vota": "No votó"}
_RESULT_LABEL = {"aprobada": "✅ APROBADA", "rechazada": "❌ RECHAZADA"}


def format_vote_block(vote, parties):
    """
    vote: dict {titulo, resumen, que_cambia, resultado,
                groups: {code: {voto, divided}}, matches: [{party, text, page_start}]}
    Enriquecido → resumen en cristiano + resultado + consecuencia.
    Sin enriquecer → fallback al título oficial, sin inventar nada.
    """
    if vote.get("resumen"):
        result = _RESULT_LABEL.get(vote.get("resultado"), "")
        header = f"🗳️ <b>{html.escape(vote['resumen'])}</b>"
        if result:
            header += f" — {result}"
        lines = [header, html.escape(vote.get("que_cambia") or "")]
    else:
        titulo = vote["titulo"]
        short = html.escape(titulo[:120]) + ("…" if len(titulo) > 120 else "")
        lines = [f"🗳️ <b>{short}</b>"]

    by_sense = {}
    for code, gv in vote.get("groups", {}).items():
        name = parties.get(code, code)
        if gv.get("divided"):
            name += " (div.)"
        by_sense.setdefault(gv["voto"], []).append(name)
    sense_parts = [
        f"{_SENSE_LABEL[s]}: {', '.join(by_sense[s])}"
        for s in _SENSE_ORDER if s in by_sense
    ]
    if sense_parts:
        lines.append(html.escape(" · ".join(sense_parts)))

    for m in vote.get("matches", []):
        excerpt = html.escape(m["text"][:200]) + ("…" if len(m["text"]) > 200 else "")
        lines.append(
            f"📋 <b>{html.escape(m['party'])}</b> en su programa (p.{m['page_start']}): <i>{excerpt}</i>"
        )

    return "\n".join(line for line in lines if line)


def format_boe_line(entry):
    text = entry.get("resumen") or entry["titulo"]
    short = html.escape(text[:160]) + ("…" if len(text) > 160 else "")
    url = f"https://www.boe.es/diario_boe/txt.php?id={entry['identificador']}"
    return f'· {short} · <a href="{url}">ver</a>'


def build_messages(header, blocks, footer, limit=TELEGRAM_LIMIT):
    """Empaqueta bloques en el mínimo de mensajes ≤ limit, header en el primero,
    footer en el último de cada mensaje para que cada uno se sostenga solo."""
    messages = []
    current = header
    for block in blocks:
        candidate = current + "\n\n" + block
        if len(candidate) + len(footer) + 2 > limit:
            messages.append(current + "\n\n" + footer)
            current = block
        else:
            current = candidate
    messages.append(current + "\n\n" + footer)
    return messages


def run(dry_run=False):
    if not TOKEN or not CHANNEL:
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID must be set in .env")
        sys.exit(1)

    init_db()
    conn = get_conn()
    try:
        parties = load_parties()
        vote_rows = get_votes_for_digest(conn)
        boe_rows = get_boe_for_digest(conn)

        print(f"Digest: {len(vote_rows)} votes, {len(boe_rows)} BOE entries pending.")
        if not vote_rows and not boe_rows:
            print("Nothing to digest this week.")
            return

        blocks = []
        for row in vote_rows:
            groups = {
                g["grupo_code"]: {"voto": g["voto"], "divided": bool(g["divided"])}
                for g in get_vote_groups(conn, row["id"])
            }
            matches = [dict(m) for m in get_validated_matches(conn, row["id"])]
            vote = dict(row)
            vote["groups"] = groups
            vote["matches"] = matches
            blocks.append(format_vote_block(vote, parties))

        if boe_rows:
            boe_lines = ["📜 <b>BOE en cristiano</b>"]
            boe_lines += [format_boe_line(dict(r)) for r in boe_rows]
            blocks.append("\n".join(boe_lines))

        today = datetime.now().strftime("%-d %b") if os.name != "nt" else datetime.now().strftime("%d %b")
        header = (
            f"📊 <b>Congreso — semana hasta el {today}</b>\n"
            f"{len(vote_rows)} votaciones · {len(boe_rows)} leyes BOE relevantes"
        )
        footer = "PolígrafoES"

        messages = build_messages(header, blocks, footer)

        sent_ids = []
        for i, text in enumerate(messages, 1):
            if dry_run:
                print(f"\n--- DRY RUN DIGEST (msg {i}/{len(messages)}) ---")
                print(text)
                print("--- END ---")
                sent_ids.append(0)
                continue
            msg_id = send_message(TOKEN, CHANNEL, text)
            if msg_id:
                sent_ids.append(msg_id)
                print(f"  Sent digest msg {i} -> Telegram msg {msg_id}")
            else:
                print(f"  WARN: Failed to send digest msg {i}")

        if sent_ids and (dry_run or len(sent_ids) == len(messages)):
            mark_digest_published(
                conn,
                [r["id"] for r in vote_rows],
                [r["id"] for r in boe_rows],
                telegram_message_id=sent_ids[-1],
            )
            print("Marked items as published.")
        elif not sent_ids:
            print("WARN: nothing sent; items remain pending for next run.")

        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
```

- [ ] **Step 5: Clean `src/publisher.py`**

Delete `format_vote_alert`, `format_boe_alert`, `VOTO_EMOJI`, `_PROGRAM_PARTY_DISPLAY`. Keep only `load_parties` and `send_message` (plus imports they need: `json`, `requests`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_digest.py -v`
Expected: 8 PASS.

- [ ] **Step 7: Full suite**

Run: `python -m pytest -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add digest.py src/db.py src/publisher.py tests/test_digest.py
git commit -m "feat(digest): formato legible v2 sobre datos enriquecidos, sin llm en el digest"
```

---

### Task 7: Config, smoke test y cierre

**Files:**
- Modify: `.env.example`
- Test: smoke manual con `--dry-run`

- [ ] **Step 1: Update `.env.example`**

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=
ANTHROPIC_API_KEY=
```

- [ ] **Step 2: Full test suite final**

Run: `python -m pytest -v`
Expected: all PASS (≈27 tests).

- [ ] **Step 3: Smoke test del digest sin red Telegram**

Run: `python digest.py --dry-run`
Expected: "Nothing to digest" (DB local vacía) o render del digest sin errores. NO debe pedir `ANTHROPIC_API_KEY` (el digest no usa LLM).

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "chore: anthropic api key en env example"
```

**Pendiente de deploy (manual, protocolo /deploy):** push, `git fetch && git reset --hard` en la Orange Pi, `pip install anthropic pydantic` en la Pi, añadir `ANTHROPIC_API_KEY` al `.env` de la Pi. Los crons no cambian. La migración corre sola en el primer `init_db()`.

---

## Self-review

- **Cobertura del spec:** §3 flujo → Tasks 5-6 · §4 matcher → Tasks 3-5 · §5 esquema → Task 1-2 · §6 llm.py → Task 4 · §7 formato → Task 6 · §8 alertas fuera → Tasks 5-6 · §9 testing → todos · §10 deploy → Task 7. Sin huecos.
- **Cambio consciente vs spec:** el digest selecciona por `published=0` en vez de ventana de 7 días — más robusto (un lunes caído se recupera solo) y elimina la dependencia de `published_messages` de la era alertas. El spec describía la ventana como mecanismo, no como requisito; el resultado visible es idéntico.
- **Consistencia de tipos:** `VoteEnrichment/PartyMatch/BoeSummary` definidos en Task 4 y usados igual en Task 5 · `top_candidates_per_party` devuelve `{party: [{chunk_id, party, score, text, page_start}]}` consistente entre Tasks 3-5 · helpers de db usados en fetcher/digest definidos en Tasks 5-6.
