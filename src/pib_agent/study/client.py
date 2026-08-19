import logging

import anthropic

from pib_agent.config import get_settings
from pib_agent.study.prompts import SYSTEM_PROMPT, build_user_prompt
from pib_agent.study.schema import MAX_LOW_PRIORITY, StudyNotes

logger = logging.getLogger(__name__)

# Larger than the enrichment budget: this pass emits several lists of points
# with per-point justifications, where enrichment emits prose plus a couple of
# questions.
_STUDY_MAX_TOKENS = 6144


class StudyError(RuntimeError):
    """Raised when the study pass fails, is refused, or returns no parsed output."""


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise StudyError(
                "ANTHROPIC_API_KEY is not set. Add it to .env before running the study pass."
            )
        _client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            max_retries=settings.anthropic_max_retries,
        )
    return _client


def analyse_article(
    *,
    title: str,
    ministry_name: str,
    summary: str,
    context: str,
    syllabus_topics: list[str],
    body_text: str,
    upsc_relevance: int,
) -> StudyNotes:
    """Extract UPSC-examinable points from one already-enriched release.

    One structured-output call, not the spec's ten-step chain: the stages are
    encoded in the output schema instead, which keeps cost and latency to a
    single round trip.

    Raises StudyError on API failure, a safety refusal, or a response that
    doesn't parse into the expected schema.
    """
    settings = get_settings()
    client = _get_client()

    user_prompt = build_user_prompt(
        title=title,
        ministry_name=ministry_name,
        summary=summary,
        context=context,
        syllabus_topics=syllabus_topics,
        body_text=body_text,
        upsc_relevance=upsc_relevance,
    )

    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=_STUDY_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
            output_format=StudyNotes,
        )
    except anthropic.APIError as exc:
        raise StudyError(f"Claude API call failed: {exc}") from exc

    if response.stop_reason == "refusal":
        raise StudyError("Claude declined to analyse this article (safety refusal).")

    if response.parsed_output is None:
        raise StudyError(
            "Claude response did not parse into the expected schema "
            f"(stop_reason={response.stop_reason!r})."
        )

    notes = response.parsed_output
    # Enforced here rather than left to the prompt: the cap exists to bound
    # what the UI hides behind a disclosure, and a model that over-produces
    # shouldn't grow the stored payload.
    if len(notes.low_priority) > MAX_LOW_PRIORITY:
        notes.low_priority = notes.low_priority[:MAX_LOW_PRIORITY]

    return notes
