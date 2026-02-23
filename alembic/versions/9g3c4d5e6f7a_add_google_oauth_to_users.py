"""add google oauth to users

Revision ID: 9g3c4d5e6f7a
Revises: 7f2b3c4d5e6a
Create Date: 2026-02-22 00:00:00.000000

"""
from typing import Union, Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9g3c4d5e6f7a'
down_revision: Union[str, Sequence[str], None] = '7f2b3c4d5e6a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add google_id column (nullable, unique)
    op.add_column('users', sa.Column('google_id', sa.String(255), nullable=True))
    op.create_index(op.f('ix_users_google_id'), 'users', ['google_id'], unique=True)

    # Add auth_provider column (default = 'local')
    op.add_column('users', sa.Column('auth_provider', sa.String(50), nullable=True, server_default='local'))

    # Make hashed_password nullable (OAuth users may not have a password)
    op.alter_column('users', 'hashed_password', existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    # Revert hashed_password back to NOT NULL (set empty string for any nulls first)
    op.execute("UPDATE users SET hashed_password = '' WHERE hashed_password IS NULL")
    op.alter_column('users', 'hashed_password', existing_type=sa.String(255), nullable=False)

    op.drop_index(op.f('ix_users_google_id'), table_name='users')
    op.drop_column('users', 'google_id')
    op.drop_column('users', 'auth_provider')
