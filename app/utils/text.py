def normalize_text(text: str) -> str:
    normalized = " ".join(text.lower().replace("ё", "е").split())
    return normalized
