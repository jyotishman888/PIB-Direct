# PIB Agent

Scrapes daily press releases from India's Press Information Bureau (PIB),
enriches each one with Claude (summary, background context, links to similar
past releases, and UPSC-relevant exam questions), and serves a ministry-wise
dashboard with Telegram subscriptions.

Built milestone by milestone — see `M<N>` markers below for what's currently
implemented.

## Requirements

- Python 3.12 (managed automatically by `uv` if not already installed)
- [`uv`](https://docs.astral.sh/uv/) for dependency management and running
  commands
- Node.js 20+ and npm, for the `frontend/` dashboard (M5)

## Setup

```bash
cd pib-agent
uv sync                          # installs all dependencies into ./.venv
cp .env.example .env              # then fill in secrets as milestones require them
uv run alembic upgrade head       # creates ./data/pib_agent.db with the current schema
```

## Running tests / lint

```bash
uv run pytest
uv run ruff check .
```

`tests/test_similarity_embeddings.py` is marked `slow` — it exercises the
real local `sentence-transformers` model (downloads weights on first run,
cached afterward). Skip it for a fast inner loop: `uv run pytest -m "not slow"`.

## CLI

```bash
uv run pib-agent --help
uv run pib-agent version
uv run pib-agent doctor    # check the live PIB listing still parses
uv run pib-agent backup    # timestamped copy of the SQLite database
```

## Configuration

All configuration is read from environment variables / `.env` (see
`.env.example`), loaded via `pib_agent.config.get_settings()`:

| Variable              | Purpose                                              | Added in |
|-----------------------|-------------------------------------------------------|----------|
| `DATABASE_URL`        | SQLAlchemy connection string (defaults to local SQLite) | M0 |
| `LOG_LEVEL`           | Root logger level                                     | M0 |
| `ANTHROPIC_API_KEY`   | Claude API key for the enrichment pipeline             | M2 |
| `ANTHROPIC_MODEL`     | Model used for enrichment/similarity (default `claude-sonnet-5`) | M2 |
| `EMBEDDING_MODEL`     | sentence-transformers model for similarity search (default `all-MiniLM-L6-v2`) | M3 |
| `SIMILARITY_TOP_K`    | Max candidate past articles sent to Claude per check (default `5`) | M3 |
| `SIMILARITY_THRESHOLD`| Min cosine similarity for a candidate to be considered (default `0.45`) | M3 |
| `API_HOST`            | REST API bind host (default `127.0.0.1`)               | M4 |
| `API_PORT`            | REST API bind port (default `8000`)                    | M4 |
| `CORS_ALLOWED_ORIGINS`| Browser origins allowed to call the API (default: the Vite dev server) | M4 |
| `TELEGRAM_BOT_TOKEN`  | Bot token from @BotFather for notifications            | M6 |
| `TELEGRAM_SEND_DELAY_SECONDS` | Delay between successive Telegram sends in `notify`, to stay under Telegram's flood limits (default `0.2`) | M6 |
| `SCHEDULER_ENABLED`   | Run the scrape→enrich→link→notify pipeline on a schedule inside `pib-agent serve` (default `false`) | M7 |
| `SCHEDULER_INTERVAL_MINUTES` | Minutes between scheduled pipeline runs (default `5` — polling is nearly free, so this stays short for near-real-time notifications) | M7 |
| `SCHEDULER_START_HOUR_IST` / `SCHEDULER_END_HOUR_IST` | Hour range (24h, inclusive) the schedule is active in `SCHEDULER_TIMEZONE` (default `9`–`21`) | M7 |
| `SCHEDULER_TIMEZONE`  | IANA timezone the schedule's hour range is evaluated in (default `Asia/Kolkata`) | M7 |
| `ADMIN_RUN_NOW_MIN_INTERVAL_SECONDS` | Minimum gap between manual `/admin/run-now` triggers (default `60`) | M7 |

## Database migrations

Schema is managed with Alembic. `alembic/env.py` pulls the DB URL from the
app's own settings (not a separate hardcoded URL in `alembic.ini`), so a
single `.env` is the source of truth.

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

## Scraping PIB

```bash
uv run pib-agent scrape
```

Fetches every listing source in `PIB_LISTING_URLS` (`config.py`; defaults to
`reg=3` "PIB Delhi" + `reg=48` "National"), merges and dedupes the results
by PRID, skips anything already in the DB, fetches+parses each new
release's detail page, and persists it. Safe to run repeatedly / on a
schedule — it's idempotent by PRID.

PIB's `reg` query param selects a **regional bureau**, not a ministry —
each bureau's listing surfaces a different, only-partly-overlapping set of
ministries/organizations (confirmed live: `reg=3` alone misses Commerce,
Culture, Education, Minority Affairs, Parliamentary Affairs, Statistics,
Tourism, UPSC, and the President's Secretariat, all of which show up under
`reg=48`). Delhi + National together cover essentially all central-government
ministries without pulling in the other ~27 city/state-specific bureaus;
add more `reg=` URLs to `PIB_LISTING_URLS` for broader (but much
higher-volume) coverage. One listing source failing doesn't lose releases
from the others — `ScrapeStats.listing_sources_failed` tracks that
separately from per-article failures; the scrape only raises if every
configured source fails.

Note: pib.gov.in's WAF rejects non-browser-looking User-Agent strings (see
`pib_request_user_agent` in `config.py`), so the client presents as a
standard desktop browser even though `robots.txt` declares no crawling
restrictions.

## Enriching articles

```bash
uv run pib-agent enrich
```

For every scraped article without an `Enrichment` row yet, calls Claude
(`ANTHROPIC_MODEL`, default `claude-sonnet-5`) for a structured
summary/background-context/UPSC-relevance judgement, with Prelims MCQs and
Mains questions generated only when the release is judged exam-relevant.
Uses the Messages API's structured-output mode (`output_format=`) so the
response is validated against a Pydantic schema, not regex-parsed. Idempotent
by article — safe to run repeatedly / on a schedule.

## Linking related past coverage

```bash
uv run pib-agent link
```

Two phases, both idempotent:

1. **Embed** — any enriched article without an embedding yet gets one, computed
   locally with `sentence-transformers` (`EMBEDDING_MODEL`, default
   `all-MiniLM-L6-v2`) over its title + Claude-written summary. No API calls,
   no cost.
2. **Link** — for any embedded article not yet checked, find prior articles
   (lower id, i.e. scraped earlier) above `SIMILARITY_THRESHOLD` cosine
   similarity via brute-force NumPy search, take the top `SIMILARITY_TOP_K`,
   and ask Claude which (if any) are *genuinely* related in substance — same
   scheme, campaign, or direct follow-up, not just similar wording. If there
   are zero candidates above the threshold, Claude isn't called at all. Every
   checked article is marked done (`Embedding.linked_at`) regardless of
   whether it produced any links, so a bare "nothing related" result is never
   re-sent to Claude on the next run.

## REST API

```bash
uv run pib-agent serve            # http://127.0.0.1:8000, add --reload for dev
```

Interactive docs at `/docs` (Swagger UI) and `/redoc`; raw schema at
`/openapi.json`.

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness check |
| `GET /ministries` | All ministries with their article count, alphabetical |
| `GET /articles` | Paginated article list. Filters: `ministry` (slug), `upsc_relevant` (bool), `search` (title/summary substring), `date_from`/`date_to`. Params: `limit` (≤100, default 20), `offset`. Newest release first, undated releases last. |
| `GET /articles/{id}` | Full detail: body text, enrichment (summary/context/UPSC questions), and related past releases with the linking note. 404 if not found. |

Built with FastAPI; DB access goes through a per-request session dependency
(`api/deps.py`) so tests can swap in an isolated database via
`app.dependency_overrides`. CORS is restricted to `CORS_ALLOWED_ORIGINS`
(defaults to the Vite dev server the dashboard uses).

## Dashboard frontend

```bash
uv run pib-agent serve            # backend, in one terminal
cd frontend && npm install        # first time only
npm run dev                        # http://localhost:5173, in another terminal
```

React + Vite + TypeScript + Tailwind CSS v4 + Ant Design (`antd`) SPA.
Ministry sidebar (article counts, click to filter) drives a paginated,
filterable article feed — search, UPSC-relevant toggle, date range — all
stored in the URL's query string so views are bookmarkable/shareable and
the browser back button works. The article detail page renders the
Claude-written summary/context, UPSC syllabus tags, interactive Prelims
MCQs (click an option to reveal correct/incorrect + explanation), Mains
questions, and related past coverage with the linking note from M3.

Ant Design components (`Menu`, `Drawer`, `Input.Search`,
`DatePicker.RangePicker`, `Pagination`, `Tag`, `Radio.Group`, `Collapse`,
`Empty`/`Result`/`Spin`/`Skeleton`) are themed via `ConfigProvider`
(`src/theme/antdTheme.ts`) to match the site's existing green/serif look
rather than antd's default blue — tokens mirror the CSS variables in
`index.css`, and `useColorScheme` (`src/hooks/`) keeps antd's light/dark
algorithm in sync with the same `prefers-color-scheme`/`data-theme`
mechanism the rest of the app already uses. Tailwind and antd coexist via
CSS cascade layers (`@layer theme, base, antd, components, utilities` in
`index.css` + `<StyleProvider layer>` in `App.tsx`, per antd's official
Tailwind compatibility guide) so Tailwind utility classes reliably win
without `!important` hacks.

Data fetching goes through TanStack Query (`src/hooks/`) against a typed
API client (`src/api/client.ts`, `src/api/types.ts` — hand-mirrors the
backend's Pydantic response schemas). Set `VITE_API_BASE_URL` in
`frontend/.env.local` to point at a non-default backend (see
`frontend/.env.example`).

```bash
cd frontend
npm run build     # tsc type-check + production build to dist/
npm run lint       # oxlint
```

## Telegram bot + notifications

```bash
uv run pib-agent bot        # long-running: interactive commands (subscribe/unsubscribe)
uv run pib-agent notify     # one-shot: dispatch notifications for un-notified articles
```

Get a token from [@BotFather](https://t.me/BotFather) (`/newbot`) and set
`TELEGRAM_BOT_TOKEN` in `.env`.

`pib-agent bot` runs the interactive side via long polling (no public URL
needed locally):

| Command | Description |
|---------|-------------|
| `/start`, `/help` | Welcome message + the ministry picker |
| `/ministries` | Inline-button keyboard — tap a ministry to subscribe/unsubscribe, ✅ marks current subs |
| `/subscribe <slug>` | Subscribe directly by ministry slug |
| `/unsubscribe <slug>` | Unsubscribe directly by ministry slug |
| `/mysubs` | List current subscriptions |

`pib-agent notify` is the dispatch side: for every enriched article not yet
notified, **if it's UPSC-relevant**, it messages every subscriber of that
article's ministry (title, summary, UPSC badge, link to the original PIB
release). Non-UPSC-relevant releases are never dispatched — a ministry
subscription is a bet on UPSC-relevant coverage, not every routine PIB
notice — but are still marked notified (`Enrichment.notified_at`), same as
articles with zero subscribers, so nothing is ever re-checked or re-sent.
A chat that has blocked the bot (`Forbidden`) has all its subscriptions
dropped automatically; other delivery errors are logged but don't touch
subscriptions, since they aren't proof the chat is actually dead. Meant to
run right after `enrich`/`link` in the M7 daily pipeline, not continuously.

## Accounts & sign-in

Reading the dashboard needs no account. Signing in is what makes subscriptions
follow you across devices, and it's the prerequisite for anything personalised.

A **User** owns the data. Each way of signing in is an **AuthIdentity** row
(`provider` + the provider's `subject`), so one person can hold both a Google
and a Telegram identity and still be one account. Subscriptions hang off the
user, not off a Telegram chat as they used to.

### Providers

Both Telegram and Google issue an OpenID Connect **ID token** to the browser,
which the backend verifies against the provider's JWKS before trusting a single
claim — one code path covers both (`src/pib_agent/auth/verify.py`).

> Telegram moved its Login Widget to OpenID Connect; the older
> HMAC `data-check-string` scheme is archived and is *not* what this uses.

| Provider | Where the client id comes from |
|----------|-------------------------------|
| Google | Cloud Console → OAuth 2.0 Client ID (Web); add `http://localhost:5173` as an authorized JavaScript origin |
| Telegram | BotFather → your bot → **Login Widget**; requires a registered domain |

```bash
# .env
GOOGLE_CLIENT_ID=...
TELEGRAM_CLIENT_ID=...
SESSION_COOKIE_SECURE=false   # true wherever you serve over HTTPS

# frontend/.env.local — must match
VITE_GOOGLE_CLIENT_ID=...
VITE_TELEGRAM_CLIENT_ID=...
```

Leave a provider's ids blank and its button is simply hidden — `GET
/auth/providers` reports what's actually configured, so the login page never
offers a button that would fail.

Google works on `localhost`. Telegram needs a real domain, so it may not be
testable locally without a tunnel.

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /auth/providers` | Which sign-in methods this server can offer |
| `POST /auth/{provider}` | Verify an ID token, sign in, set the session cookie |
| `POST /auth/{provider}/link` | Connect a second provider to the signed-in account |
| `GET /auth/session` | Current user, or `null` — never 401s, for anonymous page loads |
| `GET /auth/me` | Current user; `401` when signed out |
| `POST /auth/logout` | Revoke the session |
| `GET`/`PUT /auth/subscriptions` | Read/replace the signed-in user's ministries |

Sessions are server-side (`user_sessions`), so they can be revoked. The cookie
holds an opaque random token; only its SHA-256 hash is stored, and it's set
`httponly` + `samesite=lax`.

### The bot and the web are one account

The bot still works purely in terms of chat ids — `handlers.py` was not touched.
`subscriptions.py` resolves a chat to its user behind the scenes and creates the
account on first contact, so someone can use the bot for months without ever
visiting the site.

Because Telegram's ID token carries that same id as its `sub`, signing in on the
web with Telegram lands on **the existing account**, subscriptions and all. A
Google-only user simply isn't in the Telegram dispatch list until they connect
Telegram from the account page.

## Orchestration & scheduling

```bash
uv run pib-agent run    # one-shot: scrape -> enrich -> link -> notify, waits for it to finish
```

`pib-agent run` chains all four pipeline stages end to end. Stages are
isolated from one another: if one raises (e.g. PIB's site is briefly
unreachable), it's recorded as failed and the remaining stages still run
against whatever earlier stages already persisted — a bad scrape doesn't
stop `enrich`/`link`/`notify` from processing articles from previous runs.
Exits non-zero if any stage failed outright or reported per-item failures.
If Telegram isn't configured yet, the `notify` stage is recorded as
`skipped`, not `failed`.

Every run (CLI, scheduled, or triggered via the API) is persisted as a
`PipelineRun` row — one entry per stage with its status and summary — so
there's a queryable audit trail instead of only scrollback logs. Only one
run executes at a time; a scheduled run that overlaps a still-running
manual one is skipped rather than queued.

### Automatic scheduling

Set `SCHEDULER_ENABLED=true` in `.env` and the same pipeline runs
automatically inside `pib-agent serve`, every `SCHEDULER_INTERVAL_MINUTES`
minutes between `SCHEDULER_START_HOUR_IST` and `SCHEDULER_END_HOUR_IST`
(defaults: every 5 minutes, 9am–9pm `SCHEDULER_TIMEZONE`, since that's when
PIB actually publishes). PIB has no push/webhook mechanism, so this polling
loop is what "real-time" notifications actually means in practice — a short
interval is cheap since polling itself is just a couple of lightweight
listing-page fetches; Claude/Telegram spend only scales with new articles
actually found, not with how often the interval fires. It's off by default
so a plain `pib-agent serve` for local dev never silently starts spending
API calls on a timer — this is an explicit opt-in for unattended operation.

### Admin API

| Endpoint | Description |
|----------|-------------|
| `POST /admin/run-now` | Trigger a pipeline run immediately; returns `202` with the new run (`status: "running"`) right away, the run itself executes in the background. `409` if a run is already in progress, `429` if triggered again within `ADMIN_RUN_NOW_MIN_INTERVAL_SECONDS`. |
| `GET /admin/runs` | Paginated run history, newest first. |
| `GET /admin/runs/{id}` | One run's detail: per-stage status/summary/error. `404` if not found. |

The `429` guard exists specifically so repeated manual triggers (e.g. someone
double-clicking a "run now" button) can't fire off duplicate full pipeline
runs against PIB/Claude/Telegram back to back.

## Deployment (Railway)

Local development stays on SQLite; every Postgres branch is conditional on
`DATABASE_URL`, so nothing here changes how you run it on your machine.

### Why it's shaped this way

- **One origin.** The API is served under `/api` and the built SPA off the
  same host, because `/articles` is both an endpoint and a frontend route.
  More importantly it keeps the session cookie *first-party* — splitting the
  frontend and API across hosts would need `SameSite=None` third-party
  cookies, which browsers increasingly block.
- **A Dockerfile, not autodetection.** On Linux, `pip install torch` pulls the
  CUDA build: gigabytes of NVIDIA libraries this app never uses. The image
  installs the CPU wheel first so the CUDA one is never resolved.
- **One web replica.** The pipeline lock spans processes on Postgres (a
  `pg_try_advisory_lock`, see `orchestration/run_lock.py`), so overlapping
  instances during a rolling deploy decline instead of each firing a run and
  double-spending on Claude. Extra replicas are safe but pointless — only one
  would ever hold the lock.

### Services

| Service | Start command | Notes |
|---------|---------------|-------|
| Postgres | — (Railway plugin) | Railway manages its own backups |
| `web` | `pib-agent serve --host 0.0.0.0 --port $PORT` | Public domain, healthcheck `/api/health`, `SCHEDULER_ENABLED=true` |
| `bot` | `pib-agent bot` | No public domain; long-polls Telegram, `SCHEDULER_ENABLED=false` |

Both build from the same `Dockerfile`; only the start command differs. Point
`DATABASE_URL` at the Postgres plugin with a reference variable so both
services share it.

### Variables

Runtime (set in Railway):

```
DATABASE_URL              # reference the Postgres plugin
ANTHROPIC_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_ADMIN_CHAT_ID
GOOGLE_CLIENT_ID
TELEGRAM_CLIENT_ID
SESSION_COOKIE_SECURE=true
SCHEDULER_ENABLED=true    # web only
```

Build-time (Docker build args — **not** runtime variables):

```
VITE_GOOGLE_CLIENT_ID
VITE_TELEGRAM_CLIENT_ID
```

These are compiled into the JS bundle. Setting them only as runtime variables
is the easy mistake: the app boots fine and the login page silently offers no
buttons.

### Register the domain with both providers

Once Railway gives you `https://<name>.up.railway.app`:

| Console | Field | Value |
|---------|-------|-------|
| Google Cloud → Credentials | Authorized **JavaScript origins** | `https://<name>.up.railway.app` |
| BotFather → bot → Login Widget | Domain | `<name>.up.railway.app` |

Google's field must be JavaScript origins, not redirect URIs — this flow
returns the token to the page and never redirects.

### Moving the existing data across

Run migrations against the new database first, then copy rows:

```bash
alembic upgrade head                       # with DATABASE_URL pointed at Postgres
uv run python scripts/migrate_sqlite_to_postgres.py \
  --source sqlite:///data/pib_agent.db \
  --target "$DATABASE_URL"
```

Ids are preserved, since `article_links` and `subscriptions` reference them
and the Telegram `AuthIdentity.subject` is what keeps existing subscribers
attached to their notifications. Sequences are reset afterwards. The script
refuses to run against a target that already has articles unless you pass
`--force`.

`pib-agent backup` is SQLite-only. On Postgres, use Railway's backups (or
`pg_dump`); the command will tell you so rather than doing something useless.

## Running unattended locally

To let the whole thing run on its own — dashboard API up, pipeline on a
schedule — start it once with scheduling enabled:

```bash
# .env
SCHEDULER_ENABLED=true
```

```bash
uv run pib-agent serve
```

That single process now serves the dashboard API *and* runs
scrape→enrich→link→notify on the configured interval for as long as it's
up. To keep it running across logins/reboots on Windows, either:

- **Task Scheduler** (simplest, no extra install): create a task that runs
  at log on / at startup, action `uv run pib-agent serve` with "Start in"
  set to the project directory. Good enough for a machine that's normally
  logged in and left running.
- **[NSSM](https://nssm.cc/)** (runs as an actual Windows service,
  restarts automatically on crash, no login required): `nssm install
  PibAgent "<path to uv.exe>" "run pib-agent serve"`, set "Startup
  directory" to the project root, then `nssm start PibAgent`.

Either way, if the process is ever killed mid-run, the next startup marks
that interrupted `PipelineRun` row as `failed` (via `mark_interrupted_runs`,
called at the top of `serve`) so the admin run history stays accurate
instead of showing a run stuck "running" forever.

### Knowing when it breaks

An unattended pipeline fails silently by default, and silence looks exactly
like "nothing new to fetch". On 2026-08-14 PIB changed its listing markup so
every release link became a JS `onclick` handler instead of an `href`; the
scraper raised on every run for about seven hours before anyone read a log.

Two things guard against a repeat:

```bash
# .env — your own chat id, not the bot's
TELEGRAM_ADMIN_CHAT_ID=123456789
```

**Run alerts.** Whenever a run finishes `failed` or `partial_failure`, the
bot messages that chat with the run id, trigger, and each failing stage's
error. Successful runs say nothing. Alerts never raise — a failure to report
a problem must not become a second problem — so a broken alert channel can't
take the pipeline down with it.

**`pib-agent doctor`.** Fetches every configured listing URL and checks it
still parses, exiting non-zero when it doesn't (and alerting). Worth running
on its own schedule, since it catches upstream markup changes even on a quiet
day with no new releases:

```bash
uv run pib-agent doctor
```

The matching `pytest -m live` suite does the same against the real site and
is excluded from normal runs. This distinction matters: the fixture-based
tests were 100% green throughout the outage above, because fixtures only ever
prove the parser still handles HTML captured in the past — not the HTML PIB
is serving now.

### Backups

The database holds every enrichment you've paid Claude to produce, in one
SQLite file:

```bash
uv run pib-agent backup            # keeps the 7 most recent
uv run pib-agent backup --keep 30
```

Backups land in `data/backups/` and use SQLite's online backup API rather
than a file copy, so it's safe to run while the app is mid-write.

## Project layout

```
src/pib_agent/
  config.py           # Settings (env vars / .env)
  logging_config.py   # console + rotating file logging (UTF-8 safe)
  utils.py             # slugify()
  cli.py               # `pib-agent` Typer CLI entrypoint
  db/
    base.py            # SQLAlchemy engine/session
    models.py           # Ministry, Article ORM models
  scraper/
    http_client.py      # retrying HTTP fetch
    listing_parser.py    # parses the ministry-grouped release listing
    detail_parser.py     # parses an individual release page
    pipeline.py           # orchestrates fetch -> parse -> dedupe -> persist
  enrichment/
    schema.py             # Pydantic output schema (ArticleEnrichment, ...)
    prompts.py             # system/user prompt construction
    client.py               # Claude API call + structured-output parsing
    pipeline.py               # orchestrates: find un-enriched -> enrich -> persist
  similarity/
    embeddings.py          # sentence-transformers model loader + embed_text()
    vectors.py               # numpy <-> bytes (de)serialization for storage
    schema.py                 # Pydantic output schema (SimilarityResult, ...)
    prompts.py                 # system/user prompt construction
    client.py                   # Claude API call for the linking judgement
    pipeline.py                   # orchestrates: embed -> candidate search -> link -> persist
  api/
    deps.py                        # per-request DB session dependency
    schemas.py                      # Pydantic response models
    mapping.py                       # ORM -> response model conversion
    app.py                            # FastAPI app factory + CORS + lifespan (scheduler) + router registration
    routers/                          # health, ministries, articles, admin
  telegram/
    subscriptions.py       # DB helpers (list/toggle/subscribe by slug, subscriber lookup)
    keyboards.py             # inline ministry-picker keyboard
    handlers.py                # /start /ministries /subscribe /unsubscribe /mysubs
    bot.py                       # Application wiring + long polling
    notify.py                      # dispatch pipeline: enriched-but-unnotified -> Telegram
  orchestration/
    pipeline.py             # chains scrape->enrich->link->notify, stage isolation, run lock, PipelineRun persistence
    scheduler.py               # APScheduler wiring (cron window over the Indian working day)
alembic/                # migrations
tests/                  # pytest suite (isolated in-memory/temp-file SQLite)
  fixtures/              # real PIB HTML captured for offline parser tests

frontend/
  src/
    api/                  # typed fetch client + response types (mirrors backend schemas)
    hooks/                 # TanStack Query hooks + useDebouncedValue, useColorScheme
    theme/                  # antdTheme.ts — ConfigProvider tokens (light/dark)
    components/
      layout/                # Header, MinistrySidebar (antd Menu)
      articles/               # ArticleCard, FilterBar, Pagination, badges (list view)
      detail/                  # EnrichmentSection, Prelims/MainsQuestionCard, RelatedArticles
      common/                   # LoadingState, ErrorState, EmptyState (antd Spin/Result/Empty)
    pages/                 # DashboardPage, ArticleDetailPage
    lib/                    # formatDate, tagStyles
```

## Milestone status

- [x] **M0** — Project scaffolding: structure, config, DB models + migrations, logging, tooling
- [x] **M1** — PIB scraper
- [x] **M2** — Claude enrichment pipeline
- [x] **M3** — Related past incidents (similarity)
- [x] **M4** — Backend REST API
- [x] **M5** — Dashboard frontend
- [x] **M6** — Telegram bot + notifications
- [x] **M7** — Orchestration, scheduling & hardening
