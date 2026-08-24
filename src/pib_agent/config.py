from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _redact(url: str) -> str:
    """A connection string safe to put in an error message.

    These end up in deploy logs, which get pasted into chats and issue
    trackers, so the password must not survive.
    """
    if "://" not in url:
        return repr(url)
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        credentials, host = rest.rsplit("@", 1)
        user = credentials.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return f"{scheme}://{rest}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'pib_agent.db'}"
    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"

    # PIB's `reg` query param selects a *regional bureau*, not a ministry —
    # each bureau's listing shows a different, only-partly-overlapping set of
    # ministries/organizations (confirmed live: reg=3 "PIB Delhi" alone
    # misses Commerce, Culture, Education, Minority Affairs, Parliamentary
    # Affairs, Statistics, Tourism, UPSC, President's Secretariat, all of
    # which appear under reg=48 "National"). Scraping both is what actually
    # gets full central-government ministry coverage; PRIDs are deduped
    # across sources the same way they're deduped against the DB.
    pib_listing_urls: list[str] = [
        "https://pib.gov.in/allrel.aspx?reg=3&lang=1",  # PIB Delhi
        "https://pib.gov.in/allrel.aspx?reg=48&lang=1",  # National
    ]
    pib_detail_url_template: str = "https://pib.gov.in/PressReleasePage.aspx?PRID={prid}"
    # pib.gov.in's WAF 403s any User-Agent that doesn't look like a real browser
    # (a custom "pib-agent/0.1 (...)" identifier was blocked in testing, even
    # though robots.txt declares no crawling restrictions), so we present as
    # a standard desktop browser here.
    pib_request_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    pib_request_timeout_seconds: float = 20.0
    pib_request_max_retries: int = 3
    # Politeness delay between successive detail-page fetches within one scrape pass.
    pib_request_delay_seconds: float = 1.0

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    anthropic_max_retries: int = 2
    # Politeness delay between successive enrichment calls within one enrich pass.
    anthropic_request_delay_seconds: float = 0.5

    # Claude rates each release 1-5 on how much study time it deserves (see
    # the anchors in enrichment/prompts.py); this is the score at or above
    # which an article counts as UPSC-relevant — which drives both the
    # dashboard's "UPSC-relevant only" filter and whether subscribers get a
    # Telegram message. It's a separate knob from the prompt's content bar
    # (fixed at 3, the score from which questions get generated) precisely so
    # notification strictness can be tuned without re-enriching the corpus:
    # raise this to 4 to be notified only about substantive developments.
    upsc_relevance_threshold: int = 3

    # The point-level study-notes pass costs a second Claude call per article,
    # so the cheap article-level score above gates it: only releases scoring at
    # least this much are worth the deep extraction. Most of what PIB publishes
    # is operational communication that would yield nothing.
    study_notes_enabled: bool = True
    study_notes_min_relevance: int = 3

    # sentence-transformers model used to embed articles for similarity search.
    embedding_model: str = "all-MiniLM-L6-v2"
    similarity_top_k: int = 5
    # Minimum cosine similarity (embeddings are unit-normalized) for a past
    # article to even be considered a candidate before Claude adjudicates it.
    similarity_threshold: float = 0.45

    telegram_bot_token: str | None = None
    # Delay between successive outbound sends in `notify`, to stay comfortably
    # under Telegram's flood-control limits (30 msgs/sec globally).
    telegram_send_delay_seconds: float = 0.2

    # Chat that receives operational alerts when a pipeline run doesn't fully
    # succeed. Without this the only symptom of a break is silence: PIB
    # changed its listing markup on 2026-08-14 and every run failed for
    # ~7 hours before anyone looked at a log. Accepts the older
    # TELEGRAM_CHAT_ID spelling so existing .env files keep working.
    telegram_admin_chat_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_ADMIN_CHAT_ID", "TELEGRAM_CHAT_ID"),
    )
    # Escape hatch for local experiments; alerts are on whenever a token and
    # an admin chat are both configured.
    ops_alerts_enabled: bool = True

    # Off by default so a plain `pib-agent serve` for local dev/testing never
    # silently starts spending Claude/Telegram API calls on a schedule — the
    # user opts in explicitly for unattended daily operation.
    scheduler_enabled: bool = False
    # PIB has no push/webhook mechanism, so "real-time" means frequent
    # polling — kept short since polling itself is nearly free (a couple of
    # lightweight listing-page fetches; Claude spend only scales with new
    # articles actually found, not with how often we check).
    scheduler_interval_minutes: int = 5
    scheduler_start_hour_ist: int = 9
    scheduler_end_hour_ist: int = 21
    scheduler_timezone: str = "Asia/Kolkata"
    # Minimum gap between successive manual /admin/run-now triggers, so
    # repeated clicks can't fire off duplicate full pipeline runs.
    admin_run_now_min_interval_seconds: float = 60.0

    # Re-export the static bundle after each run and push it, so the deployed
    # site tracks the database instead of drifting a day further behind for
    # every day nobody runs `export-static` by hand. Off by default for the
    # same reason as the scheduler: a local dev run must never push to a
    # public repo on its own — the operator opts in for unattended operation.
    publish_enabled: bool = False

    # --- Sign-in -----------------------------------------------------------
    # OAuth client ids. Google: Cloud Console -> OAuth 2.0 Client ID (Web).
    # Telegram: BotFather -> your bot -> Login Widget (Telegram moved the
    # widget to OpenID Connect; the old HMAC hash scheme is archived).
    # Sign-in for a provider is simply unavailable while its id is unset.
    google_client_id: str | None = None
    telegram_client_id: str | None = None

    session_ttl_days: int = 30
    session_cookie_name: str = "pib_session"
    # Must be True wherever the site is served over HTTPS. Left False by
    # default so local http://localhost development works; production
    # deployments have to set it.
    session_cookie_secure: bool = False

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Origins allowed to call the API from a browser (the Vite dev server).
    # Unused in production, where the API and SPA share one origin.
    cors_allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        """Accept the DATABASE_URL managed Postgres platforms actually hand out.

        Railway (and Heroku, and most others) set `postgresql://…` or the
        legacy `postgres://…`. SQLAlchemy 2 needs an explicit driver, and this
        project uses psycopg3, so both are rewritten to `postgresql+psycopg://`
        — which means the platform's own variable works untouched instead of
        failing at import with "Can't load plugin: sqlalchemy.dialects:postgres".
        """
        value = value.strip().strip('"').strip("'")

        # An unresolved platform reference arrives as the literal text, and an
        # unset-but-present variable arrives empty. Both reach SQLAlchemy as
        # "Could not parse SQLAlchemy URL from given URL string" thrown at
        # import time, which says nothing about where the bad value came from.
        if not value:
            raise ValueError(
                "DATABASE_URL is empty. If it's set to a platform reference like "
                "${{Postgres.DATABASE_PUBLIC_URL}}, that variable doesn't exist on the "
                "referenced service — check the name, or paste the connection string directly."
            )
        if value.startswith("${") or "://" not in value:
            raise ValueError(
                f"DATABASE_URL doesn't look like a connection string: {_redact(value)}. "
                "An unresolved platform reference is stored verbatim rather than "
                "substituted, so check the service and variable names."
            )

        # Pasting a whole `KEY=value` line into a value field is easy to do and
        # leaves a string that passes every shape check above.
        if "=" in value.split("://", 1)[0]:
            key = value.split("=", 1)[0]
            raise ValueError(
                f"DATABASE_URL looks like it includes the variable name ({key}=...). "
                "Paste only the connection string itself, not the whole line."
            )

        if value.startswith("postgresql+"):
            normalised = value
        elif value.startswith(("postgresql://", "postgres://")):
            _, rest = value.split("://", 1)
            normalised = "postgresql+psycopg://" + rest
        else:
            normalised = value

        # Validate with the parser that will actually be used, so a bad value
        # fails here — naming the variable — rather than as an opaque
        # ArgumentError raised while importing pib_agent.db.
        from sqlalchemy.engine.url import make_url

        try:
            make_url(normalised)
        except Exception as exc:
            raise ValueError(
                f"DATABASE_URL could not be parsed as a connection string "
                f"({_redact(normalised)}): {exc}. Special characters in the password "
                "(#, @, /, ?) must be percent-encoded."
            ) from exc

        return normalised


@lru_cache
def get_settings() -> Settings:
    return Settings()
