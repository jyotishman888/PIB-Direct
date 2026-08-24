from datetime import datetime
from pathlib import Path

import pytest

from pib_agent.scraper.detail_parser import DetailParseError, parse_detail

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_article_without_subtitle():
    article = parse_detail(_load("detail_2296782_renewable_energy.html"))

    assert article.title == "India Achieves Landmark 300 GW Non-Fossil Fuel Power Capacity"
    assert article.subtitle is None
    assert article.ministry_name == "Ministry of New and Renewable Energy"
    assert article.release_datetime == datetime(2026, 8, 9, 14, 31)
    assert article.pib_office == "PIB Delhi"
    assert "300 GW" in article.body_text
    assert "Solar Power" in article.body_text
    assert "<li>" in article.body_html


def test_parses_article_with_multi_bullet_subtitle():
    article = parse_detail(_load("detail_2296750_vice_president.html"))

    assert article.ministry_name == "Vice President's Secretariat"
    assert article.release_datetime == datetime(2026, 8, 9, 12, 45)
    assert article.pib_office == "PIB Delhi"
    assert article.subtitle is not None
    assert "Bharat is one and will always remain one" in article.subtitle
    # four bullet points joined by newlines, no stray empty lines
    assert article.subtitle.count("\n") == 3


def test_parses_article_with_inline_images():
    article = parse_detail(_load("detail_2296800_cci_with_images.html"))

    assert article.ministry_name == "Competition Commission of India"
    assert "BRICS" in article.title
    assert "<img" in article.body_html
    assert len(article.body_text) > 0


def test_raises_on_missing_title():
    html = (
        "<html><body><div id='PrDateTime'>"
        "Posted On: 09 AUG 2026 2:31PM by PIB Delhi"
        "</div></body></html>"
    )
    with pytest.raises(DetailParseError):
        parse_detail(html)


def test_raises_when_no_date_div_and_no_body():
    with pytest.raises(DetailParseError):
        parse_detail("<html><body><h2 id='Titleh2'>Some Title</h2></body></html>")


def test_parses_regional_page_without_date_div():
    """Regional PIB offices omit #PrDateTime; the release is still real."""
    article = parse_detail(_load("detail_2302236_regional_no_datediv.html"))

    assert article.ministry_name == "Ministry of Information & Broadcasting"
    assert "57th IFFI" in article.title
    # the date line is recovered from the unnamed div the regional template uses
    assert article.release_datetime == datetime(2026, 8, 22, 9, 44)
    assert article.pib_office == "PIB Delhi"
    assert "International Film Festival of India" in article.body_text
    # body starts after the title block, so the headline isn't repeated into it
    assert not article.body_text.startswith(article.title)


def test_unparseable_date_line_does_not_raise():
    html = """
    <html><body>
        <h2 id="Titleh2">Some Title</h2>
        <div id="PrDateTime">garbled date text</div>
        <p>Body paragraph with enough content to count as real text.</p>
        <span id="ReleaseId">(Release ID: 1)</span>
    </body></html>
    """
    article = parse_detail(html)
    assert article.release_datetime is None
    assert article.pib_office is None
    assert "Body paragraph" in article.body_text
