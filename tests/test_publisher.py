from src.publisher import send_message, load_parties


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_devuelve_message_id_en_exito(monkeypatch):
    monkeypatch.setattr("src.publisher.requests.post",
                        lambda *a, **k: FakeResponse(200, {"ok": True, "result": {"message_id": 7}}))
    assert send_message("t", "c", "hola") == 7


def test_reintenta_tras_429_y_acaba_enviando(monkeypatch):
    respuestas = [
        FakeResponse(429, {"ok": False, "parameters": {"retry_after": 2}}),
        FakeResponse(200, {"ok": True, "result": {"message_id": 9}}),
    ]
    monkeypatch.setattr("src.publisher.requests.post", lambda *a, **k: respuestas.pop(0))
    esperas = []
    assert send_message("t", "c", "hola", sleep=esperas.append) == 9
    assert esperas == [2]  # respeta el retry_after que dice Telegram


def test_se_rinde_tras_agotar_reintentos(monkeypatch):
    monkeypatch.setattr("src.publisher.requests.post",
                        lambda *a, **k: FakeResponse(429, {"ok": False, "parameters": {"retry_after": 1}}))
    assert send_message("t", "c", "hola", max_retries=2, sleep=lambda s: None) is None


def test_error_no_429_no_reintenta(monkeypatch):
    llamadas = []

    def post(*a, **k):
        llamadas.append(1)
        return FakeResponse(400, {"ok": False, "description": "Bad Request: message is too long"})

    monkeypatch.setattr("src.publisher.requests.post", post)
    assert send_message("t", "c", "x", sleep=lambda s: None) is None
    assert len(llamadas) == 1


def test_load_parties_mapea_siglas():
    assert load_parties()["GP"] == "PP"
