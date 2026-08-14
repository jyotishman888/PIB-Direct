from dataclasses import dataclass, field
from types import SimpleNamespace

import httpx
import pytest
from anthropic import APIConnectionError

from pib_agent.enrichment.client import EnrichmentError, enrich_article
from pib_agent.enrichment.schema import ArticleEnrichment, MainsQuestion, PrelimsQuestion

SAMPLE_ENRICHMENT = ArticleEnrichment(
    summary="India crossed 300 GW of non-fossil power capacity.",
    context="This builds on the National Green Hydrogen Mission and prior renewable targets.",
    upsc_relevance=5,
    syllabus_topics=["GS Paper 3 - Environment: Renewable Energy"],
    prelims_questions=[
        PrelimsQuestion(
            question="India's non-fossil capacity milestone announced in Aug 2026 was:",
            options=["200 GW", "300 GW", "400 GW", "500 GW"],
            correct_option_index=1,
            explanation="The release states India crossed 300 GW of non-fossil capacity.",
        )
    ],
    mains_questions=[
        MainsQuestion(
            question="Discuss India's progress toward its 500 GW non-fossil energy target.",
            gs_paper="GS Paper 3 - Environment",
        )
    ],
)


@dataclass
class _FakeParseCall:
    kwargs: dict = field(default_factory=dict)


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
        title="India Achieves Landmark 300 GW Non-Fossil Fuel Power Capacity",
        ministry_name="Ministry of New and Renewable Energy",
        subtitle=None,
        body_text="India has crossed 300 GW of non-fossil fuel-based installed capacity.",
        release_datetime=None,
        pib_office="PIB Delhi",
    )
    base.update(overrides)
    return base


def test_enrich_article_returns_parsed_output(monkeypatch):
    fake_response = SimpleNamespace(stop_reason="end_turn", parsed_output=SAMPLE_ENRICHMENT)
    fake_client = _fake_client(response=fake_response)
    monkeypatch.setattr("pib_agent.enrichment.client._get_client", lambda: fake_client)

    result = enrich_article(**_article_kwargs())

    assert result is SAMPLE_ENRICHMENT
    assert fake_client.messages.calls[0]["output_format"] is ArticleEnrichment
    assert fake_client.messages.calls[0]["messages"][0]["role"] == "user"
    assert "300 GW" in fake_client.messages.calls[0]["messages"][0]["content"]


def test_enrich_article_raises_on_refusal(monkeypatch):
    fake_response = SimpleNamespace(stop_reason="refusal", parsed_output=None)
    fake_client = _fake_client(response=fake_response)
    monkeypatch.setattr("pib_agent.enrichment.client._get_client", lambda: fake_client)

    with pytest.raises(EnrichmentError, match="refus"):
        enrich_article(**_article_kwargs())


def test_enrich_article_raises_when_unparsed(monkeypatch):
    fake_response = SimpleNamespace(stop_reason="end_turn", parsed_output=None)
    fake_client = _fake_client(response=fake_response)
    monkeypatch.setattr("pib_agent.enrichment.client._get_client", lambda: fake_client)

    with pytest.raises(EnrichmentError, match="did not parse"):
        enrich_article(**_article_kwargs())


def test_enrich_article_wraps_api_errors(monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_client = _fake_client(exc=APIConnectionError(request=request))
    monkeypatch.setattr("pib_agent.enrichment.client._get_client", lambda: fake_client)

    with pytest.raises(EnrichmentError, match="Claude API call failed"):
        enrich_article(**_article_kwargs())


def test_get_client_raises_without_api_key(monkeypatch):
    import pib_agent.enrichment.client as client_module

    monkeypatch.setattr(client_module, "_client", None)
    fake_settings = SimpleNamespace(
        anthropic_api_key=None, anthropic_model="claude-sonnet-5", anthropic_max_retries=2
    )
    monkeypatch.setattr(client_module, "get_settings", lambda: fake_settings)

    with pytest.raises(EnrichmentError, match="ANTHROPIC_API_KEY"):
        client_module._get_client()
