import re

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Turn a ministry name into a stable, URL-safe, dedupe-friendly key.

    e.g. "Ministry of New and Renewable Energy " -> "ministry-of-new-and-renewable-energy"
    """
    slug = _SLUG_INVALID_CHARS.sub("-", text.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"Cannot slugify empty/non-alphanumeric text: {text!r}")
    return slug
