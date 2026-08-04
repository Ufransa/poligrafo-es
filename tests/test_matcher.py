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


# --- top_candidates_per_party (similitud coseno sobre embeddings, v3) ---

import numpy as np
from src.matcher import top_candidates_per_party


def _fake_chunk(cid, party, text, vector):
    v = np.array(vector, dtype=np.float32)
    v = v / np.linalg.norm(v)
    return {"id": cid, "party": party, "text": text, "page_start": 10,
            "embedding": v.tobytes()}


def test_devuelve_candidatos_por_encima_del_umbral(monkeypatch):
    # El voto apunta en la dirección [1,0]; el chunk A coincide, el B es ortogonal.
    monkeypatch.setattr("src.matcher.embed_texts",
                        lambda textos, prefijo: np.array([[1.0, 0.0]], dtype=np.float32))
    chunks = [
        _fake_chunk(1, "PP", "accesibilidad universal", [1.0, 0.02]),
        _fake_chunk(2, "PP", "política pesquera", [0.0, 1.0]),
    ]
    res = top_candidates_per_party("ley de discapacidad", chunks, min_similarity=0.80)
    assert [c["chunk_id"] for c in res["PP"]] == [1]


def test_no_hay_sesgo_por_numero_de_chunks(monkeypatch):
    # PSOE tiene 5 chunks irrelevantes, PNV tiene 1 relevante. Debe ganar PNV.
    monkeypatch.setattr("src.matcher.embed_texts",
                        lambda textos, prefijo: np.array([[1.0, 0.0]], dtype=np.float32))
    chunks = [_fake_chunk(i, "PSOE", "irrelevante", [0.0, 1.0]) for i in range(5)]
    chunks.append(_fake_chunk(99, "PNV", "accesibilidad", [1.0, 0.01]))
    res = top_candidates_per_party("ley de discapacidad", chunks, min_similarity=0.80)
    assert "PSOE" not in res
    assert [c["chunk_id"] for c in res["PNV"]] == [99]


def test_deduplica_extractos_repetidos(monkeypatch):
    # La ingesta repitió cada extracto ~5 veces; el top-N no puede ser N copias
    # de la misma promesa.
    monkeypatch.setattr("src.matcher.embed_texts",
                        lambda textos, prefijo: np.array([[1.0, 0.0]], dtype=np.float32))
    chunks = [_fake_chunk(i, "PP", "accesibilidad universal", [1.0, 0.01]) for i in range(5)]
    chunks.append(_fake_chunk(99, "PP", "otra promesa distinta", [1.0, 0.02]))
    res = top_candidates_per_party("ley", chunks, per_party=3, min_similarity=0.80)
    assert len(res["PP"]) == 2
    assert {c["text"] for c in res["PP"]} == {"accesibilidad universal", "otra promesa distinta"}


def test_limita_a_per_party_candidatos(monkeypatch):
    monkeypatch.setattr("src.matcher.embed_texts",
                        lambda textos, prefijo: np.array([[1.0, 0.0]], dtype=np.float32))
    chunks = [_fake_chunk(i, "PP", f"texto {i}", [1.0, 0.01 * i]) for i in range(10)]
    res = top_candidates_per_party("ley", chunks, per_party=3, min_similarity=0.80)
    assert len(res["PP"]) == 3
