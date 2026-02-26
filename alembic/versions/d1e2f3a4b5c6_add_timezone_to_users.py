"""add_timezone_to_users

Revision ID: d1e2f3a4b5c6
Revises: cee5a3b592ca
Create Date: 2026-02-26 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'cee5a3b592ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add timezone column to users table."""
    op.add_column(
        'users',
        sa.Column(
            'timezone',
            sa.String(length=64),
            nullable=False,
            server_default='UTC',
        ),
    )


def downgrade() -> None:
    """Remove timezone column from users table."""
    op.drop_column('users', 'timezone')
