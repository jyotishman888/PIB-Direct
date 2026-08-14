from types import SimpleNamespace

import httpx
import pytest
from anthropic import APIConnectionError

from pib_agent.similarity.client import SimilarityError, find_related_links
from pib_agent.similarity.prompts import Candidate
from pib_agent.similarity.schema import RelatedLink, SimilarityResult

SAMPLE_CANDIDATES = [
    Candidate(
        index=0,
        title="India's Solar Capacity Crosses 150 GW",
        ministry_name="Ministry of New and Renewable Energy",
        summary="An earlier milestone release on solar capacity growth.",
        release_datetime=None,
    )
]

SAMPLE_RESULT = SimilarityResult(
    related_links=[
        RelatedLink(
            candidate_index=0,
            relationship="Both releases track India's progress toward renewable energy targets.",
        )
    ]
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


def _call_kwargs(**overrides):
    base = dict(
        title="India Achieves Landmark 300 GW Non-Fossil Fuel Power Capacity",
        ministry_name="Ministry of New and Renewable Energy",
        summary="India crossed 300 GW of non-fossil fuel capacity.",
        release_datetime=None,
        candidates=SAMPLE_CANDIDATES,
    )
    base.update(overrides)
    return base


def test_find_related_links_returns_parsed_output(monkeypatch):
    fake_response = SimpleNamespace(stop_reason="end_turn", parsed_output=SAMPLE_RESULT)
    fake_client = _fake_client(response=fake_response)
    monkeypatch.setattr("pib_agent.similarity.client._get_client", lambda: fake_client)

    result = find_related_links(**_call_kwargs())

    assert result is SAMPLE_RESULT
    call = fake_client.messages.calls[0]
    assert call["output_format"] is SimilarityResult
    assert "[0]" in call["messages"][0]["content"]


def test_find_related_links_raises_on_refusal(monkeypatch):
    fake_response = SimpleNamespace(stop_reason="refusal", parsed_output=None)
    fake_client = _fake_client(response=fake_response)
    monkeypatch.setattr("pib_agent.similarity.client._get_client", lambda: fake_client)

    with pytest.raises(SimilarityError, match="refus"):
        find_related_links(**_call_kwargs())


def test_find_related_links_raises_when_unparsed(monkeypatch):
    fake_response = SimpleNamespace(stop_reason="end_turn", parsed_output=None)
    fake_client = _fake_client(response=fake_response)
    monkeypatch.setattr("pib_agent.similarity.client._get_client", lambda: fake_client)

    with pytest.raises(SimilarityError, match="did not parse"):
        find_related_links(**_call_kwargs())


def test_find_related_links_wraps_api_errors(monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_client = _fake_client(exc=APIConnectionError(request=request))
    monkeypatch.setattr("pib_agent.similarity.client._get_client", lambda: fake_client)

    with pytest.raises(SimilarityError, match="Claude API call failed"):
        find_related_links(**_call_kwargs())


def test_get_client_raises_without_api_key(monkeypatch):
    import pib_agent.similarity.client as client_module

    monkeypatch.setattr(client_module, "_client", None)
    fake_settings = SimpleNamespace(
        anthropic_api_key=None, anthropic_model="claude-sonnet-5", anthropic_max_retries=2
    )
    monkeypatch.setattr(client_module, "get_settings", lambda: fake_settings)

    with pytest.raises(SimilarityError, match="ANTHROPIC_API_KEY"):
        client_module._get_client()
