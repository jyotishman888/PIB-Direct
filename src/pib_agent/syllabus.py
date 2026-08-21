"""The canonical UPSC General Studies syllabus, as a closed vocabulary.

Single source of truth for both the enrichment prompt and the study pass.
Before this existed the model was told to format tags as
"GS Paper N - Area: Sub-topic", and it invented the sub-topic freely — 1090
distinct tags across 486 articles, 991 of them used exactly once. That is
free text wearing a taxonomy's clothes: unusable as an index, and no stable
target for anything (topic browsing, PYQ mapping) to join against.

The areas below are typed as Literals in the generation schemas, so the
structured-output API constrains the model to select rather than invent.
"""

import difflib
import re
from typing import Literal

# Mirrors the official GS syllabus headings. Deliberately colon-free: a colon
# is what invited the free-form suffix in the first place.
GSArea = Literal[
    "GS Paper 1 - Art and Culture",
    "GS Paper 1 - Modern Indian History",
    "GS Paper 1 - Freedom Struggle",
    "GS Paper 1 - Post-Independence Consolidation",
    "GS Paper 1 - World History",
    "GS Paper 1 - Indian Society",
    "GS Paper 1 - Social Empowerment",
    "GS Paper 1 - Urbanisation",
    "GS Paper 1 - World Physical Geography",
    "GS Paper 1 - Resource Distribution",
    "GS Paper 1 - Geophysical Phenomena",
    "GS Paper 2 - Polity and Constitution",
    "GS Paper 2 - Governance",
    "GS Paper 2 - Social Justice",
    "GS Paper 2 - Welfare Schemes",
    "GS Paper 2 - Health",
    "GS Paper 2 - Education",
    "GS Paper 2 - Government Policies and Interventions",
    "GS Paper 2 - Federalism",
    "GS Paper 2 - Judiciary",
    "GS Paper 2 - Human Resources",
    "GS Paper 2 - Statutory and Regulatory Bodies",
    "GS Paper 2 - International Relations",
    "GS Paper 3 - Economy",
    "GS Paper 3 - Agriculture",
    "GS Paper 3 - Infrastructure",
    "GS Paper 3 - Science and Technology",
    "GS Paper 3 - Environment and Biodiversity",
    "GS Paper 3 - Disaster Management",
    "GS Paper 3 - Internal Security",
    "GS Paper 4 - Ethics and Integrity",
    "GS Paper 4 - Probity in Governance",
]

GS_AREAS: tuple[str, ...] = GSArea.__args__

# Prelims subject areas, used for point-level tagging in the study pass.
PrelimsSubject = Literal[
    "History",
    "Art and Culture",
    "Geography",
    "Polity",
    "Economy",
    "Environment",
    "Science and Technology",
    "Agriculture",
    "International Relations",
    "Government Schemes",
    "Society",
    "Security",
    "Ethics",
]

PRELIMS_SUBJECTS: tuple[str, ...] = PrelimsSubject.__args__


_STOPWORDS = {"and", "of", "for", "in", "the", "gs", "paper"}

# Legacy wordings that share too few words with their canonical area for any
# scoring to connect them.
_ALIASES = {
    "indian culture heritage": "GS Paper 1 - Art and Culture",
    "culture heritage": "GS Paper 1 - Art and Culture",
    "indian culture": "GS Paper 1 - Art and Culture",
    "centre state relations federalism": "GS Paper 2 - Federalism",
}


def _words(value: str) -> set[str]:
    cleaned = value.split(":")[0].replace("&", "and").replace("-", " ").lower()
    return {w for w in cleaned.split() if w.isalpha() and w not in _STOPWORDS}


def _paper_of(value: str) -> str | None:
    match = re.search(r"paper\s*([1-4])", value.lower())
    return match.group(1) if match else None


def normalise_area(value: str) -> str | None:
    """Best-effort map of a legacy free-text tag onto a canonical area.

    Handles the shapes the old prompt produced: a trailing ": Sub-topic"
    suffix, near-miss wording ("Environment" for "Environment and
    Biodiversity"), and "&" for "and". Returns None when nothing matches well
    enough, so a bad guess is never written in place of a known-unknown.
    """
    legacy = _words(value)
    if not legacy:
        return None

    alias = _ALIASES.get(" ".join(sorted(legacy)))
    if alias:
        return alias
    for key, area in _ALIASES.items():
        if set(key.split()) <= legacy:
            return area

    paper = _paper_of(value)
    best, best_score = None, 0.0
    for area in GS_AREAS:
        if paper and _paper_of(area) != paper:
            continue  # never cross papers; "Health" belongs to GS2 alone
        canonical = _words(area)
        if not canonical:
            continue
        shared = len(canonical & legacy)
        # Forward: how much of the canonical name the legacy tag contains
        # ("welfare schemes for vulnerable sections" -> "Welfare Schemes").
        # Reverse: how much of the legacy tag the canonical name covers, which
        # is what catches short prefixes ("Environment" -> "Environment and
        # Biodiversity"). The paper constraint above keeps this from being
        # promiscuous.
        containment = max(shared / len(canonical), shared / len(legacy))
        ratio = difflib.SequenceMatcher(
            None, " ".join(sorted(legacy)), " ".join(sorted(canonical))
        ).ratio()
        score = max(containment, ratio)
        if score > best_score:
            best, best_score = area, score
    return best if best_score >= 0.7 else None


def normalise_subject(value: str) -> str | None:
    """Map a free-text Prelims subject onto the fixed list, or None."""
    words = _words(value)
    if not words:
        return None
    best, best_score = None, 0.0
    for subject in PRELIMS_SUBJECTS:
        canonical = _words(subject)
        shared = len(canonical & words)
        score = max(shared / len(canonical), shared / len(words))
        if score > best_score:
            best, best_score = subject, score
    return best if best_score >= 0.7 else None


def area_slug(area: str) -> str:
    """URL-safe slug for a canonical area: 'GS Paper 3 - Economy' -> 'gs-paper-3-economy'.

    Derived rather than stored: the vocabulary is a fixed tuple, so the mapping
    is a pure function and needs no column or migration. Slugs exist so a
    shared link reads as a topic instead of a percent-encoded sentence.
    """
    return "-".join(_words_ordered(area))


def area_from_slug(slug: str) -> str | None:
    """The canonical area a slug names, or None if it names nothing."""
    return _SLUG_TO_AREA.get(slug.strip().lower())


def _words_ordered(value: str) -> list[str]:
    cleaned = value.replace("&", "and").replace("-", " ").lower()
    return [w for w in "".join(c if c.isalnum() else " " for c in cleaned).split() if w]


_SLUG_TO_AREA: dict[str, str] = {area_slug(a): a for a in GS_AREAS}
