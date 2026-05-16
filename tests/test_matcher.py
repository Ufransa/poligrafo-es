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
