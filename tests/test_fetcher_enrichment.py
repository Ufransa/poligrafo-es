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


def _seed_vote(conn, session_number=300, published=0):
    sid = insert_session(conn, session_number, "20260611")
    vid = insert_vote(conn, sid, 1, "Proposición de Ley de vivienda",
                      "alquiler asequible jóvenes", "11/6/2026",
                      a_favor=200, en_contra=140, abstenciones=10, resultado="aprobada",
                      clase="sustantiva", expediente_key="alquiler asequible jóvenes")
    conn.execute("UPDATE votes SET published=? WHERE id=?", (published, vid))
    conn.commit()
    return vid


def test_unenriched_votes_excludes_already_published(conn):
    _seed_vote(conn, session_number=300, published=1)  # voto pre-v2 ya emitido como alerta
    vid_new = _seed_vote(conn, session_number=301, published=0)
    rows = get_unenriched_votes(conn)
    assert [r["id"] for r in rows] == [vid_new]


def test_enrich_pending_stores_summary_and_matches(conn, monkeypatch):
    vid = _seed_vote(conn)
    cid = insert_program_chunk(conn, "PSOE", "vivienda", 45,
                               "vivienda alquiler asequible jóvenes garantizado")

    def fake_enrich(expediente, candidates, client=None):
        return VoteEnrichment(
            resumen="Ley de vivienda", que_cambia="Cambia X.",
            matches=[PartyMatch(party="PSOE", chunk_id=cid,
                                promesa="alquiler asequible para jóvenes",
                                veredicto="cumple")],
        )

    monkeypatch.setattr(fetcher, "enrich_expediente", fake_enrich)
    fetcher.enrich_pending(conn)

    row = conn.execute("SELECT * FROM votes WHERE id=?", (vid,)).fetchone()
    assert row["resumen"] == "Ley de vivienda"
    assert row["enriched_at"] is not None
    matches = conn.execute("SELECT * FROM vote_program_matches WHERE vote_id=?", (vid,)).fetchall()
    assert len(matches) == 1
    assert matches[0]["chunk_id"] == cid
    assert matches[0]["veredicto"] == "cumple"


def test_enrich_failure_leaves_item_pending(conn, monkeypatch):
    vid = _seed_vote(conn)

    def boom(expediente, candidates, client=None):
        raise RuntimeError("api caída")

    monkeypatch.setattr(fetcher, "enrich_expediente", boom)
    fetcher.enrich_pending(conn)  # no debe lanzar

    row = conn.execute("SELECT * FROM votes WHERE id=?", (vid,)).fetchone()
    assert row["enriched_at"] is None  # se reintenta en el siguiente run


def test_enrich_boe_stores_summary(conn, monkeypatch):
    eid = insert_boe_entry(conn, "BOE-A-2026-1", "Real Decreto-ley de ayudas",
                           "Real Decreto-ley", "Min. Vivienda", "2026-06-11",
                           "http://x", ["vivienda"], "texto preview")

    monkeypatch.setattr(fetcher, "summarize_boe",
                        lambda entry, client=None: "Ayudas al alquiler joven")
    fetcher.enrich_pending(conn)

    row = conn.execute("SELECT * FROM boe_entries WHERE id=?", (eid,)).fetchone()
    assert row["resumen"] == "Ayudas al alquiler joven"
    assert row["enriched_at"] is not None


def test_uncategorized_boe_not_enriched(conn, monkeypatch):
    insert_boe_entry(conn, "BOE-A-2026-2", "Nombramientos varios",
                     "Orden", "Presidencia", "2026-06-11",
                     "http://x", [], "")
    called = []
    monkeypatch.setattr(fetcher, "summarize_boe",
                        lambda entry, client=None: called.append(1) or "x")
    fetcher.enrich_pending(conn)
    assert called == []
