"""add study notes columns to enrichments

Both columns are nullable and carry no default: the study pass only runs for
articles clearing the relevance gate, so most rows legitimately never get one,
and every row predating the feature has none. That makes this purely additive —
existing rows and every code path unaware of the columns keep working.

Revision ID: 8b9c123d5a9f
Revises: c7c00a3ad67c
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8b9c123d5a9f"
down_revision: str | Sequence[str] | None = "c7c00a3ad67c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("enrichments", sa.Column("study_notes", sa.JSON(), nullable=True))
    op.add_column(
        "enrichments", sa.Column("study_classification", sa.String(length=16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("enrichments", "study_classification")
    op.drop_column("enrichments", "study_notes")
