"""add users auth identities sessions and user-scoped subscriptions

Revision ID: c7c00a3ad67c
Revises: e7aead8ba0f4
Create Date: 2026-08-14 18:20:00.000000

Subscriptions used to key straight off a Telegram chat_id, which made the
Telegram account the only identity in the system. This introduces a real User
that can own several sign-in methods, and re-points subscriptions at it.

The data step matters: every existing chat_id becomes a User with a matching
`telegram` AuthIdentity whose `subject` is that same chat_id, so notifications
keep resolving to the same Telegram chat and nobody loses a subscription.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7c00a3ad67c'
down_revision: Union[str, Sequence[str], None] = 'e7aead8ba0f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=320), nullable=True),
        sa.Column('avatar_url', sa.String(length=512), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'auth_identities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'subject', name='uq_auth_identities_provider_subject'),
    )
    op.create_index('ix_auth_identities_user_id', 'auth_identities', ['user_id'])

    op.create_table(
        'user_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])
    op.create_index('ix_user_sessions_token_hash', 'user_sessions', ['token_hash'], unique=True)

    # --- subscriptions: chat_id -> user_id ---------------------------------
    op.add_column('subscriptions', sa.Column('user_id', sa.Integer(), nullable=True))

    connection = op.get_bind()
    chat_ids = [
        row[0]
        for row in connection.execute(
            sa.text('SELECT DISTINCT chat_id FROM subscriptions ORDER BY chat_id')
        )
    ]

    for chat_id in chat_ids:
        result = connection.execute(
            sa.text(
                'INSERT INTO users (display_name, created_at) '
                'VALUES (:name, CURRENT_TIMESTAMP)'
            ),
            {'name': f'Telegram {chat_id}'},
        )
        user_id = result.lastrowid
        connection.execute(
            sa.text(
                'INSERT INTO auth_identities (user_id, provider, subject, created_at) '
                "VALUES (:user_id, 'telegram', :subject, CURRENT_TIMESTAMP)"
            ),
            {'user_id': user_id, 'subject': str(chat_id)},
        )
        connection.execute(
            sa.text('UPDATE subscriptions SET user_id = :user_id WHERE chat_id = :chat_id'),
            {'user_id': user_id, 'chat_id': chat_id},
        )

    # Drop chat_id's index first: batch mode rebuilds the table and replays its
    # indexes, so an index over a column we're about to drop fails on replay.
    op.drop_index('ix_subscriptions_chat_id', table_name='subscriptions')

    # SQLite can't drop a column or swap a constraint in place, so the table is
    # rebuilt; batch_alter_table handles that uniformly across backends.
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint('uq_subscriptions_chat_ministry', type_='unique')
        batch_op.create_unique_constraint(
            'uq_subscriptions_user_ministry', ['user_id', 'ministry_id']
        )
        batch_op.create_foreign_key(
            'fk_subscriptions_user_id_users', 'users', ['user_id'], ['id']
        )
        batch_op.drop_column('chat_id')
    op.create_index('ix_subscriptions_user_id', 'subscriptions', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_subscriptions_user_id', table_name='subscriptions')
    op.add_column('subscriptions', sa.Column('chat_id', sa.BigInteger(), nullable=True))

    # Recover each subscription's Telegram chat from its owner's identity.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            'UPDATE subscriptions SET chat_id = ('
            '  SELECT CAST(ai.subject AS INTEGER) FROM auth_identities ai'
            "  WHERE ai.user_id = subscriptions.user_id AND ai.provider = 'telegram'"
            '  LIMIT 1'
            ')'
        )
    )
    # A user with no Telegram identity has no chat to go back to.
    connection.execute(sa.text('DELETE FROM subscriptions WHERE chat_id IS NULL'))

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.alter_column('chat_id', existing_type=sa.BigInteger(), nullable=False)
        batch_op.drop_constraint('fk_subscriptions_user_id_users', type_='foreignkey')
        batch_op.drop_constraint('uq_subscriptions_user_ministry', type_='unique')
        batch_op.create_unique_constraint(
            'uq_subscriptions_chat_ministry', ['chat_id', 'ministry_id']
        )
        batch_op.drop_column('user_id')
    op.create_index('ix_subscriptions_chat_id', 'subscriptions', ['chat_id'])

    op.drop_index('ix_user_sessions_token_hash', table_name='user_sessions')
    op.drop_index('ix_user_sessions_user_id', table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_index('ix_auth_identities_user_id', table_name='auth_identities')
    op.drop_table('auth_identities')
    op.drop_table('users')
