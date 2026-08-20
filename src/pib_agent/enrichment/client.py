import logging
from datetime import datetime

import anthropic

from pib_agent.config import get_settings
from pib_agent.enrichment.prompts import SYSTEM_PROMPT, build_user_prompt
from pib_agent.enrichment.schema import ArticleEnrichment
from pib_agent.syllabus import normalise_area

logger = logging.getLogger(__name__)

_ENRICHMENT_MAX_TOKENS = 4096

# The prompt asks for "one or two" areas, but the model sprays and repeats:
# observed live, a farming scheme listed Agriculture twice and a defence
# agreement returned eleven areas including Art and Culture. Enforced here
# rather than left to the prompt.
_MAX_SYLLABUS_AREAS = 2


class EnrichmentError(RuntimeError):
    """Raised when Claude enrichment fails, is refused, or returns no parsed output."""


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise EnrichmentError(
                "ANTHROPIC_API_KEY is not set. Add it to .env before running enrichment."
            )
        _client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            max_retries=settings.anthropic_max_retries,
        )
    return _client


def enrich_article(
    *,
    title: str,
    ministry_name: str,
    subtitle: str | None,
    body_text: str,
    release_datetime: datetime | None,
    pib_office: str | None,
) -> ArticleEnrichment:
    """Call Claude to summarize/contextualize/UPSC-annotate one PIB article.

    Raises EnrichmentError on API failure, a safety refusal, or a response
    that doesn't parse into the expected schema.
    """
    settings = get_settings()
    client = _get_client()

    user_prompt = build_user_prompt(
        title=title,
        ministry_name=ministry_name,
        subtitle=subtitle,
        body_text=body_text,
        release_datetime=release_datetime,
        pib_office=pib_office,
    )

    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=_ENRICHMENT_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
            output_format=ArticleEnrichment,
        )
    except anthropic.APIError as exc:
        raise EnrichmentError(f"Claude API call failed: {exc}") from exc

    if response.stop_reason == "refusal":
        raise EnrichmentError("Claude declined to process this article (safety refusal).")

    if response.parsed_output is None:
        raise EnrichmentError(
            "Claude response did not parse into the expected schema "
            f"(stop_reason={response.stop_reason!r})."
        )

    result = response.parsed_output
    # Coerced, not validated: typing this field as a Literal made a one-word
    # casing slip ("Statutory And Regulatory Bodies") fail the whole
    # enrichment, losing the summary and context too. Mapping onto the
    # vocabulary and dropping what doesn't fit keeps a bad tag from costing a
    # good article.
    canonical: dict[str, None] = {}
    for tag in result.syllabus_topics:
        area = normalise_area(tag)
        if area is not None:
            canonical[area] = None
    result.syllabus_topics = list(canonical)[:_MAX_SYLLABUS_AREAS]
    return result
