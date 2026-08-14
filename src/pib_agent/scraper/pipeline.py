import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from pib_agent.config import get_settings
from pib_agent.db import Article, Ministry
from pib_agent.db import session_scope as default_session_scope
from pib_agent.scraper.detail_parser import DetailParseError, parse_detail
from pib_agent.scraper.http_client import PibFetchError, fetch_html
from pib_agent.scraper.listing_parser import ListingItem, ListingParseError, parse_listing
from pib_agent.utils import slugify

logger = logging.getLogger(__name__)

SessionScopeFn = Callable[[], AbstractContextManager[Session]]


@dataclass
class ScrapeStats:
    listed: int = 0
    already_known: int = 0
    new_articles: int = 0
    failed: int = 0
    failed_prids: list[int] = field(default_factory=list)
    # A listing source (e.g. one PIB regional bureau) that couldn't be
    # fetched/parsed this pass — distinct from `failed`, which counts
    # individual release detail-page failures.
    listing_sources_failed: int = 0


def _get_or_create_ministry(session: Session, name: str) -> Ministry:
    slug = slugify(name)
    ministry = session.query(Ministry).filter_by(slug=slug).one_or_none()
    if ministry is None:
        ministry = Ministry(name=name, slug=slug)
        session.add(ministry)
        session.flush()
    return ministry


def _scrape_one(
    item: ListingItem, session_scope: SessionScopeFn, stats: ScrapeStats
) -> None:
    settings = get_settings()
    detail_url = settings.pib_detail_url_template.format(prid=item.prid)

    try:
        detail_html = fetch_html(detail_url)
        parsed = parse_detail(detail_html)
    except (PibFetchError, DetailParseError) as exc:
        logger.error("Failed to scrape PRID %s (%s): %s", item.prid, detail_url, exc)
        stats.failed += 1
        stats.failed_prids.append(item.prid)
        return

    ministry_name = parsed.ministry_name or item.ministry_name
    if parsed.ministry_name and slugify(parsed.ministry_name) != slugify(item.ministry_name):
        logger.debug(
            "Ministry name differs between listing (%r) and detail page (%r) for PRID %s",
            item.ministry_name,
            parsed.ministry_name,
            item.prid,
        )

    with session_scope() as session:
        # Re-check inside the transaction in case of a concurrent/overlapping scrape run.
        if session.query(Article).filter_by(prid=item.prid).one_or_none() is not None:
            stats.already_known += 1
            return

        ministry = _get_or_create_ministry(session, ministry_name)
        session.add(
            Article(
                prid=item.prid,
                ministry=ministry,
                title=parsed.title,
                subtitle=parsed.subtitle,
                body_text=parsed.body_text,
                body_html=parsed.body_html,
                pib_office=parsed.pib_office,
                release_datetime=parsed.release_datetime,
                source_url=detail_url,
            )
        )

    stats.new_articles += 1
    logger.info(
        "Scraped new release PRID=%s ministry=%r title=%r",
        item.prid,
        ministry_name,
        parsed.title[:60],
    )


def _fetch_listings(listing_urls: list[str], stats: ScrapeStats) -> list[ListingItem]:
    """Fetch+parse every configured listing source, merging results.

    Each source is isolated: one bureau's listing being unreachable doesn't
    lose releases from the others. The same release occasionally appears
    under more than one bureau (e.g. a PMO release relayed nationally), so
    items are deduped by PRID across sources — first source wins, and later
    duplicates never trigger a second detail-page fetch.
    """
    items_by_prid: dict[int, ListingItem] = {}
    for listing_url in listing_urls:
        try:
            listing_html = fetch_html(listing_url)
            listing_items = parse_listing(listing_html)
        except (PibFetchError, ListingParseError) as exc:
            logger.error("Failed to fetch/parse PIB listing page %s: %s", listing_url, exc)
            stats.listing_sources_failed += 1
            continue
        for item in listing_items:
            items_by_prid.setdefault(item.prid, item)

    if not items_by_prid and stats.listing_sources_failed == len(listing_urls):
        raise PibFetchError(
            f"Failed to fetch/parse all {len(listing_urls)} configured PIB listing page(s)."
        )
    return list(items_by_prid.values())


def run_scrape(*, session_scope: SessionScopeFn = default_session_scope) -> ScrapeStats:
    """Fetch every configured PIB listing source, scrape any releases not already in the DB.

    Idempotent: safe to call repeatedly (e.g. on a schedule) since new releases
    are deduped against the DB by PRID before being fetched/persisted.
    """
    settings = get_settings()
    stats = ScrapeStats()

    items = _fetch_listings(settings.pib_listing_urls, stats)
    stats.listed = len(items)

    with session_scope() as session:
        known_prids = {row[0] for row in session.query(Article.prid).all()}

    new_items = [item for item in items if item.prid not in known_prids]
    stats.already_known = stats.listed - len(new_items)

    for index, item in enumerate(new_items):
        if index > 0:
            time.sleep(settings.pib_request_delay_seconds)
        _scrape_one(item, session_scope, stats)

    logger.info(
        "Scrape complete: listed=%s new=%s already_known=%s failed=%s listing_sources_failed=%s",
        stats.listed,
        stats.new_articles,
        stats.already_known,
        stats.failed,
        stats.listing_sources_failed,
    )
    return stats
