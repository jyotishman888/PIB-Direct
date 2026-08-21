import logging
from pathlib import Path

import typer

from pib_agent import __version__
from pib_agent.config import get_settings
from pib_agent.db.backup import BackupError, backup_database
from pib_agent.db.base import session_scope
from pib_agent.db.diagnostics import (
    DatabaseNotReadyError,
    check_database_ready,
    wait_for_database,
)
from pib_agent.enrichment import run_enrich
from pib_agent.export_static import DEFAULT_EXPORT_DIR, DEFAULT_WINDOW_DAYS, export_static
from pib_agent.logging_config import setup_logging
from pib_agent.orchestration import (
    PipelineAlreadyRunningError,
    mark_interrupted_runs,
    run_pipeline,
)
from pib_agent.pyq import PyqImportError, import_past_questions
from pib_agent.scraper import run_scrape
from pib_agent.scraper.http_client import PibFetchError, fetch_html
from pib_agent.scraper.listing_parser import ListingParseError, parse_listing
from pib_agent.similarity import run_similarity
from pib_agent.study import run_study
from pib_agent.syllabus import normalise_area
from pib_agent.telegram import TelegramConfigError, run_bot, run_notify
from pib_agent.telegram.alerts import send_ops_alert

app = typer.Typer(
    name="pib-agent",
    help="Scrape, enrich, and serve daily PIB (Press Information Bureau) releases.",
    no_args_is_help=True,
)

logger = logging.getLogger(__name__)


@app.callback()
def _main() -> None:
    setup_logging()
    logger.debug("pib-agent CLI invoked (version=%s)", __version__)


@app.command()
def version() -> None:
    """Print the installed pib-agent version."""
    typer.echo(__version__)


@app.command()
def scrape() -> None:
    """Fetch today's PIB releases and persist any not already in the DB."""
    stats = run_scrape()
    typer.echo(
        f"Listed {stats.listed} releases: "
        f"{stats.new_articles} new, {stats.already_known} already known, "
        f"{stats.failed} failed."
    )
    if stats.failed:
        typer.echo(f"Failed PRIDs: {stats.failed_prids}")
        raise typer.Exit(code=1)


@app.command()
def enrich() -> None:
    """Summarize/contextualize/UPSC-annotate any articles not yet enriched."""
    stats = run_enrich()
    typer.echo(
        f"Pending {stats.pending} articles: "
        f"{stats.enriched} enriched, {stats.failed} failed."
    )
    if stats.failed:
        typer.echo(f"Failed article IDs: {stats.failed_article_ids}")
        raise typer.Exit(code=1)


@app.command("import-pyq")
def import_pyq(
    path: str = typer.Argument(..., help="A .json or .csv file of real past-year questions."),
    source: str = typer.Option(
        None, help="Label recorded against every row, so a bad batch can be found later."
    ),
) -> None:
    """Import real UPSC past-year questions from a file you supply.

    Nothing in this project generates these. A fabricated "asked in 2019" is
    the fastest way to lose an aspirant's trust, so the corpus is fed only by
    import, and each row records where it came from.

    Idempotent: duplicates are detected on (year, paper, question), so
    re-running the same file after a partial failure changes nothing.
    """
    try:
        stats = import_past_questions(Path(path), source=source)
    except PyqImportError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Read {stats.read}: {stats.imported} imported, {stats.duplicates} already present, "
        f"{stats.rejected} rejected."
    )
    if stats.unmapped_area:
        typer.echo(
            f"{stats.unmapped_area} row(s) had a syllabus area that didn't map to the "
            "canonical vocabulary; stored without one rather than guessed at."
        )
    for message in stats.errors[:10]:
        typer.echo(f"  rejected: {message}")
    if stats.rejected:
        raise typer.Exit(code=1)


@app.command("normalise-syllabus")
def normalise_syllabus(
    dry_run: bool = typer.Option(False, help="Report what would change without writing."),
) -> None:
    """Map legacy free-text syllabus tags onto the canonical vocabulary.

    The old prompt allowed a free-form "GS Paper N - Area: Sub-topic" suffix,
    which produced ~1090 distinct tags across the corpus. New enrichments are
    constrained by the schema; this cleans up what came before. Tags that
    don't map confidently are left untouched rather than guessed at.
    """
    from pib_agent.db import Enrichment

    changed = untouched = 0
    with session_scope() as session:
        for enrichment in session.query(Enrichment).all():
            tags = enrichment.syllabus_topics or []
            mapped, dirty = [], False
            for tag in tags:
                area = normalise_area(tag)
                if area and area != tag:
                    dirty = True
                    mapped.append(area)
                elif area:
                    mapped.append(area)
                else:
                    untouched += 1
                    mapped.append(tag)
            # dedupe while preserving order - collapsing sub-topics routinely
            # maps several legacy tags onto the same area.
            deduped = list(dict.fromkeys(mapped))
            if dirty or deduped != tags:
                changed += 1
                if not dry_run:
                    enrichment.syllabus_topics = deduped
        if dry_run:
            session.rollback()

    verb = "would change" if dry_run else "changed"
    typer.echo(f"{verb} {changed} enrichments; {untouched} tags left as-is (no confident match).")


@app.command()
def study() -> None:
    """Extract point-level UPSC study notes for enriched, relevant articles.

    Runs only for releases scoring at least `study_notes_min_relevance`: the
    cheap article-level score gates this more expensive second Claude call.
    """
    stats = run_study()
    typer.echo(
        f"Pending {stats.pending} articles: {stats.analysed} analysed, {stats.failed} failed."
    )
    if stats.failed:
        typer.echo(f"Failed article ids: {stats.failed_article_ids}")
        raise typer.Exit(code=1)


@app.command()
def link() -> None:
    """Embed enriched articles and link them to genuinely related past releases."""
    stats = run_similarity()
    typer.echo(
        f"Embedded {stats.embedded}/{stats.embed_pending} pending articles. "
        f"Similarity-checked {stats.linked}/{stats.link_pending} articles, "
        f"creating {stats.links_created} link(s)."
    )
    if stats.embed_failed or stats.link_failed:
        typer.echo(
            f"{stats.embed_failed} embedding failure(s); "
            f"{stats.link_failed} similarity-check failure(s): {stats.link_failed_article_ids}"
        )
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: str = typer.Option(None, help="Override API_HOST from settings."),
    port: int = typer.Option(None, help="Override API_PORT from settings."),
    reload: bool = typer.Option(False, help="Enable auto-reload for local development."),
) -> None:
    """Run the REST API server (FastAPI + Uvicorn).

    If SCHEDULER_ENABLED=true, this also runs the scrape->enrich->link->notify
    pipeline on a schedule for as long as the server is up.
    """
    import uvicorn

    settings = get_settings()
    try:
        wait_for_database()
        check_database_ready()
    except DatabaseNotReadyError as exc:
        typer.echo(f"Cannot start: {exc}")
        raise typer.Exit(code=1) from exc

    mark_interrupted_runs()
    uvicorn.run(
        "pib_agent.api.app:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=reload,
    )


@app.command()
def run() -> None:
    """Run scrape -> enrich -> link -> notify once, end to end, and wait for it to finish."""
    try:
        result = run_pipeline("cli")
    except PipelineAlreadyRunningError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    for stage in result.stages:
        detail = stage.summary if stage.status != "failed" else stage.error
        typer.echo(f"{stage.name}: {stage.status} ({detail})")

    typer.echo(f"Pipeline run {result.id}: {result.status}")
    if result.status in ("failed", "partial_failure"):
        raise typer.Exit(code=1)


@app.command()
def bot() -> None:
    """Run the Telegram bot (long polling) so users can manage subscriptions."""
    try:
        wait_for_database()
        check_database_ready()
    except DatabaseNotReadyError as exc:
        typer.echo(f"Cannot start: {exc}")
        raise typer.Exit(code=1) from exc

    try:
        run_bot()
    except TelegramConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc


@app.command()
def notify() -> None:
    """Send Telegram notifications for enriched articles not yet dispatched."""
    try:
        stats = run_notify()
    except TelegramConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Pending {stats.pending} articles: notified {stats.notified_articles}, "
        f"sent {stats.messages_sent} message(s), {stats.messages_failed} failed, "
        f"{stats.dead_chats_removed} dead chat(s) unsubscribed."
    )


@app.command()
def backup(
    keep: int = typer.Option(7, help="How many timestamped backups to retain."),
) -> None:
    """Take a timestamped copy of the SQLite database and prune old ones.

    Backups land in <db folder>/backups.
    """
    try:
        destination = backup_database(keep=keep)
    except BackupError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"Backed up to {destination}")


@app.command()
def migrate(
    wait_seconds: float = typer.Option(
        60.0, help="How long to wait for the database to become reachable first."
    ),
) -> None:
    """Apply Alembic migrations, waiting for the database to come up first.

    Meant for the container start command rather than a build or pre-deploy
    step: managed platforms only attach the private network at runtime
    (Railway documents this explicitly), so a migration run during the build
    can't reach the database at all, and one run the instant a container
    starts can lose a race with the network coming up.
    """
    from alembic.config import Config

    from alembic import command as alembic_command

    try:
        wait_for_database(timeout_seconds=wait_seconds)
    except DatabaseNotReadyError as exc:
        typer.echo(f"Cannot migrate: {exc}")
        raise typer.Exit(code=1) from exc

    config_path = Path.cwd() / "alembic.ini"
    if not config_path.exists():
        typer.echo(f"alembic.ini not found at {config_path}. Run this from the project root.")
        raise typer.Exit(code=1)

    alembic_command.upgrade(Config(str(config_path)), "head")
    typer.echo("Migrations applied.")


@app.command("export-static")
def export_static_command(
    out: str = typer.Option(
        str(DEFAULT_EXPORT_DIR),
        help="Directory to write the JSON bundle into. Rebuilt from scratch each run.",
    ),
    days: int = typer.Option(
        DEFAULT_WINDOW_DAYS,
        help="How many days back from the newest release to include.",
    ),
) -> None:
    """Export the corpus as static JSON for hosting without a backend.

    Reads only the public corpus - never the user, auth or subscription
    tables, since this bundle is committed to a public repository.
    """
    try:
        with session_scope() as session:
            result = export_static(out, session, days=days)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Exported {result.article_count} articles "
        f"across {result.ministry_count} ministries to {result.out_dir}"
    )
    typer.echo(f"Latest release date: {result.latest_date or 'none'}")
    if result.article_count == 0:
        typer.echo("Nothing to publish - the database has no articles in range.")
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """Check the live PIB listing still parses. Exits non-zero when it doesn't.

    Fixture-based tests can't catch PIB changing its markup - they passed
    perfectly while the real site was returning something the parser couldn't
    read. Run this on a schedule, or before trusting a quiet day.
    """
    settings = get_settings()
    failures: list[str] = []
    total = 0

    for url in settings.pib_listing_urls:
        try:
            items = parse_listing(fetch_html(url))
        except (PibFetchError, ListingParseError) as exc:
            failures.append(f"{url}: {exc}")
            typer.echo(f"FAIL  {url}\n      {exc}")
            continue
        total += len(items)
        typer.echo(f"OK    {url} -> {len(items)} release(s)")

    if failures:
        send_ops_alert("PIB listing check failed", "\n".join(failures))
        raise typer.Exit(code=1)

    if total == 0:
        typer.echo("No releases found on any source - could be an off-hours lull, or a break.")
        raise typer.Exit(code=2)

    typer.echo(f"All {len(settings.pib_listing_urls)} source(s) healthy, {total} release(s).")


def main() -> None:
    app()
