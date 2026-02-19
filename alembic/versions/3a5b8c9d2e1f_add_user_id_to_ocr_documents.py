"""add user_id to ocr_documents

Revision ID: 3a5b8c9d2e1f
Revises: 216127cc7adb
Create Date: 2026-02-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a5b8c9d2e1f'
down_revision: Union[str, Sequence[str], None] = '216127cc7adb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add user_id column as nullable first
    op.add_column('ocr_documents', sa.Column('user_id', sa.Integer(), nullable=True))
    
    # Create foreign key constraint
    op.create_foreign_key(
        'fk_ocr_documents_user_id',
        'ocr_documents',
        'users',
        ['user_id'],
        ['id']
    )
    
    # Create index on user_id
    op.create_index(op.f('ix_ocr_documents_user_id'), 'ocr_documents', ['user_id'], unique=False)
    
    # Note: In production, you would need to set user_id values for existing rows
    # before making it non-nullable. For now, we'll leave it nullable to avoid issues.
    # If you want to make it non-nullable, you'd need to:
    # 1. Set a default user_id for all existing rows
    # 2. Run: op.alter_column('ocr_documents', 'user_id', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_ocr_documents_user_id'), table_name='ocr_documents')
    op.drop_constraint('fk_ocr_documents_user_id', 'ocr_documents', type_='foreignkey')
    op.drop_column('ocr_documents', 'user_id')
