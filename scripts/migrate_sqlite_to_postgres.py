"""Copy the local SQLite database into Postgres, once, before going live.

Usage:
    uv run python scripts/migrate_sqlite_to_postgres.py \
        --source sqlite:///data/pib_agent.db \
        --target postgresql://user:pass@host:5432/railway

The target must already have the schema (`alembic upgrade head` against it).
This only moves rows.

Ids are preserved rather than regenerated, because they're referenced across
tables (article_links points at articles twice, subscriptions at users) and
because the Telegram AuthIdentity.subject is the thread that keeps existing
subscribers attached to their notifications. Sequences are reset afterwards so
the next insert doesn't collide with a preserved id.
"""

import argparse
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from pib_agent.db.base import Base
from pib_agent.db.models import (
    Article,
    ArticleLink,
    AuthIdentity,
    Embedding,
    Enrichment,
    Ministry,
    PipelineRun,
    Subscription,
    User,
    UserSession,
)

# Order matters: every table's foreign keys must already exist when it lands.
TABLES = [
    Ministry,
    Article,
    Enrichment,
    Embedding,
    ArticleLink,
    User,
    AuthIdentity,
    Subscription,
    UserSession,
    PipelineRun,
]


def _normalise(url: str) -> str:
    """Match the driver rewrite Settings does, so pasted URLs just work."""
    if url.startswith("postgresql+"):
        return url
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def _row_to_kwargs(model, row) -> dict:
    return {c.name: getattr(row, c.name) for c in model.__table__.columns}


def _reset_sequences(session: Session) -> None:
    """Point each identity sequence past the highest copied id.

    Without this, Postgres' sequence still sits at 1 while rows occupy 1..N,
    so the very next insert raises a duplicate-key error.
    """
    from sqlalchemy import text

    for model in TABLES:
        table = model.__table__.name
        session.execute(
            text(
                "SELECT setval("
                "  pg_get_serial_sequence(:table, 'id'),"
                "  COALESCE((SELECT MAX(id) FROM " + table + "), 1),"
                "  true)"
            ),
            {"table": table},
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="SQLite URL to read from")
    parser.add_argument("--target", required=True, help="Postgres URL to write to")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Copy even if the target already holds articles (rows are added, not replaced).",
    )
    parser.add_argument(
        "--create-schema",
        action="store_true",
        help="Create tables on the target first. Prefer `alembic upgrade head`.",
    )
    args = parser.parse_args()

    source_engine = create_engine(args.source)
    target_engine = create_engine(_normalise(args.target))

    if args.create_schema:
        Base.metadata.create_all(target_engine)

    with Session(source_engine) as src, Session(target_engine) as dst:
        existing = dst.scalar(select(func.count()).select_from(Article.__table__))
        if existing and not args.force:
            print(
                f"Target already holds {existing} articles. Refusing to run twice — "
                "pass --force if you really mean to add to it.",
                file=sys.stderr,
            )
            return 1

        total = 0
        for model in TABLES:
            rows = src.scalars(select(model).order_by(model.id)).all()
            for row in rows:
                dst.merge(model(**_row_to_kwargs(model, row)))
            dst.flush()
            print(f"{model.__tablename__:18} {len(rows):>5}")
            total += len(rows)

        _reset_sequences(dst)
        dst.commit()

    print(f"\nCopied {total} rows.")
    print("Verify before switching traffic: row counts, and that existing")
    print("subscriptions still resolve via get_subscriber_chat_ids().")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
