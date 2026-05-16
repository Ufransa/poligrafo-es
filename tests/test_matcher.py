# tests/test_matcher.py
import pytest
from src.matcher import categorize_text, load_categories, find_program_matches

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


SAMPLE_CHUNKS = [
    {"id": 1, "party": "PP",   "category": "vivienda",   "text": "El partido propone regulación del alquiler con viviendas asequibles para todos."},
    {"id": 2, "party": "PSOE", "category": "vivienda",   "text": "Construir viviendas sociales y limitar el precio del alquiler en zonas tensionadas."},
    {"id": 3, "party": "VOX",  "category": "fiscalidad", "text": "Eliminar impuestos sobre la renta y reducir la carga fiscal de las familias."},
]


def test_find_program_matches_returns_matches_above_threshold():
    matches = find_program_matches("Proposición de ley de regulación del alquiler de viviendas", SAMPLE_CHUNKS, min_keywords=2)
    parties = {m["party"] for m in matches}
    assert "PP" in parties
    assert "PSOE" in parties


def test_find_program_matches_excludes_below_threshold():
    matches = find_program_matches("Proposición sobre política exterior y diplomacia", SAMPLE_CHUNKS, min_keywords=2)
    assert matches == []


def test_find_program_matches_sorted_by_score_desc():
    matches = find_program_matches("alquiler vivienda regulación acceso social asequible", SAMPLE_CHUNKS, min_keywords=1)
    if len(matches) >= 2:
        assert matches[0]["score"] >= matches[1]["score"]
