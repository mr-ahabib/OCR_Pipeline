"""add is_deleted to ocr_documents

Revision ID: 4b6c9d0e2f3g
Revises: 3a5b8c9d2e1f
Create Date: 2026-02-19 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b6c9d0e2f3g'
down_revision: Union[str, Sequence[str], None] = '3a5b8c9d2e1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add is_deleted column with default False
    op.add_column('ocr_documents', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    
    # Create index on is_deleted
    op.create_index(op.f('ix_ocr_documents_is_deleted'), 'ocr_documents', ['is_deleted'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_ocr_documents_is_deleted'), table_name='ocr_documents')
    op.drop_column('ocr_documents', 'is_deleted')
