from pathlib import Path

import pytest

from pib_agent.db.models import Article, Ministry
from pib_agent.scraper.http_client import PibFetchError
from pib_agent.scraper.pipeline import run_scrape

FIXTURES = Path(__file__).parent / "fixtures"
LISTING_URL = "https://pib.gov.in/allrel.aspx?reg=3&lang=1"
NATIONAL_LISTING_URL = "https://pib.gov.in/allrel.aspx?reg=48&lang=1"
EMPTY_LISTING_HTML = "<html><body><div class='norecord'>***No Release Found***</div></body></html>"

RENEWABLE_ENERGY_PRID = 2296782
VICE_PRESIDENT_PRID = 2296750
CCI_PRID = 2296800


def _listing_block(ministry_name: str, prid: int, title: str) -> str:
    return (
        f"<ul><li><h3 class='font104'>{ministry_name}</h3><ul class='num'>"
        f"<li><a title='{title}' href='/PressReleasePage.aspx?PRID={prid}' "
        f'target="_blank">{title}</a></li>'
        "</ul></li></ul>"
    )


SYNTHETIC_LISTING_HTML = "<html><body>" + "".join(
    [
        _listing_block(
            "Ministry of New and Renewable Energy ",
            RENEWABLE_ENERGY_PRID,
            "India Achieves Landmark 300 GW Non-Fossil Fuel Power Capacity",
        ),
        _listing_block(
            "Vice President's Secretariat",
            VICE_PRESIDENT_PRID,
            "Vice-President launches campaign",
        ),
        _listing_block(
            "Competition Commission of India",
            CCI_PRID,
            "CCI hosts BRICS meeting",
        ),
    ]
) + "</body></html>"


def _detail_url(prid: int) -> str:
    return f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _fake_fetch_html(responses: dict[str, str]):
    def _fetch(url: str) -> str:
        try:
            return responses[url]
        except KeyError:
            raise AssertionError(f"Unexpected fetch of URL not stubbed in test: {url}") from None

    return _fetch


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("pib_agent.scraper.pipeline.time.sleep", lambda _seconds: None)


def _default_responses() -> dict[str, str]:
    return {
        LISTING_URL: SYNTHETIC_LISTING_HTML,
        NATIONAL_LISTING_URL: EMPTY_LISTING_HTML,
        _detail_url(RENEWABLE_ENERGY_PRID): _fixture("detail_2296782_renewable_energy.html"),
        _detail_url(VICE_PRESIDENT_PRID): _fixture("detail_2296750_vice_president.html"),
        _detail_url(CCI_PRID): _fixture("detail_2296800_cci_with_images.html"),
    }


def test_run_scrape_persists_all_new_articles(monkeypatch, session_scope_factory):
    monkeypatch.setattr(
        "pib_agent.scraper.pipeline.fetch_html", _fake_fetch_html(_default_responses())
    )

    stats = run_scrape(session_scope=session_scope_factory)

    assert stats.listed == 3
    assert stats.new_articles == 3
    assert stats.already_known == 0
    assert stats.failed == 0

    with session_scope_factory() as session:
        prids = {a.prid for a in session.query(Article).all()}
        assert prids == {RENEWABLE_ENERGY_PRID, VICE_PRESIDENT_PRID, CCI_PRID}

        renewable = session.query(Article).filter_by(prid=RENEWABLE_ENERGY_PRID).one()
        assert renewable.ministry.name == "Ministry of New and Renewable Energy"
        assert renewable.title == "India Achieves Landmark 300 GW Non-Fossil Fuel Power Capacity"
        assert renewable.source_url == _detail_url(RENEWABLE_ENERGY_PRID)


def test_run_scrape_skips_already_known_prids(monkeypatch, session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(
            name="Ministry of New and Renewable Energy",
            slug="ministry-of-new-and-renewable-energy",
        )
        session.add(
            Article(
                prid=RENEWABLE_ENERGY_PRID,
                ministry=ministry,
                title="Pre-existing title",
                subtitle=None,
                body_text="already scraped",
                body_html="<p>already scraped</p>",
                pib_office="PIB Delhi",
                release_datetime=None,
                source_url=_detail_url(RENEWABLE_ENERGY_PRID),
            )
        )

    responses = _default_responses()
    fetch_calls: list[str] = []

    def _tracking_fetch(url: str) -> str:
        fetch_calls.append(url)
        return responses[url]

    monkeypatch.setattr("pib_agent.scraper.pipeline.fetch_html", _tracking_fetch)

    stats = run_scrape(session_scope=session_scope_factory)

    assert stats.listed == 3
    assert stats.new_articles == 2
    assert stats.already_known == 1
    assert _detail_url(RENEWABLE_ENERGY_PRID) not in fetch_calls  # never re-fetched

    with session_scope_factory() as session:
        # the pre-existing row is untouched, not overwritten
        stored = session.query(Article).filter_by(prid=RENEWABLE_ENERGY_PRID).one()
        assert stored.title == "Pre-existing title"


def test_run_scrape_continues_after_one_detail_fetch_fails(monkeypatch, session_scope_factory):
    responses = _default_responses()

    def _flaky_fetch(url: str) -> str:
        if url == _detail_url(VICE_PRESIDENT_PRID):
            raise PibFetchError("simulated network failure")
        return responses[url]

    monkeypatch.setattr("pib_agent.scraper.pipeline.fetch_html", _flaky_fetch)

    stats = run_scrape(session_scope=session_scope_factory)

    assert stats.listed == 3
    assert stats.new_articles == 2
    assert stats.failed == 1
    assert stats.failed_prids == [VICE_PRESIDENT_PRID]

    with session_scope_factory() as session:
        prids = {a.prid for a in session.query(Article).all()}
        assert prids == {RENEWABLE_ENERGY_PRID, CCI_PRID}


def test_run_scrape_reuses_ministry_across_articles(monkeypatch, session_scope_factory):
    listing_html = "<html><body>" + _listing_block(
        "Ministry of New and Renewable Energy ", RENEWABLE_ENERGY_PRID, "Release A"
    ) + "</body></html>"
    responses = {
        LISTING_URL: listing_html,
        NATIONAL_LISTING_URL: EMPTY_LISTING_HTML,
        _detail_url(RENEWABLE_ENERGY_PRID): _fixture("detail_2296782_renewable_energy.html"),
    }
    monkeypatch.setattr("pib_agent.scraper.pipeline.fetch_html", _fake_fetch_html(responses))

    run_scrape(session_scope=session_scope_factory)

    with session_scope_factory() as session:
        slug = "ministry-of-new-and-renewable-energy"
        ministries = session.query(Ministry).filter_by(slug=slug).all()
        assert len(ministries) == 1


NATIONAL_ONLY_PRID = 2296900


def test_run_scrape_merges_items_from_multiple_listing_sources(monkeypatch, session_scope_factory):
    national_html = (
        "<html><body>"
        + _listing_block("Ministry of Tourism", NATIONAL_ONLY_PRID, "National-only release")
        + "</body></html>"
    )
    responses = _default_responses()
    responses[NATIONAL_LISTING_URL] = national_html
    responses[_detail_url(NATIONAL_ONLY_PRID)] = _fixture("detail_2296800_cci_with_images.html")
    monkeypatch.setattr("pib_agent.scraper.pipeline.fetch_html", _fake_fetch_html(responses))

    stats = run_scrape(session_scope=session_scope_factory)

    assert stats.listed == 4  # 3 from Delhi + 1 from National
    assert stats.new_articles == 4

    with session_scope_factory() as session:
        prids = {a.prid for a in session.query(Article).all()}
        assert NATIONAL_ONLY_PRID in prids


def test_run_scrape_dedupes_same_prid_across_sources(monkeypatch, session_scope_factory):
    # The same release (by PRID) is listed under both the Delhi and National bureaus.
    duplicate_listing_html = (
        "<html><body>"
        + _listing_block(
            "Ministry of New and Renewable Energy", RENEWABLE_ENERGY_PRID, "Duplicate listing"
        )
        + "</body></html>"
    )
    responses = _default_responses()
    responses[NATIONAL_LISTING_URL] = duplicate_listing_html

    fetch_calls: list[str] = []

    def _tracking_fetch(url: str) -> str:
        fetch_calls.append(url)
        return responses[url]

    monkeypatch.setattr("pib_agent.scraper.pipeline.fetch_html", _tracking_fetch)

    stats = run_scrape(session_scope=session_scope_factory)

    assert stats.listed == 3  # the shared PRID is only counted/fetched once
    assert stats.new_articles == 3
    assert fetch_calls.count(_detail_url(RENEWABLE_ENERGY_PRID)) == 1


def test_run_scrape_continues_when_one_listing_source_fails(monkeypatch, session_scope_factory):
    responses = _default_responses()

    def _flaky_fetch(url: str) -> str:
        if url == NATIONAL_LISTING_URL:
            raise PibFetchError("simulated network failure")
        return responses[url]

    monkeypatch.setattr("pib_agent.scraper.pipeline.fetch_html", _flaky_fetch)

    stats = run_scrape(session_scope=session_scope_factory)

    assert stats.listing_sources_failed == 1
    assert stats.listed == 3  # Delhi's items still processed despite National failing
    assert stats.new_articles == 3


def test_run_scrape_raises_when_all_listing_sources_fail(monkeypatch, session_scope_factory):
    def _always_fails(url: str) -> str:
        raise PibFetchError("simulated network failure")

    monkeypatch.setattr("pib_agent.scraper.pipeline.fetch_html", _always_fails)

    with pytest.raises(PibFetchError):
        run_scrape(session_scope=session_scope_factory)
