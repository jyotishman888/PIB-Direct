from pydantic import BaseModel, Field


class RelatedLink(BaseModel):
    candidate_index: int = Field(
        description=(
            "0-based index into the candidate list identifying which past release this refers to."
        )
    )
    relationship: str = Field(
        description=(
            "1-2 sentence explanation of how this past release relates to the new one, "
            "suitable for display under 'Related past coverage'."
        )
    )


class SimilarityResult(BaseModel):
    related_links: list[RelatedLink] = Field(
        description=(
            "Past releases genuinely related to the new one in substance (same scheme, "
            "policy area, recurring event, or direct follow-up) — not just similar wording "
            "or the same ministry. Empty list when none are meaningfully related."
        )
    )
