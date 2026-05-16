# src/programs.py
import io

import pdfplumber
import requests

from src.matcher import categorize_text

TIMEOUT = 30
WORDS_PER_CHUNK = 500

PARTY_PDFS = {
    "PP": "https://www.pp.es/storage/2023/07/programa_electoral_pp_23j_feijoo_2023.pdf",
    "PSOE": "https://www.psoe.es/media-content/2023/07/PROGRAMA_ELECTORAL-GENERALES-2023.pdf",
    "SUMAR": "https://www.newtral.es/wp-content/uploads/2023/07/Programa_electoral_sumar_23j_2023.pdf",
    "VOX": "https://files.mediaset.es/file/2023/0707/15/programa-vox-completo-pdf.pdf",
}


def download_pdf_bytes(url):
    """Download PDF from URL. Returns bytes or None on any failure."""
    try:
        r = requests.get(
            url, timeout=(10, 120), headers={"User-Agent": "PoligrafoES/1.0"}
        )
    except Exception:
        return None
    if r.status_code != 200:
        return None
    return r.content


def _text_to_chunks(text):
    """Split text into ~WORDS_PER_CHUNK word chunks. Returns list of strings."""
    words = text.split()
    if not words:
        return []
    return [
        " ".join(words[i : i + WORDS_PER_CHUNK])
        for i in range(0, len(words), WORDS_PER_CHUNK)
    ]


def extract_chunks(pdf_bytes, party, categories):
    """
    Extract categorized text chunks from PDF bytes.
    Returns list of {party, category, page_start, text}.
    page_start: 1-indexed chunk sequence number (not PDF page number — all pages are concatenated before chunking).
    Chunks that match no category are discarded.
    A single chunk that matches N categories produces N dicts — one per matched category.
    """
    all_text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            all_text += (page.extract_text() or "") + " "

    chunks = []
    for idx, chunk_text in enumerate(_text_to_chunks(all_text.strip())):
        cats = categorize_text(chunk_text, categories)
        for cat in cats:
            chunks.append(
                {
                    "party": party,
                    "category": cat,
                    "page_start": idx + 1,
                    "text": chunk_text,
                }
            )
    return chunks
