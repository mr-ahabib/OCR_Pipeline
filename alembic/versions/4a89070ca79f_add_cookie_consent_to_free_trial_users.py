"""add_cookie_consent_to_free_trial_users

Revision ID: 4a89070ca79f
Revises: 5c7d0e1f3g4h
Create Date: 2026-02-19 14:41:08.434736

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a89070ca79f'
down_revision: Union[str, Sequence[str], None] = '5c7d0e1f3g4h'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
