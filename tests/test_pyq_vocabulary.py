"""The tagger's vocabulary file must not drift from the project's real areas.

scripts/tag_pyq.py rejects anything the model returns that is not in this file,
so a stale copy would silently reject *correct* areas — and the whole design
rests on questions and articles carrying byte-identical strings, since that is
what makes matching a join rather than fuzzy overlap.
"""

from pathlib import Path

from pib_agent.config import PROJECT_ROOT
from pib_agent.syllabus import GS_AREAS

VOCAB = Path(PROJECT_ROOT) / "data" / "pyq" / "vocabulary.txt"


def _terms() -> list[str]:
    lines = VOCAB.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def test_vocabulary_file_matches_the_syllabus_exactly():
    assert _terms() == list(GS_AREAS), (
        "data/pyq/vocabulary.txt is out of date with syllabus.py — "
        "regenerate it (see data/pyq/README.md)"
    )


def test_every_term_is_paper_prefixed():
    """tag_pyq scopes the vocabulary by GS paper with a 'GS Paper N' match."""
    assert all(term.startswith("GS Paper ") for term in _terms())
