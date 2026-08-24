"""Publish the exported static bundle to the repo that serves the site.

The hourly pipeline keeps the database current, but the deployed site reads a
JSON bundle committed to the repo — so without this the two drift apart by a
day for every day nobody remembers to run `export-static` by hand.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pib_agent.config import PROJECT_ROOT, get_settings
from pib_agent.db import session_scope
from pib_agent.export_static import DEFAULT_EXPORT_DIR, DEFAULT_WINDOW_DAYS, export_static

logger = logging.getLogger(__name__)


class PublishDisabledError(RuntimeError):
    """Raised when publishing is switched off, so the stage records as skipped."""


@dataclass
class PublishStats:
    articles: int
    changed: bool
    pushed: bool


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


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
    return PublishStats(articles=result.article_count, changed=True, pushed=True)
