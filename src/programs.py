# src/programs.py
import io

import pdfplumber
import requests

from src.matcher import categorize_text

TIMEOUT = 30
WORDS_PER_CHUNK = 500

# Programas de las generales del 23J de 2023 (legislatura XV, la que se vota).
# Las claves deben coincidir EXACTAMENTE con los valores de config/parties.json:
# el juez cruza la promesa con el sentido de voto casando por ese nombre, y
# "SUMAR" contra "Sumar" le obligaba a adivinar.
PARTY_PDFS = {
    "PP": "https://www.pp.es/storage/2023/07/programa_electoral_pp_23j_feijoo_2023.pdf",
    # El dominio del PSOE está tras Cloudflare y devuelve 0 bytes: espejo de prensa.
    "PSOE": "https://www.elnacional.cat/uploads/s1/42/65/82/06/programa-electoral-psoe-eleccions-generals-2023-pedro-sanchez.pdf",
    "Sumar": "https://www.newtral.es/wp-content/uploads/2023/07/Programa_electoral_sumar_23j_2023.pdf",
    "Vox": "https://files.mediaset.es/file/2023/0707/15/programa-vox-completo-pdf.pdf",
    # ERC y Junts publican solo en catalán. El modelo de embeddings es
    # multilingüe y cruza idiomas, y el juez parafrasea la promesa en castellano.
    "ERC": "https://defensacatalunya.esquerrarepublicana.cat/documents/e2023-programa.pdf",
    "Junts": "https://img.beteve.cat/wp-content/uploads/2023/07/programa-junts-per-catalunya-eleccions-generals-2023.pdf",
    "EH Bildu": "https://www.elnacional.cat/uploads/s1/42/81/42/33/programa-electoral-eh-bildu-eleccions-generals-2023.pdf",
    "PNV": "https://www.eaj-pnv.eus/es/adjuntos-documentos/20945/pdf/con-voz-propia-programa-electoral-23-j",
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
    content = r.content
    if not content.startswith(b"%PDF"):
        return None
    return content


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
    page_start: número de página REAL del PDF donde empieza el trozo (1-indexed).
    Antes era el índice del trozo, así que la cita "(p.N)" que se publicaba
    apuntaba a una página que a menudo ni existía.
    Chunks that match no category are discarded.
    A single chunk that matches N categories produces N dicts — one per matched category.
    """
    # Se arrastra la página de cada palabra para saber en cuál empieza cada trozo.
    palabras: list[str] = []
    paginas: list[int] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for num_pagina, page in enumerate(pdf.pages, start=1):
            for palabra in (page.extract_text() or "").split():
                palabras.append(palabra)
                paginas.append(num_pagina)

    chunks = []
    for i in range(0, len(palabras), WORDS_PER_CHUNK):
        chunk_text = " ".join(palabras[i:i + WORDS_PER_CHUNK])
        cats = categorize_text(chunk_text, categories)
        for cat in cats:
            chunks.append(
                {
                    "party": party,
                    "category": cat,
                    "page_start": paginas[i],
                    "text": chunk_text,
                }
            )
    return chunks
