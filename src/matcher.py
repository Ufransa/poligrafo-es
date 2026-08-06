# src/matcher.py
import json

import numpy as np

from src.embeddings import embed_texts, from_blob

# Medido sobre los 540 textos únicos: e5-small comprime las similitudes en
# 0.80-0.89, así que el 0.80 previsto dejaba pasar el 100%. A 0.85 quedaban
# 15-60 candidatos por ley y el juez seguía convirtiendo promesas genéricas en
# veredictos; a 0.87 quedan 5-9, todos con solape real de materia.
MIN_SIMILARITY = 0.87


def load_categories(config_path="config/categories.json"):
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def categorize_text(text, categories):
    """
    text: string to search (e.g., titulo + texto_expediente)
    categories: dict {category_key: [keyword, ...]} from categories.json
    Returns: list of matching category keys (any keyword present in text)
    """
    text_lower = text.lower()
    return [
        cat for cat, keywords in categories.items()
        if any(kw in text_lower for kw in keywords)
    ]


def top_candidates_per_party(vote_text, chunks, per_party=3, min_similarity=MIN_SIMILARITY):
    """
    Top-N chunks por partido por similitud coseno con el texto de la votación.

    A diferencia del prefiltro por keywords que sustituye, no premia a los
    partidos con programas largos: el umbral es absoluto, no relativo.
    """
    # program_chunks guarda una fila por (texto, categoría), así que un extracto
    # que toca 10 categorías llega aquí 10 veces: 540 textos reales en 2646 filas.
    # Sin deduplicar, el top-N de un partido son N copias de la misma promesa.
    vistos = set()
    unicos = []
    for c in chunks:
        if not c["embedding"]:
            continue
        clave = (c["party"], c["text"])
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(c)
    chunks = unicos
    if not chunks:
        return {}

    consulta = embed_texts([vote_text], "query: ")[0]
    matriz = np.vstack([from_blob(c["embedding"]) for c in chunks])
    similitudes = matriz @ consulta

    by_party = {}
    for chunk, sim in zip(chunks, similitudes):
        if sim < min_similarity:
            continue
        by_party.setdefault(chunk["party"], []).append({
            "chunk_id": chunk["id"],
            "party": chunk["party"],
            "score": float(sim),
            "text": chunk["text"],
            "page_start": chunk["page_start"],
        })

    return {
        party: sorted(cands, key=lambda c: -c["score"])[:per_party]
        for party, cands in by_party.items()
    }
