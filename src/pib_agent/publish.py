"""Publish the exported static bundle to the repo that serves the site.

The hourly pipeline keeps the database current, but the deployed site reads a
JSON bundle committed to the repo — so without this the two drift apart by a
day for every day nobody remembers to run `export-static` by hand.
"""

import logging
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from pib_agent.config import PROJECT_ROOT, get_settings
from pib_agent.db import session_scope
from pib_agent.export_static import DEFAULT_EXPORT_DIR, DEFAULT_WINDOW_DAYS, export_static

logger = logging.getLogger(__name__)


class PublishDisabledError(RuntimeError):
    """Raised when publishing is switched off, so the stage records as skipped."""


class PublishUnreachableError(RuntimeError):
    """Raised when the push succeeded but the site isn't serving."""


@dataclass
class PublishStats:
    articles: int
    changed: bool
    pushed: bool
    site_ok: bool | None = None


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _check_site(url: str) -> None:
    """Confirm the published site actually serves.

    A successful push says nothing about whether anything is deployed: making
    the repo private took GitHub Pages offline while every run still recorded
    "publish success", and the site was dead for four days before anyone
    looked at it.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "pib-agent"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        raise PublishUnreachableError(f"{url} returned HTTP {exc.code}") from exc
    except OSError as exc:  # DNS failure, TLS error, timeout
        raise PublishUnreachableError(f"{url} could not be reached: {exc}") from exc

    if status != 200:
        raise PublishUnreachableError(f"{url} returned HTTP {status}")


def run_publish(
    *, out_dir: Path = DEFAULT_EXPORT_DIR, days: int = DEFAULT_WINDOW_DAYS
) -> PublishStats:
    """Export the bundle and, if it changed, commit and push it.

    Only ever touches the export directory: the `git add`/`git commit` are
    path-limited so a run can't sweep up unrelated work in progress.
    """
    settings = get_settings()
    if not settings.publish_enabled:
        raise PublishDisabledError("Publishing disabled (PUBLISH_ENABLED=false).")

    with session_scope() as session:
        result = export_static(out_dir, session, days=days)

    rel = Path(out_dir).as_posix()
    # -A so releases dropping out of the window are staged as deletions too;
    # the export rebuilds the directory from scratch each time.
    _git("add", "-A", "--", rel)
    if not _git("status", "--porcelain", "--", rel):
        logger.info("Publish: bundle unchanged, nothing to push")
        return PublishStats(articles=result.article_count, changed=False, pushed=False)

    _git(
        "commit",
        "-m",
        f"Refresh static bundle to {result.latest_date or 'latest'}"
        f" ({result.article_count} articles)",
        "--",
        rel,
    )
    _git("push")
    logger.info("Publish: pushed %s articles (latest %s)", result.article_count, result.latest_date)

    if settings.site_url:
        # Raises, so the stage records as failed and the ops alert fires. The
        # push already landed; what failed is the site, which is the thing
        # worth being told about.
        _check_site(settings.site_url)
        logger.info("Publish: %s is serving", settings.site_url)
        return PublishStats(articles=result.article_count, changed=True, pushed=True, site_ok=True)

    return PublishStats(articles=result.article_count, changed=True, pushed=True)
