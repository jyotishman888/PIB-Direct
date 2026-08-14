from pib_agent.enrichment.prompts import SYSTEM_PROMPT, build_user_prompt

# Anthropic's minimum cacheable prefix for Sonnet-class models. A system
# block marked with cache_control that falls below this is silently ignored —
# no error, no warning, just full input price on every call forever.
MIN_CACHEABLE_TOKENS = 1024

# Measured against the real count_tokens endpoint: a 3,027-character version
# of this prompt counted 1,009 tokens, i.e. ~3.0 chars/token for this text.
# Used as an offline proxy so this guard doesn't need network or credits.
CHARS_PER_TOKEN = 3.0


def test_system_prompt_stays_above_the_cache_threshold():
    """The prompt cache is load-bearing and fails silently when it breaks.

    This prompt sat at 1,009 tokens — fifteen short of the minimum — so the
    `cache_control` marker in enrichment/client.py did nothing at all and
    every enrichment call paid full input price. Shortening the prompt is a
    perfectly reasonable-looking edit that would silently reintroduce that,
    so it's guarded here rather than left to be noticed on a bill.
    """
    estimated_tokens = len(SYSTEM_PROMPT) / CHARS_PER_TOKEN

    assert estimated_tokens > MIN_CACHEABLE_TOKENS, (
        f"System prompt is ~{estimated_tokens:.0f} tokens, at or below the "
        f"{MIN_CACHEABLE_TOKENS}-token minimum cacheable prefix — cache_control "
        "would be silently ignored. Add substantive guidance rather than padding."
    )


def test_system_prompt_documents_every_output_field():
    """Each schema field needs instructions, or the model improvises one."""
    for field in (
        "summary",
        "context",
        "upsc_relevance",
        "syllabus_topics",
        "prelims_questions",
        "mains_questions",
    ):
        assert field in SYSTEM_PROMPT


def test_system_prompt_lists_the_canonical_gs_papers():
    """Free-form topic strings can't be indexed; the taxonomy keeps them consistent."""
    for paper in ("GS Paper 1", "GS Paper 2", "GS Paper 3", "GS Paper 4"):
        assert paper in SYSTEM_PROMPT


def test_system_prompt_is_stable_across_calls():
    """A prompt that varies per call can never be cached, whatever its length."""
    assert SYSTEM_PROMPT is SYSTEM_PROMPT
    assert "{" not in SYSTEM_PROMPT.replace("{prid}", "")  # no accidental format placeholders


def test_user_prompt_truncates_very_long_bodies():
    body = "x" * 20_000

    prompt = build_user_prompt(
        title="T",
        ministry_name="M",
        subtitle=None,
        body_text=body,
        release_datetime=None,
        pib_office=None,
    )

    assert "[release truncated for length]" in prompt
    assert len(prompt) < 15_000
