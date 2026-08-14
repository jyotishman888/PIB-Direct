import logging
from datetime import datetime

import anthropic

from pib_agent.config import get_settings
from pib_agent.similarity.prompts import SYSTEM_PROMPT, Candidate, build_user_prompt
from pib_agent.similarity.schema import SimilarityResult

logger = logging.getLogger(__name__)

_SIMILARITY_MAX_TOKENS = 2048


class SimilarityError(RuntimeError):
    """Raised when the Claude similarity-linking call fails, is refused, or doesn't parse."""


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise SimilarityError(
                "ANTHROPIC_API_KEY is not set. Add it to .env before running similarity linking."
            )
        _client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            max_retries=settings.anthropic_max_retries,
        )
    return _client


def find_related_links(
    *,
    title: str,
    ministry_name: str,
    summary: str,
    release_datetime: datetime | None,
    candidates: list[Candidate],
) -> SimilarityResult:
    """Ask Claude which (if any) of the candidate past releases are genuinely related.

    Raises SimilarityError on API failure, a safety refusal, or a response
    that doesn't parse into the expected schema.
    """
    settings = get_settings()
    client = _get_client()

    user_prompt = build_user_prompt(
        title=title,
        ministry_name=ministry_name,
        summary=summary,
        release_datetime=release_datetime,
        candidates=candidates,
    )

    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=_SIMILARITY_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
            output_format=SimilarityResult,
        )
    except anthropic.APIError as exc:
        raise SimilarityError(f"Claude API call failed: {exc}") from exc

    if response.stop_reason == "refusal":
        raise SimilarityError("Claude declined to process this similarity check (safety refusal).")

    if response.parsed_output is None:
        raise SimilarityError(
            "Claude response did not parse into the expected schema "
            f"(stop_reason={response.stop_reason!r})."
        )

    return response.parsed_output
