import json
import pytest
from unittest.mock import patch, MagicMock
from src.publisher import format_vote_alert, send_message, load_parties, format_boe_alert

PARTIES = {
    "GP": "PP",
    "GS": "PSOE",
    "GSUMAR": "Sumar",
    "GVOX": "Vox",
    "GR": "ERC",
}

SAMPLE_VOTE = {
    "session_number": 177,
    "numero_votacion": 1,
    "titulo": "Proposición de Ley de regularización extraordinaria",
    "texto_expediente": "Regularización de personas extranjeras con arraigo laboral.",
    "fecha": "30/4/2026",
    "group_votes": {
        "GP":     {"voto": "No",  "total": 137, "divided": False},
        "GS":     {"voto": "Sí",  "total": 120, "divided": False},
        "GSUMAR": {"voto": "Sí",  "total": 31,  "divided": False},
        "GVOX":   {"voto": "No",  "total": 33,  "divided": False},
    }
}


def test_format_vote_alert_contains_title():
    text = format_vote_alert(SAMPLE_VOTE, PARTIES)
    assert "regularización extraordinaria" in text


def test_format_vote_alert_shows_si_emoji_for_yes_votes():
    text = format_vote_alert(SAMPLE_VOTE, PARTIES)
    assert "✅" in text


def test_format_vote_alert_shows_no_emoji_for_no_votes():
    text = format_vote_alert(SAMPLE_VOTE, PARTIES)
    assert "❌" in text


def test_format_vote_alert_shows_party_names():
    text = format_vote_alert(SAMPLE_VOTE, PARTIES)
    assert "PP" in text
    assert "PSOE" in text


def test_format_vote_alert_marks_divided_groups():
    vote = dict(SAMPLE_VOTE)
    vote["group_votes"] = {
        "GP": {"voto": "No", "total": 137, "divided": True},
    }
    text = format_vote_alert(vote, PARTIES)
    assert "div" in text.lower()


def test_format_stays_under_telegram_limit():
    text = format_vote_alert(SAMPLE_VOTE, PARTIES)
    assert len(text) <= 4096


def test_send_message_returns_message_id_on_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 42}}

    with patch("src.publisher.requests.post", return_value=mock_response):
        msg_id = send_message("fake_token", "fake_channel", "Hello")

    assert msg_id == 42


def test_send_message_returns_none_on_failure():
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"ok": False, "description": "Bad Request"}

    with patch("src.publisher.requests.post", return_value=mock_response):
        msg_id = send_message("fake_token", "fake_channel", "Hello")

    assert msg_id is None


SAMPLE_BOE_ENTRY = {
    "identificador": "BOE-A-2026-10511",
    "titulo": "Real Decreto 392/2026 sobre fiscalidad del IRPF",
    "rango": "Real Decreto",
    "departamento": "Ministerio de Hacienda",
    "fecha": "20260515",
    "categories": ["fiscalidad"],
}


def test_format_boe_alert_contains_title():
    text = format_boe_alert(SAMPLE_BOE_ENTRY)
    assert "Real Decreto 392/2026" in text


def test_format_boe_alert_contains_category():
    text = format_boe_alert(SAMPLE_BOE_ENTRY)
    assert "fiscalidad" in text


def test_format_boe_alert_contains_boe_link():
    text = format_boe_alert(SAMPLE_BOE_ENTRY)
    assert "BOE-A-2026-10511" in text


def test_format_boe_alert_under_telegram_limit():
    text = format_boe_alert(SAMPLE_BOE_ENTRY)
    assert len(text) <= 4096


def test_format_boe_alert_works_with_minimal_entry():
    minimal = {
        "identificador": "BOE-A-2026-00001",
        "titulo": "Ley de prueba",
        "fecha": "20260515",
        "categories": [],
    }
    text = format_boe_alert(minimal)
    assert "Ley de prueba" in text
    assert "BOE-A-2026-00001" in text
    assert len(text) <= 4096


SAMPLE_PROGRAM_MATCHES = [
    {"party": "PP",   "text": "El PP propone regulación del mercado de alquiler con medidas para viviendas asequibles de protección oficial."},
    {"party": "VOX", "text": "VOX se opone a la regulación del alquiler porque distorsiona el mercado y reduce la oferta disponible."},
]


def test_format_vote_alert_includes_program_excerpts():
    parties = {"GP": "PP", "GS": "PSOE", "GSUMAR": "Sumar", "GVOX": "Vox"}
    vote = {
        "session_number": 34, "numero_votacion": 1,
        "titulo": "Ley de vivienda", "texto_expediente": "Regulación del alquiler",
        "fecha": "15/5/2026",
        "group_votes": {"GP": {"voto": "Sí", "total": 137, "divided": False}},
    }
    text = format_vote_alert(vote, parties, program_matches=SAMPLE_PROGRAM_MATCHES)
    assert "📋" in text
    assert "PP" in text
    assert "programa" in text


def test_format_vote_alert_without_matches_has_no_program_section():
    parties = {"GP": "PP"}
    vote = {
        "session_number": 34, "numero_votacion": 1,
        "titulo": "Ley de vivienda", "texto_expediente": "",
        "fecha": "15/5/2026",
        "group_votes": {"GP": {"voto": "Sí", "total": 137, "divided": False}},
    }
    text = format_vote_alert(vote, parties)
    assert "📋" not in text


def test_format_vote_alert_with_program_still_under_telegram_limit():
    parties = {"GP": "PP"}
    vote = {
        "session_number": 34, "numero_votacion": 1,
        "titulo": "Título " * 20, "texto_expediente": "Expediente " * 30,
        "fecha": "15/5/2026",
        "group_votes": {"GP": {"voto": "Sí", "total": 137, "divided": False}},
    }
    long_matches = [{"party": "PP", "text": "x " * 500}]
    text = format_vote_alert(vote, parties, program_matches=long_matches)
    assert len(text) <= 4096
