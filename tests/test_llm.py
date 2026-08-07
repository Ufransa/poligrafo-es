from src.llm import (enrich_expediente, summarize_boe, build_expediente_prompt,
                     VoteEnrichment, PartyMatch, BoeSummary)


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


EXPEDIENTE = {
    "texto_expediente": "Proyecto de Ley de discapacidad",
    "titulo": "Dictámenes de Comisiones sobre iniciativas legislativas.",
    "resultado": "aprobada",
    "a_favor": 179,
    "en_contra": 33,
    "enmiendas": [
        {"grupo": "Junts", "detalle": "Enmienda 174.", "resultado": "rechazada"},
        {"grupo": "PNV", "detalle": "Enmienda 14.", "resultado": "rechazada"},
    ],
}

CANDIDATES = {
    "PSOE": [{"chunk_id": 10, "party": "PSOE", "score": 0.87,
              "text": "Subiremos el SMI hasta el 60% del salario medio", "page_start": 45}],
    "VOX": [{"chunk_id": 20, "party": "VOX", "score": 0.82,
             "text": "Reforma fiscal integral", "page_start": 12}],
}


def test_prompt_incluye_resultado_y_recuento_de_enmiendas():
    prompt = build_expediente_prompt(EXPEDIENTE, {})
    assert "aprobada" in prompt
    assert "179" in prompt
    assert "Junts" in prompt
    assert "2 votaciones de enmiendas" in prompt


def test_match_sin_veredicto_es_valido_pero_se_descarta_al_publicar():
    m = PartyMatch(party="PP", chunk_id=None, promesa="", veredicto=None)
    assert m.chunk_id is None
    assert m.veredicto is None


def test_match_con_veredicto_conserva_la_promesa():
    m = PartyMatch(party="PP", chunk_id=12,
                   promesa="blindar por ley el apoyo a la discapacidad",
                   veredicto="incumple")
    assert m.veredicto == "incumple"
    assert "blindar" in m.promesa


def test_enrich_expediente_devuelve_el_enriquecimiento():
    parsed = VoteEnrichment(
        resumen="Ley de discapacidad aprobada",
        que_cambia="Amplía prestaciones y accesibilidad universal.",
        matches=[PartyMatch(party="PSOE", chunk_id=10, promesa="subir el SMI",
                            veredicto="cumple")],
    )
    client = FakeClient(parsed)
    result = enrich_expediente(EXPEDIENTE, CANDIDATES, client=client)
    assert result.resumen == "Ley de discapacidad aprobada"
    assert result.matches[0].chunk_id == 10


def test_enrich_expediente_descarta_chunk_ids_alucinados():
    parsed = VoteEnrichment(
        resumen="x", que_cambia="y",
        matches=[
            PartyMatch(party="PSOE", chunk_id=10, promesa="p", veredicto="cumple"),
            PartyMatch(party="VOX", chunk_id=999, promesa="p", veredicto="incumple"),
            PartyMatch(party="PP", chunk_id=None, promesa="", veredicto=None),
        ],
    )
    client = FakeClient(parsed)
    result = enrich_expediente(EXPEDIENTE, CANDIDATES, client=client)
    assert [m.chunk_id for m in result.matches] == [10]


def test_enrich_expediente_descarta_matches_sin_veredicto():
    parsed = VoteEnrichment(
        resumen="x", que_cambia="y",
        matches=[
            PartyMatch(party="PSOE", chunk_id=10, promesa="p", veredicto=None),
            PartyMatch(party="VOX", chunk_id=20, promesa="p", veredicto="incumple"),
        ],
    )
    client = FakeClient(parsed)
    result = enrich_expediente(EXPEDIENTE, CANDIDATES, client=client)
    assert [m.chunk_id for m in result.matches] == [20]


def test_enrich_expediente_prompt_lleva_chunk_ids_y_modelo():
    parsed = VoteEnrichment(resumen="x", que_cambia="y", matches=[])
    client = FakeClient(parsed)
    enrich_expediente(EXPEDIENTE, CANDIDATES, client=client)
    kwargs = client.messages.last_kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    user_content = kwargs["messages"][0]["content"]
    assert "chunk_id=10" in user_content
    assert "chunk_id=20" in user_content
    assert "Proyecto de Ley de discapacidad" in user_content


def test_summarize_boe_returns_string():
    client = FakeClient(BoeSummary(resumen="Nuevas ayudas al alquiler joven de hasta 250€/mes"))
    entry = {"titulo": "Real Decreto 123/2026...", "rango": "Real Decreto",
             "departamento": "Ministerio de Vivienda", "texto_preview": "..."}
    result = summarize_boe(entry, client=client)
    assert result == "Nuevas ayudas al alquiler joven de hasta 250€/mes"


def test_prompt_incluye_el_sentido_de_voto_de_cada_partido():
    """
    Sin esto el juez adivinaba: le pedíamos comparar la promesa con el sentido
    de voto sin decirle cómo había votado nadie.
    """
    exp = {**EXPEDIENTE, "votos_por_partido": {
        "PP": "Abstención", "PSOE": "Sí", "Vox": "No"}}
    prompt = build_expediente_prompt(exp, {})
    assert "PP: Abstención" in prompt
    assert "PSOE: Sí" in prompt
    assert "Vox: No" in prompt


def test_prompt_avisa_de_que_una_enmienda_a_la_totalidad_invierte_el_voto():
    exp = {**EXPEDIENTE,
           "titulo": "Enmiendas a la totalidad de devolución.",
           "votos_por_partido": {"PP": "Sí"}}
    prompt = build_expediente_prompt(exp, {})
    assert "invierte" in prompt.lower()


def test_prompt_sin_votos_no_revienta():
    prompt = build_expediente_prompt(EXPEDIENTE, {})
    assert "aprobada" in prompt


class FakeMessagesSecuencia:
    """Devuelve una respuesta distinta por llamada, para simular la variabilidad
    real del modelo entre pasadas idénticas."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = 0

    def parse(self, **kwargs):
        self.llamadas += 1
        return FakeResponse(self._respuestas.pop(0))


class FakeClientSecuencia:
    def __init__(self, respuestas):
        self.messages = FakeMessagesSecuencia(respuestas)


def _enriquecimiento(*matches):
    return VoteEnrichment(resumen="x", que_cambia="y", matches=list(matches))


def test_descarta_el_veredicto_que_cambia_entre_pasadas():
    """
    Medido en producción: en una ley con solape débil, dos ejecuciones idénticas
    daban 'cumple' e 'incumple' para la misma promesa. Un veredicto que no se
    reproduce no es un veredicto, es ruido.
    """
    client = FakeClientSecuencia([
        _enriquecimiento(PartyMatch(party="ERC", chunk_id=10, promesa="p", veredicto="cumple")),
        _enriquecimiento(PartyMatch(party="ERC", chunk_id=10, promesa="p", veredicto="incumple")),
    ])
    result = enrich_expediente(EXPEDIENTE, CANDIDATES, client=client)
    assert result.matches == []
    assert client.messages.llamadas == 2


def test_conserva_el_veredicto_que_se_repite():
    client = FakeClientSecuencia([
        _enriquecimiento(PartyMatch(party="PSOE", chunk_id=10, promesa="p", veredicto="cumple")),
        _enriquecimiento(PartyMatch(party="PSOE", chunk_id=10, promesa="otra redaccion", veredicto="cumple")),
    ])
    result = enrich_expediente(EXPEDIENTE, CANDIDATES, client=client)
    assert [(m.party, m.veredicto) for m in result.matches] == [("PSOE", "cumple")]


def test_descarta_el_match_que_solo_aparece_en_una_pasada():
    client = FakeClientSecuencia([
        _enriquecimiento(PartyMatch(party="PSOE", chunk_id=10, promesa="p", veredicto="cumple"),
                         PartyMatch(party="VOX", chunk_id=20, promesa="p", veredicto="incumple")),
        _enriquecimiento(PartyMatch(party="PSOE", chunk_id=10, promesa="p", veredicto="cumple")),
    ])
    result = enrich_expediente(EXPEDIENTE, CANDIDATES, client=client)
    assert [m.chunk_id for m in result.matches] == [10]
