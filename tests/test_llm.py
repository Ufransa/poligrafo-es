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
