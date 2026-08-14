"""add upsc_relevance score to enrichments

Revision ID: e7aead8ba0f4
Revises: c559f3554429
Create Date: 2026-08-14 15:58:29.142441

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7aead8ba0f4'
down_revision: Union[str, Sequence[str], None] = 'c559f3554429'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable on purpose: rows enriched before the score existed only ever
    # carried the boolean, and there's no honest score to backfill them with
    # short of re-running enrichment. NULL means "scored under the old
    # binary prompt" and is distinguishable from any real 1-5 rating.
    op.add_column('enrichments', sa.Column('upsc_relevance', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('enrichments', 'upsc_relevance')
