# tests/test_matcher.py
import pytest
from src.matcher import categorize_text, load_categories

CATEGORIES = {
    "vivienda": ["vivienda", "alquiler", "hipoteca"],
    "fiscalidad": ["impuesto", "fiscal", "irpf"],
    "empleo": ["empleo", "trabajo", "laboral"],
}


def test_categorize_text_matches_single_category():
    result = categorize_text("Real Decreto sobre fiscalidad del IRPF", CATEGORIES)
    assert "fiscalidad" in result


def test_categorize_text_matches_multiple_categories():
    result = categorize_text("Ley de empleo y medidas fiscales", CATEGORIES)
    assert "empleo" in result
    assert "fiscalidad" in result


def test_categorize_text_returns_empty_for_no_match():
    result = categorize_text("Instrumento de adhesión a convenio marítimo internacional", CATEGORIES)
    assert result == []


def test_categorize_text_is_case_insensitive():
    result = categorize_text("ALQUILER DE VIVIENDAS PROTEGIDAS", CATEGORIES)
    assert "vivienda" in result


def test_categorize_text_matches_keyword_substring():
    result = categorize_text("arrendamientos hipotecarios", CATEGORIES)
    assert "vivienda" in result


def test_load_categories_returns_dict_with_known_keys():
    cats = load_categories()
    assert isinstance(cats, dict)
    assert "vivienda" in cats
    assert "fiscalidad" in cats
    assert len(cats) == 12


# --- top_candidates_per_party (pre-filtro para el juez LLM, v2) ---

from src.matcher import top_candidates_per_party


def _chunk(cid, party, text, page=1):
    return {"id": cid, "party": party, "text": text, "page_start": page}


VOTE_TEXT = "Proposición de ley sobre vivienda y alquiler asequible para jóvenes"


def test_top_candidates_returns_dict_keyed_by_party():
    chunks = [
        _chunk(1, "PP", "garantizar vivienda y alquiler asequible jóvenes"),
        _chunk(2, "PSOE", "vivienda alquiler asequible para todos los jóvenes"),
    ]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert set(result.keys()) == {"PP", "PSOE"}


def test_top_candidates_caps_at_five_per_party():
    chunks = [
        _chunk(i, "PP", f"vivienda alquiler asequible jóvenes propuesta {i}")
        for i in range(1, 9)
    ]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert len(result["PP"]) == 5


def test_top_candidates_sorted_by_score_desc():
    chunks = [
        _chunk(1, "PP", "vivienda"),
        _chunk(2, "PP", "vivienda alquiler asequible jóvenes"),
    ]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert result["PP"][0]["chunk_id"] == 2
    assert result["PP"][0]["score"] > result["PP"][1]["score"]


def test_top_candidates_zero_score_chunks_excluded():
    chunks = [_chunk(1, "VOX", "pesca fluvial trucha sostenible")]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert "VOX" not in result


def test_top_candidates_carry_page_start():
    chunks = [_chunk(7, "PSOE", "vivienda alquiler asequible", page=45)]
    result = top_candidates_per_party(VOTE_TEXT, chunks)
    assert result["PSOE"][0]["page_start"] == 45
