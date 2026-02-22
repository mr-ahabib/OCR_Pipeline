"""add subscription fields to users

Revision ID: 6e1a2b3c4d5f
Revises: 0303e56b757e
Create Date: 2026-02-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e1a2b3c4d5f'
down_revision: Union[str, Sequence[str], None] = '0303e56b757e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add subscription / free-trial quota columns to the users table."""
    op.add_column('users', sa.Column('free_ocr_used', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('subscription_pages_total', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('subscription_pages_used', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Remove subscription / free-trial quota columns from the users table."""
    op.drop_column('users', 'subscription_pages_used')
    op.drop_column('users', 'subscription_pages_total')
    op.drop_column('users', 'free_ocr_used')
