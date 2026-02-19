"""add cookie consent columns

Revision ID: 0303e56b757e
Revises: 4a89070ca79f
Create Date: 2026-02-19 14:46:59.837460

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0303e56b757e'
down_revision: Union[str, Sequence[str], None] = '4a89070ca79f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
