# src/matcher.py
import re
import json


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


_STOPWORDS = {
    "para", "como", "este", "esta", "estos", "estas", "sobre",
    "todos", "todas", "entre", "cuando", "hasta", "desde", "según",
    "tanto", "todo", "toda", "donde", "dicha", "dicho",
    "proyecto", "real", "decreto", "artículo", "artículos",
    "medida", "medidas", "españa", "español", "española",
}


def _keywords(text):
    """Extract significant words (5+ chars, not stopwords) from text."""
    words = set(re.findall(r'\b[a-záéíóúüñ]{5,}\b', text.lower()))
    return words - _STOPWORDS


def top_candidates_per_party(vote_text, chunks, per_party=5):
    """
    Pre-filtro para el juez LLM: top-N chunks por partido por score de keywords.
    vote_text: str (titulo + texto_expediente)
    chunks: iterable de dicts/Rows con {id, party, text, page_start}
    Returns: {party: [{chunk_id, party, score, text, page_start}, ...]} orden score desc
    """
    vote_kws = _keywords(vote_text)
    if not vote_kws:
        return {}

    seen = set()
    by_party = {}
    for chunk in chunks:
        key = (chunk["id"], chunk["party"])
        if key in seen:
            continue
        seen.add(key)
        score = len(vote_kws & _keywords(chunk["text"]))
        if score < 1:
            continue
        by_party.setdefault(chunk["party"], []).append({
            "chunk_id": chunk["id"],
            "party": chunk["party"],
            "score": score,
            "text": chunk["text"],
            "page_start": chunk["page_start"],
        })

    return {
        party: sorted(cands, key=lambda c: -c["score"])[:per_party]
        for party, cands in by_party.items()
    }
