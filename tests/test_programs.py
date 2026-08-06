# tests/test_programs.py
from unittest.mock import patch, MagicMock

CATEGORIES = {
    "vivienda": ["vivienda", "alquiler"],
    "fiscalidad": ["impuesto", "fiscal", "irpf"],
}


def test_text_to_chunks_creates_500_word_chunks():
    from src.programs import _text_to_chunks
    words = ["palabra"] * 1200
    text = " ".join(words)
    chunks = _text_to_chunks(text)
    assert len(chunks) == 3
    assert len(chunks[0].split()) == 500
    assert len(chunks[1].split()) == 500
    assert len(chunks[2].split()) == 200


def test_text_to_chunks_handles_short_text():
    from src.programs import _text_to_chunks
    text = "texto corto aquí"
    chunks = _text_to_chunks(text)
    assert chunks == [text]


def test_text_to_chunks_returns_empty_for_blank():
    from src.programs import _text_to_chunks
    assert _text_to_chunks("") == []
    assert _text_to_chunks("   ") == []


def test_extract_chunks_assigns_correct_party():
    from src.programs import extract_chunks
    page_text = "vivienda alquiler hipoteca " * 200

    mock_page = MagicMock()
    mock_page.extract_text.return_value = page_text

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = lambda s: mock_pdf
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]

    with patch("src.programs.pdfplumber.open", return_value=mock_pdf):
        chunks = extract_chunks(b"fake_pdf", "PP", CATEGORIES)

    assert len(chunks) >= 1
    assert all(c["party"] == "PP" for c in chunks)


def test_extract_chunks_only_returns_categorized_chunks():
    from src.programs import extract_chunks
    # Text that matches vivienda but not fiscalidad
    page_text = "vivienda alquiler medidas de alquiler accesible " * 200

    mock_page = MagicMock()
    mock_page.extract_text.return_value = page_text

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = lambda s: mock_pdf
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]

    with patch("src.programs.pdfplumber.open", return_value=mock_pdf):
        chunks = extract_chunks(b"fake_pdf", "PP", CATEGORIES)

    assert all(c["category"] in CATEGORIES for c in chunks)
    assert any(c["category"] == "vivienda" for c in chunks)


def test_download_pdf_bytes_returns_content_on_200():
    from src.programs import download_pdf_bytes
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"%PDF-1.4 fake content"
    with patch("src.programs.requests.get", return_value=mock_resp):
        result = download_pdf_bytes("https://example.com/file.pdf")
    assert result == b"%PDF-1.4 fake content"


def test_download_pdf_bytes_returns_none_on_404():
    from src.programs import download_pdf_bytes
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("src.programs.requests.get", return_value=mock_resp):
        result = download_pdf_bytes("https://example.com/file.pdf")
    assert result is None


def test_download_pdf_bytes_returns_none_on_network_error():
    from src.programs import download_pdf_bytes
    with patch("src.programs.requests.get", side_effect=Exception("timeout")):
        result = download_pdf_bytes("https://example.com/file.pdf")
    assert result is None


def test_extract_chunks_handles_page_with_no_text():
    from src.programs import extract_chunks
    mock_page = MagicMock()
    mock_page.extract_text.return_value = None  # pdfplumber returns None for image-only pages

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = lambda s: mock_pdf
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]

    with patch("src.programs.pdfplumber.open", return_value=mock_pdf):
        chunks = extract_chunks(b"fake_pdf", "PP", {"vivienda": ["vivienda"]})

    assert chunks == []


def _pdf_falso(paginas):
    """paginas: lista de strings, una por página del PDF."""
    mock_pdf = MagicMock()
    mock_pdf.__enter__ = lambda s: mock_pdf
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = []
    for texto in paginas:
        p = MagicMock()
        p.extract_text.return_value = texto
        mock_pdf.pages.append(p)
    return mock_pdf


def test_page_start_es_la_pagina_real_del_pdf():
    """
    Antes era el índice del trozo: VOX llegaba a 59 en un PDF de ~40 páginas.
    Publicar esa cifra como "p.N" mandaba al lector a una página inexistente.
    """
    from src.programs import extract_chunks
    # 3 páginas de 500 palabras: un chunk por página, con su número.
    paginas = [" ".join(["vivienda alquiler"] * 250) for _ in range(3)]

    with patch("src.programs.pdfplumber.open", return_value=_pdf_falso(paginas)):
        chunks = extract_chunks(b"x", "PP", CATEGORIES)

    paginas_vistas = sorted({c["page_start"] for c in chunks})
    assert paginas_vistas == [1, 2, 3]


def test_page_start_nunca_supera_el_numero_de_paginas():
    from src.programs import extract_chunks
    paginas = [" ".join(["vivienda alquiler"] * 600) for _ in range(2)]  # 2400 palabras

    with patch("src.programs.pdfplumber.open", return_value=_pdf_falso(paginas)):
        chunks = extract_chunks(b"x", "PP", CATEGORIES)

    assert max(c["page_start"] for c in chunks) <= 2
    assert min(c["page_start"] for c in chunks) >= 1
