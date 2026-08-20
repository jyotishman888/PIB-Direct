import pytest

from pib_agent.enrichment.prompts import SYSTEM_PROMPT
from pib_agent.syllabus import GS_AREAS, PRELIMS_SUBJECTS, normalise_area


def test_areas_carry_no_colon():
    """A colon is what invited the free-form suffix that produced 1090 tags."""
    assert [a for a in GS_AREAS if ":" in a] == []


def test_every_area_names_its_paper():
    assert all(a.startswith("GS Paper ") for a in GS_AREAS)


def test_vocabulary_is_unique():
    assert len(set(GS_AREAS)) == len(GS_AREAS)
    assert len(set(PRELIMS_SUBJECTS)) == len(PRELIMS_SUBJECTS)


def test_prompt_lists_the_canonical_vocabulary():
    """The prompt renders from the constant, so the two cannot drift apart."""
    for area in GS_AREAS:
        assert area in SYSTEM_PROMPT


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        # the ": Sub-topic" suffix the old prompt invited
        ("GS Paper 3 - Economy: Infrastructure", "GS Paper 3 - Economy"),
        (
            "GS Paper 1 - Modern Indian History: Role of literature",
            "GS Paper 1 - Modern Indian History",
        ),
        # short prefixes of longer canonical names
        ("GS Paper 3 - Environment", "GS Paper 3 - Environment and Biodiversity"),
        ("GS Paper 2 - Polity", "GS Paper 2 - Polity and Constitution"),
        # "&" for "and"
        ("GS Paper 3 - Science & Technology", "GS Paper 3 - Science and Technology"),
        # longer wording that contains the canonical name
        ("GS Paper 2 - Welfare schemes for vulnerable sections", "GS Paper 2 - Welfare Schemes"),
        # exact input is preserved
        ("GS Paper 2 - Governance", "GS Paper 2 - Governance"),
    ],
)
def test_normalise_maps_legacy_wordings(legacy, expected):
    assert normalise_area(legacy) == expected


def test_normalise_never_crosses_papers():
    """'Health' is a GS2 area; a GS3 tag must not be pulled into it."""
    assert normalise_area("GS Paper 3 - Health of soil ecosystems") != "GS Paper 2 - Health"


def test_normalise_returns_none_rather_than_guessing():
    assert normalise_area("GS Paper 2 - Zzzqqx Wibble Frobnicate") is None
    assert normalise_area("") is None
