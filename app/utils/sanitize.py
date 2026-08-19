import bleach


def sanitize_text(value: str, max_length: int = 500) -> str:
    cleaned = bleach.clean(value.strip(), tags=[], strip=True)
    return cleaned[:max_length]
