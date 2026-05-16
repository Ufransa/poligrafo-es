# tests/test_digest.py
import json
import pytest

PARTIES = {"GP": "PP", "GS": "PSOE", "GSUMAR": "Sumar", "GVOX": "Vox"}

SAMPLE_VOTES = [
    {"id": 1, "titulo": "Ley de regulación del alquiler de viviendas protegidas en zonas tensionadas", "fecha": "15/5/2026", "vote_number": 1, "session_number": 34, "session_date": "20260515"},
    {"id": 2, "titulo": "Proposición de ley sobre fiscalidad verde y energías renovables", "fecha": "15/5/2026", "vote_number": 2, "session_number": 34, "session_date": "20260515"},
]

SAMPLE_VOTE_GROUPS = {
    1: {"GP": "No", "GS": "Sí", "GSUMAR": "Sí", "GVOX": "No"},
    2: {"GP": "No", "GS": "Sí", "GSUMAR": "Sí", "GVOX": "No"},
}

SAMPLE_BOE = [
    {"id": 1, "identificador": "BOE-A-2026-001", "titulo": "Real Decreto sobre regulación de arrendamientos urbanos", "categories": '["vivienda"]', "fecha": "20260515"},
    {"id": 2, "identificador": "BOE-A-2026-002", "titulo": "Ley de medidas fiscales y tributarias para 2026", "categories": '["fiscalidad"]', "fecha": "20260515"},
]


def test_format_digest_contains_header():
    from digest import format_digest
    text = format_digest(SAMPLE_VOTES, SAMPLE_VOTE_GROUPS, SAMPLE_BOE, "15/05/2026", PARTIES)
    assert "📊" in text
    assert "15/05/2026" in text


def test_format_digest_contains_vote_titles():
    from digest import format_digest
    text = format_digest(SAMPLE_VOTES, SAMPLE_VOTE_GROUPS, SAMPLE_BOE, "15/05/2026", PARTIES)
    assert "alquiler" in text.lower() or "regulación" in text.lower()


def test_format_digest_contains_vote_party_emojis():
    from digest import format_digest
    text = format_digest(SAMPLE_VOTES, SAMPLE_VOTE_GROUPS, SAMPLE_BOE, "15/05/2026", PARTIES)
    assert "✅" in text
    assert "❌" in text


def test_format_digest_contains_boe_section():
    from digest import format_digest
    text = format_digest(SAMPLE_VOTES, SAMPLE_VOTE_GROUPS, SAMPLE_BOE, "15/05/2026", PARTIES)
    assert "📜" in text
    assert "BOE-A-2026-001" in text or "arrendamientos" in text.lower()


def test_format_digest_empty_boe_omits_boe_section():
    from digest import format_digest
    text = format_digest(SAMPLE_VOTES, SAMPLE_VOTE_GROUPS, [], "15/05/2026", PARTIES)
    assert "📜" not in text


def test_format_digest_respects_telegram_limit():
    from digest import format_digest
    # 50 votes to stress-test truncation
    many_votes = [
        {"id": i, "titulo": f"Ley número {i} sobre materia legislativa de larga denominación", "fecha": "15/5/2026", "vote_number": i, "session_number": 34, "session_date": "20260515"}
        for i in range(1, 51)
    ]
    many_groups = {i: {"GP": "Sí", "GS": "No", "GSUMAR": "Sí", "GVOX": "No"} for i in range(1, 51)}
    many_boe = [
        {"id": i, "identificador": f"BOE-A-2026-{i:03d}", "titulo": f"Real Decreto número {i} sobre materia normativa", "categories": '["fiscalidad"]', "fecha": "20260515"}
        for i in range(1, 31)
    ]
    texts = format_digest(many_votes, many_groups, many_boe, "15/05/2026", PARTIES)
    # format_digest returns a list of strings when splitting
    if isinstance(texts, list):
        for t in texts:
            assert len(t) <= 4096
    else:
        assert len(texts) <= 4096


def test_format_digest_footer():
    from digest import format_digest
    text = format_digest(SAMPLE_VOTES, SAMPLE_VOTE_GROUPS, SAMPLE_BOE, "15/05/2026", PARTIES)
    result = text if isinstance(text, str) else "\n".join(text)
    assert "PolígrafoES" in result
