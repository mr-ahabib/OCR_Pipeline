"""add free trial users table

Revision ID: 5c7d0e1f3g4h
Revises: 4b6c9d0e2f3g
Create Date: 2026-02-19 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c7d0e1f3g4h'
down_revision: Union[str, Sequence[str], None] = '4b6c9d0e2f3g'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create free_trial_users table for tracking anonymous user trials"""
    op.create_table(
        'free_trial_users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('device_id', sa.String(length=255), nullable=False),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_usage', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('first_used_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cookie_id', sa.String(length=255), nullable=True),
        sa.Column('cookie_consent_given', sa.Boolean(), nullable=True),
        sa.Column('cookie_consent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('is_blocked', sa.Boolean(), nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for fast lookups
    op.create_index(op.f('ix_free_trial_users_id'), 'free_trial_users', ['id'], unique=False)
    op.create_index(op.f('ix_free_trial_users_device_id'), 'free_trial_users', ['device_id'], unique=True)
    op.create_index(op.f('ix_free_trial_users_cookie_id'), 'free_trial_users', ['cookie_id'], unique=False)


def downgrade() -> None:
    """Drop free_trial_users table"""
    op.drop_index(op.f('ix_free_trial_users_cookie_id'), table_name='free_trial_users')
    op.drop_index(op.f('ix_free_trial_users_device_id'), table_name='free_trial_users')
    op.drop_index(op.f('ix_free_trial_users_id'), table_name='free_trial_users')
    op.drop_table('free_trial_users')
