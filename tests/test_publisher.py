from unittest.mock import patch, MagicMock
from src.publisher import send_message, load_parties


def test_load_parties_returns_known_codes():
    parties = load_parties()
    assert parties["GP"] == "PP"
    assert parties["GS"] == "PSOE"


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
