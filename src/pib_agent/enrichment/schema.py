from pydantic import BaseModel, Field


class PrelimsQuestion(BaseModel):
    question: str = Field(description="A UPSC Prelims-style factual/conceptual MCQ stem.")
    options: list[str] = Field(description="Exactly four answer options, in order.")
    correct_option_index: int = Field(
        description="0-based index into `options` identifying the correct answer."
    )
    explanation: str = Field(
        description="Brief explanation of why the correct option is right, grounded in the release."
    )


class MainsQuestion(BaseModel):
    question: str = Field(
        description=(
            "A UPSC Mains-style analytical/descriptive question this development could motivate."
        )
    )
    gs_paper: str = Field(
        description="Which General Studies paper this fits, e.g. 'GS Paper 2 - Governance'."
    )


class ArticleEnrichment(BaseModel):
    summary: str = Field(
        description=(
            "A self-contained 2-4 sentence summary of the release for a reader "
            "who has not seen it."
        )
    )
    context: str = Field(
        description=(
            "1-3 paragraphs of background: why this matters, the broader scheme/policy/"
            "historical context, not just a restatement of the release."
        )
    )
    upsc_relevance: int = Field(
        ge=1,
        le=5,
        description=(
            "How much this release is worth an aspirant's study time, 1-5. "
            "5 = a landmark development almost certain to be examinable. "
            "4 = a substantive scheme/policy/report likely to be asked about. "
            "3 = worth knowing as background but unlikely to be asked directly. "
            "2 = marginal: a routine update on an examinable subject. "
            "1 = no study value (events, appointments, ceremonies, procedural notices)."
        ),
    )
    syllabus_topics: list[str] = Field(
        description=(
            "GS syllabus tags this release relates to, e.g. 'GS Paper 3 - Economy: "
            "Infrastructure'. Empty list when upsc_relevance is below 3."
        )
    )
    prelims_questions: list[PrelimsQuestion] = Field(
        description=(
            "1-2 Prelims-style MCQs grounded in this release. "
            "Empty list when upsc_relevance is below 3."
        )
    )
    mains_questions: list[MainsQuestion] = Field(
        description=(
            "1-2 Mains-style questions grounded in this release. "
            "Empty list when upsc_relevance is below 3."
        )
    )
