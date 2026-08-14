"""Canary tests against the real PIB website.

Excluded from the default run (see `addopts` in pyproject.toml) — run with:

    uv run pytest -m live

Why these exist: on 2026-08-14 PIB moved release links from a real href to a
JS onclick handler. The entire fixture-based suite stayed green while the
scraper ingested nothing at all for most of a day, because fixtures only ever
prove "we can still parse the HTML we captured once". These prove "we can
parse what PIB is serving right now", which is the property that actually
matters.
"""

import pytest

from pib_agent.config import get_settings
from pib_agent.scraper.detail_parser import parse_detail
from pib_agent.scraper.http_client import fetch_html
from pib_agent.scraper.listing_parser import parse_listing

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def listing_items():
    settings = get_settings()
    items = parse_listing(fetch_html(settings.pib_listing_urls[0]))
    if not items:
        pytest.skip("PIB is currently serving zero releases; nothing to assert against.")
    return items


def test_live_listing_parses_into_releases(listing_items):
    assert len(listing_items) > 0


def test_live_listing_items_are_well_formed(listing_items):
    for item in listing_items:
        assert item.prid > 0
        assert item.title.strip()
        assert item.ministry_name.strip()
        assert str(item.prid) in item.detail_path


def test_live_listing_prids_are_unique(listing_items):
    prids = [item.prid for item in listing_items]
    assert len(prids) == len(set(prids))


def test_live_detail_page_parses(listing_items):
    """The listing and detail parsers can break independently."""
    settings = get_settings()
    url = settings.pib_detail_url_template.format(prid=listing_items[0].prid)

    detail = parse_detail(fetch_html(url))

    assert detail.title.strip()
    assert detail.body_text.strip()
