import logging
import re
from dataclasses import dataclass
from datetime import datetime

from bs4 import BeautifulSoup
from bs4.element import Tag

logger = logging.getLogger(__name__)

_DATE_LINE_RE = re.compile(
    r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{1,2}:\d{2}\s*[AP]M)\s+by\s+(.+)"
)
_DATE_FORMAT = "%d %b %Y %I:%M%p"

# Sibling elements after #PrDateTime that carry no real body content and should
# be skipped rather than treated as the end of the article.
_BODY_NOISE_TAGS = {"input"}


class DetailParseError(ValueError):
    """Raised when a PIB detail page HTML doesn't match the expected structure."""


@dataclass(frozen=True, slots=True)
class ParsedArticle:
    title: str
    subtitle: str | None
    ministry_name: str
    body_text: str
    body_html: str
    release_datetime: datetime | None
    pib_office: str | None


def _parse_date_line(text: str) -> tuple[datetime | None, str | None]:
    match = _DATE_LINE_RE.search(text)
    if not match:
        logger.warning("Could not parse PIB date line: %r", text)
        return None, None
    date_str, office = match.group(1), match.group(2).strip()
    try:
        return datetime.strptime(date_str, _DATE_FORMAT), office
    except ValueError:
        logger.warning("Could not parse date %r from date line %r", date_str, text)
        return None, office


def _extract_body(date_div: Tag) -> tuple[str, str]:
    end_marker = date_div.find_next(id="reel_pic") or date_div.find_next(id="ReleaseId")

    html_parts: list[str] = []
    text_parts: list[str] = []
    for sibling in date_div.find_next_siblings():
        if end_marker is not None and sibling is end_marker:
            break
        if not isinstance(sibling, Tag) or sibling.name in _BODY_NOISE_TAGS:
            continue

        has_text = bool(sibling.get_text(strip=True))
        has_image = sibling.find("img") is not None
        if not has_text and not has_image:
            continue

        html_parts.append(str(sibling))
        if has_text:
            text_parts.append(sibling.get_text(separator=" ", strip=True))

    return "\n".join(text_parts), "\n".join(html_parts)


def parse_detail(html: str) -> ParsedArticle:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.find(id="Titleh2")
    if title_el is None:
        raise DetailParseError("No #Titleh2 element found — PIB page structure may have changed.")
    title = title_el.get_text(strip=True)

    subtitle_el = soup.find(id="Subtitleh3")
    subtitle = subtitle_el.get_text(separator="\n", strip=True) if subtitle_el else ""

    ministry_el = soup.find(id="MinistryName")
    ministry_name = ministry_el.get_text(strip=True) if ministry_el else ""

    date_div = soup.find(id="PrDateTime")
    if date_div is None:
        raise DetailParseError("No #PrDateTime element found — PIB page structure may have changed")
    release_datetime, pib_office = _parse_date_line(date_div.get_text(" ", strip=True))

    body_text, body_html = _extract_body(date_div)
    if not body_text:
        raise DetailParseError("Parsed article body is empty — PIB page structure may have changed")

    return ParsedArticle(
        title=title,
        subtitle=subtitle or None,
        ministry_name=ministry_name,
        body_text=body_text,
        body_html=body_html,
        release_datetime=release_datetime,
        pib_office=pib_office,
    )
