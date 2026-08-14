from pathlib import Path

import pytest

from pib_agent.scraper.listing_parser import ListingParseError, parse_listing

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_all_releases_grouped_by_ministry():
    items = parse_listing(_load("listing_page.html"))

    assert len(items) == 23
    prids = {item.prid for item in items}
    assert len(prids) == 23  # every release is unique
    assert 2296782 in prids
    assert 2296750 in prids


def test_release_fields_are_populated_correctly():
    items = parse_listing(_load("listing_page.html"))
    by_prid = {item.prid: item for item in items}

    renewable_energy = by_prid[2296782]
    assert renewable_energy.ministry_name == "Ministry of New and Renewable Energy"
    assert renewable_energy.title == "India Achieves Landmark 300 GW Non-Fossil Fuel Power Capacity"
    assert renewable_energy.detail_path == "/PressReleasePage.aspx?PRID=2296782"

    vice_president = by_prid[2296750]
    assert vice_president.ministry_name == "Vice President's Secretariat"
    assert "Har Ghar Tiranga" in vice_president.title


def test_ministries_with_multiple_releases_are_all_captured():
    items = parse_listing(_load("listing_page.html"))
    target = "Ministry of Social Justice & Empowerment"
    social_justice = [i for i in items if i.ministry_name == target]
    assert len(social_justice) == 5


def test_no_releases_yet_returns_empty_list_not_an_error():
    # Real PIB HTML captured when nothing had been published yet for the
    # day (renders `<div class='norecord'>***No Release Found***</div>`
    # instead of any ministry headings) — this is a legitimate zero-release
    # result, not a parse failure.
    items = parse_listing(_load("listing_page_no_releases.html"))

    assert items == []


def test_parses_js_onclick_links():
    """PIB switched the listing to JS-driven anchors on 2026-08-14.

    The href became a dead `javascript:void(0)` and the PRID moved into an
    onclick handler, which broke the scraper outright — every listing raised
    "Ministry headings found, but no release links inside them" and no new
    article was ingested until the parser learned the new shape. Fixture is
    real HTML captured from the live page that day.
    """
    items = parse_listing(_load("listing_page_onclick.html"))

    assert len(items) > 0
    by_prid = {item.prid: item for item in items}

    president = by_prid[2299386]
    assert president.ministry_name == "President's Secretariat"
    assert "AMRIT UDYAN" in president.title
    # No usable href on a JS anchor, so the canonical detail path is synthesised
    assert president.detail_path == "/PressReleasePage.aspx?PRID=2299386"


def test_onclick_and_href_links_parse_to_the_same_shape():
    """Both markup styles must yield identical ListingItem fields.

    Guards the fallback: a mixed page, or a revert by PIB, shouldn't change
    what downstream code sees.
    """
    href_style = """
        <ul><li><h3 class='font104'>Ministry of Test</h3>
          <ul class='num'><li>
            <a title='A release' href='/PressReleasePage.aspx?PRID=42'>A release</a>
          </li></ul>
        </li></ul>
    """
    onclick_style = """
        <ul><li><h3 class='font104'>Ministry of Test</h3>
          <ul class='num'><li>
            <a class='listLeftrel2' href='javascript:void(0)'
               onclick='return Bind_PressReleaseDetails(42)' title='A release'>A release</a>
          </li></ul>
        </li></ul>
    """

    (from_href,) = parse_listing(href_style)
    (from_onclick,) = parse_listing(onclick_style)

    assert from_href == from_onclick


def test_raises_on_unrecognised_html():
    with pytest.raises(ListingParseError):
        parse_listing("<html><body>Nothing here</body></html>")


def test_raises_when_anchors_carry_no_recoverable_prid():
    """A structural change that hides the PRID entirely must still be loud.

    The onclick fallback shouldn't quietly turn a genuine breakage into a
    zero-release day.
    """
    html = """
        <ul><li><h3 class='font104'>Ministry of Test</h3>
          <ul class='num'><li>
            <a href='javascript:void(0)' onclick='return SomethingElse()'>A release</a>
          </li></ul>
        </li></ul>
    """
    with pytest.raises(ListingParseError):
        parse_listing(html)


def test_raises_on_empty_string():
    with pytest.raises(ListingParseError):
        parse_listing("")
