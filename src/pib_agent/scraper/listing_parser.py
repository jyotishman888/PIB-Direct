import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

# PIB has served two link shapes for the same listing. Originally the PRID
# sat in a real href:
#     <a href='/PressReleasePage.aspx?PRID=123'>Title</a>
# As of 2026-08-14 the anchors are JS-driven instead, with a dead href and
# the PRID only reachable through the click handler:
#     <a href='javascript:void(0)' onclick='return Bind_PressReleaseDetails(123)'>
# Both are matched so a flip back (or a page serving a mix) still parses.
_PRID_HREF_RE = re.compile(r"PRID=(\d+)")
_PRID_ONCLICK_RE = re.compile(r"Bind_PressReleaseDetails\(\s*(\d+)\s*\)")

_DETAIL_PATH_TEMPLATE = "/PressReleasePage.aspx?PRID={prid}"


def _extract_prid(link) -> int | None:
    """Pull the release id out of an anchor, whichever shape PIB is serving."""
    href = link.get("href") or ""
    match = _PRID_HREF_RE.search(href)
    if match:
        return int(match.group(1))
    match = _PRID_ONCLICK_RE.search(link.get("onclick") or "")
    if match:
        return int(match.group(1))
    return None


class ListingParseError(ValueError):
    """Raised when the PIB listing page HTML doesn't match the expected structure."""


@dataclass(frozen=True, slots=True)
class ListingItem:
    prid: int
    title: str
    ministry_name: str
    detail_path: str  # relative path as found on the page, e.g. "/PressReleasePage.aspx?PRID=123"


def parse_listing(html: str) -> list[ListingItem]:
    """Parse https://pib.gov.in/allrel.aspx?reg=3&lang=1 into per-release entries.

    The page groups releases under a ministry heading:
        <ul><li><h3 class='font104'>Ministry Name</h3>
            <ul class='num'><li><a title='..' href='/PressReleasePage.aspx?PRID=1'>..</a></li></ul>
        </li></ul>

    The anchor inside may carry its PRID in the href or in an onclick handler
    (see _extract_prid) — PIB has served both.
    """
    soup = BeautifulSoup(html, "lxml")
    ministry_headings = soup.select("h3.font104")
    if not ministry_headings:
        # PIB renders this instead of any ministry headings when nothing has
        # been published yet for the current period (e.g. overnight, before
        # the day's releases start) — a legitimate zero-release result, not
        # a parsing failure. Only treat a *missing* "no releases" marker as
        # evidence the page structure itself has actually changed.
        if soup.select_one(".norecord") is not None:
            return []
        raise ListingParseError(
            "No ministry headings (h3.font104) found — PIB page structure may have changed."
        )

    items: list[ListingItem] = []
    for heading in ministry_headings:
        ministry_name = heading.get_text(strip=True)
        if not ministry_name:
            continue

        release_list = heading.find_next_sibling("ul", class_="num")
        if release_list is None:
            continue

        for link in release_list.find_all("a"):
            prid = _extract_prid(link)
            if prid is None:
                continue
            title = (link.get("title") or link.get_text(strip=True)).strip()
            if not title:
                continue
            href = (link.get("href") or "").strip()
            # A JS-driven anchor's href is a dead `javascript:void(0)`, so fall
            # back to the canonical path the detail fetcher uses anyway.
            detail_path = (
                href
                if _PRID_HREF_RE.search(href)
                else _DETAIL_PATH_TEMPLATE.format(prid=prid)
            )
            items.append(
                ListingItem(
                    prid=prid,
                    title=title,
                    ministry_name=ministry_name,
                    detail_path=detail_path,
                )
            )

    if not items:
        raise ListingParseError("Ministry headings found, but no release links inside them.")

    return items
