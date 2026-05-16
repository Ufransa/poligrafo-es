# src/matcher.py
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
