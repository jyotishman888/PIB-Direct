from types import SimpleNamespace

import httpx
import pytest
from anthropic import APIConnectionError

from pib_agent.study.client import StudyError, analyse_article
from pib_agent.study.schema import (
    MAX_LOW_PRIORITY,
    BothPoint,
    LowPriorityPoint,
    MainsPoint,
    PrelimsPoint,
    StudyNotes,
)

SAMPLE_NOTES = StudyNotes(
    classification="BOTH",
    reason="Carries a testable institutional core and real analytical depth on self-reliance.",
    prelims=[
        PrelimsPoint(
            point="India Semiconductor Mission sits under MeitY.",
            importance="IMPORTANT",
            syllabus="Science and Technology",
            why_important="Implementing-agency pairings are a standard statement-matching target.",
        )
    ],
    mains=[
        MainsPoint(
            point="Capital intensity and fab talent shortages constrain domestic capacity.",
            importance="IMPORTANT",
            gs_paper="GS3",
            theme="Technological self-reliance",
            analytical_use="Supports questions on barriers to semiconductor self-sufficiency.",
        )
    ],
    both=[
        BothPoint(
            concept="Semiconductor manufacturing ecosystem",
            prelims_angle="Terminology, incentives and the nodal agency.",
            mains_angle="Supply-chain resilience and strategic dependence.",
            importance="IMPORTANT",
        )
    ],
    low_priority=[
        LowPriorityPoint(point="Ceremony attendee list.", reason="No examinable content.")
    ],
)


class _FakeMessages:
    def __init__(self, response=None, exc: Exception | None = None):
        self._response = response
        self._exc = exc
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._response


def _fake_client(response=None, exc: Exception | None = None):
    return SimpleNamespace(messages=_FakeMessages(response=response, exc=exc))


def _article_kwargs(**overrides):
    base = dict(
        title="Cabinet approves semiconductor fabrication incentives",
        ministry_name="Ministry of Electronics & IT",
        summary="The Cabinet cleared incentives for domestic semiconductor fabrication.",
        context="This follows the India Semiconductor Mission announced earlier.",
        syllabus_topics=["GS Paper 3 - Science and Technology"],
        body_text="The Union Cabinet today approved incentives for semiconductor fabs.",
        upsc_relevance=4,
    )
    base.update(overrides)
    return base


def test_analyse_article_returns_parsed_output(monkeypatch):
    fake = _fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=SAMPLE_NOTES))
    monkeypatch.setattr("pib_agent.study.client._get_client", lambda: fake)

    result = analyse_article(**_article_kwargs())

    assert result.classification == "BOTH"
    assert result.prelims[0].importance == "IMPORTANT"
    assert result.both[0].concept == "Semiconductor manufacturing ecosystem"


def test_analyse_article_caches_the_system_prompt(monkeypatch):
    """The system prompt is fixed and re-sent for every article in a batch.

    Losing the cache_control breakpoint would quietly multiply input cost
    across a full backfill, which is exactly how this project shipped a dead
    cache once before.
    """
    fake = _fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=SAMPLE_NOTES))
    monkeypatch.setattr("pib_agent.study.client._get_client", lambda: fake)

    analyse_article(**_article_kwargs())

    system = fake.messages.calls[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_analyse_article_raises_on_refusal(monkeypatch):
    fake = _fake_client(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    monkeypatch.setattr("pib_agent.study.client._get_client", lambda: fake)

    with pytest.raises(StudyError, match="declined"):
        analyse_article(**_article_kwargs())


def test_analyse_article_raises_when_unparsed(monkeypatch):
    fake = _fake_client(SimpleNamespace(stop_reason="max_tokens", parsed_output=None))
    monkeypatch.setattr("pib_agent.study.client._get_client", lambda: fake)

    with pytest.raises(StudyError, match="did not parse"):
        analyse_article(**_article_kwargs())


def test_analyse_article_wraps_api_errors(monkeypatch):
    exc = APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake = _fake_client(exc=exc)
    monkeypatch.setattr("pib_agent.study.client._get_client", lambda: fake)

    with pytest.raises(StudyError, match="API call failed"):
        analyse_article(**_article_kwargs())


def test_low_priority_is_capped(monkeypatch):
    """The cap is enforced in code, not left to the prompt.

    Low-priority material is hidden behind a disclosure in the UI, so an
    over-producing model would only bloat the stored payload.
    """
    overproduced = SAMPLE_NOTES.model_copy(
        update={
            "low_priority": [
                LowPriorityPoint(point=f"Filler {i}", reason="Not examinable.")
                for i in range(MAX_LOW_PRIORITY + 4)
            ]
        }
    )
    fake = _fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=overproduced))
    monkeypatch.setattr("pib_agent.study.client._get_client", lambda: fake)

    result = analyse_article(**_article_kwargs())

    assert len(result.low_priority) == MAX_LOW_PRIORITY


def test_prompt_carries_existing_enrichment_rather_than_redoing_it(monkeypatch):
    fake = _fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=SAMPLE_NOTES))
    monkeypatch.setattr("pib_agent.study.client._get_client", lambda: fake)

    analyse_article(**_article_kwargs())

    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "The Cabinet cleared incentives" in prompt
    assert "GS Paper 3 - Science and Technology" in prompt


def test_prompt_carries_the_relevance_score_as_calibration(monkeypatch):
    """Without it every release looks equally worth extracting from, which is
    how a merely-useful release ends up scored like a landmark one."""
    fake = _fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=SAMPLE_NOTES))
    monkeypatch.setattr("pib_agent.study.client._get_client", lambda: fake)

    analyse_article(**_article_kwargs(upsc_relevance=3))

    prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "3/5" in prompt
    assert "budget for an overall score of 3" in prompt
