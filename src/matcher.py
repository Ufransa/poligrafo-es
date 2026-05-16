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


def find_program_matches(vote_text, chunks, min_keywords=2):
    """
    vote_text: str (titulo + texto_expediente of the vote)
    chunks: list/iterable of dicts or Row objects with {id, party, text}
    Returns: list of {chunk_id, party, score, text} sorted by score desc
    """
    vote_kws = _keywords(vote_text)
    if not vote_kws:
        return []

    seen = set()
    results = []
    for chunk in chunks:
        key = (chunk["id"], chunk["party"])
        if key in seen:
            continue
        seen.add(key)
        chunk_kws = _keywords(chunk["text"])
        score = len(vote_kws & chunk_kws)
        if score >= min_keywords:
            results.append(
                {
                    "chunk_id": chunk["id"],
                    "party": chunk["party"],
                    "score": score,
                    "text": chunk["text"],
                }
            )

    return sorted(results, key=lambda x: -x["score"])
