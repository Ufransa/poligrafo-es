import json
import pytest
from unittest.mock import patch, MagicMock
from src.publisher import format_vote_alert, send_message, load_parties

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
