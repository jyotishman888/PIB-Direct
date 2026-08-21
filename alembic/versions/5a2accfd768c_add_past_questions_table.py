"""add past_questions table

Holds real questions from previous UPSC papers, fed only by
`pib-agent import-pyq` from an operator-supplied file. Nothing generates
these: a fabricated "asked in 2019" would be worse than having no PYQ
feature at all.

`syllabus_area` draws on the same closed vocabulary as
Enrichment.syllabus_topics, which is what lets a question be matched to an
article by a shared taxonomy rather than fuzzy text overlap.

Revision ID: 5a2accfd768c
Revises: 8b9c123d5a9f
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5a2accfd768c"
down_revision: str | Sequence[str] | None = "8b9c123d5a9f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "past_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("paper", sa.String(length=32), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("syllabus_area", sa.String(length=64), nullable=True),
        sa.Column("source_topic", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        # Re-importing the same file must not duplicate rows.
        sa.UniqueConstraint("year", "paper", "question", name="uq_past_questions_identity"),
    )
    op.create_index("ix_past_questions_year", "past_questions", ["year"])
    op.create_index("ix_past_questions_syllabus_area", "past_questions", ["syllabus_area"])
    op.create_index("ix_past_questions_area_year", "past_questions", ["syllabus_area", "year"])


def downgrade() -> None:
    op.drop_index("ix_past_questions_area_year", table_name="past_questions")
    op.drop_index("ix_past_questions_syllabus_area", table_name="past_questions")
    op.drop_index("ix_past_questions_year", table_name="past_questions")
    op.drop_table("past_questions")
