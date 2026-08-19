from typing import Literal

from pydantic import BaseModel, Field

# §5 of the spec keeps low-priority material out of the primary notes, so
# extracting it without limit spends output tokens on content the UI hides
# behind a disclosure. Three is enough to show the model discriminated.
MAX_LOW_PRIORITY = 3

Classification = Literal["PRELIMS", "MAINS", "BOTH", "LOW_PRIORITY"]


class PrelimsPoint(BaseModel):
    point: str = Field(
        description=(
            "One factual or conceptual item UPSC could turn into an objective question: "
            "an institution, provision, scheme feature, index, species, treaty, "
            "definition, or a distinction between two similar concepts."
        )
    )
    importance: int = Field(
        ge=1,
        le=5,
        description=(
            "5 = direct syllabus relevance and strong testability. 4 = likely to be "
            "tested. 3 = useful background, lower probability. 2 = peripheral. "
            "1 = mostly contextual."
        ),
    )
    syllabus: str = Field(
        description=(
            "Prelims subject area, e.g. 'Polity', 'Environment', "
            "'Science & Technology', 'Government Schemes'."
        )
    )
    why_important: str = Field(
        description=(
            "One concise sentence on why an aspirant should hold this fact. "
            "Specific to this point — not a generic statement about the topic."
        )
    )


class MainsPoint(BaseModel):
    point: str = Field(
        description=(
            "One analytical dimension: a cause, consequence, challenge, implication, "
            "policy gap, stakeholder perspective, or way forward."
        )
    )
    importance: int = Field(ge=1, le=5, description="Same 1-5 scale as Prelims points.")
    gs_paper: str = Field(description="Which paper this serves, e.g. 'GS3'.")
    theme: str = Field(
        description="Short theme label, e.g. 'Technological self-reliance'."
    )
    analytical_use: str = Field(
        description=(
            "How this point would be deployed in an answer — the kind of question it "
            "helps address. Describe the question pattern; never invent a past paper."
        )
    )


class BothPoint(BaseModel):
    concept: str = Field(
        description="A concept carrying both a testable factual core and analytical depth."
    )
    prelims_angle: str = Field(description="What could be asked objectively about it.")
    mains_angle: str = Field(description="What it lets an aspirant analyse.")
    importance: int = Field(ge=1, le=5, description="Same 1-5 scale.")


class LowPriorityPoint(BaseModel):
    point: str = Field(description="Material carrying little exam value.")
    reason: str = Field(description="Briefly, why it is not examinable.")


class StudyNotes(BaseModel):
    """Point-level UPSC extraction for one release.

    Deliberately does not restate the article-level relevance score or the
    syllabus tags — `Enrichment.upsc_relevance` and `Enrichment.syllabus_topics`
    already hold those, and this pass runs only for articles that cleared that
    score.
    """

    classification: Classification = Field(
        description=(
            "Where this release's value sits overall. BOTH when it carries a testable "
            "factual core and real analytical depth — that is the highest-value case. "
            "LOW_PRIORITY when neither is genuinely present."
        )
    )
    reason: str = Field(
        description="One or two sentences justifying the classification."
    )
    prelims: list[PrelimsPoint] = Field(
        default_factory=list,
        description=(
            "Objectively testable items. Empty when the release offers none — "
            "an empty list is a valid and useful answer."
        ),
    )
    mains: list[MainsPoint] = Field(
        default_factory=list,
        description="Analytical dimensions. Empty when the release offers none.",
    )
    both: list[BothPoint] = Field(
        default_factory=list,
        description=(
            "Concepts serving both purposes. Reserve for genuinely dual-use material "
            "rather than restating a Prelims point with commentary attached."
        ),
    )
    low_priority: list[LowPriorityPoint] = Field(
        default_factory=list,
        description=(
            f"At most {MAX_LOW_PRIORITY} items of noise worth naming so the reader "
            "can see it was considered and set aside."
        ),
    )
