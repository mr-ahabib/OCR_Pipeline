"""add payment_history table

Revision ID: 7f2b3c4d5e6a
Revises: 6e1a2b3c4d5f
Create Date: 2026-02-22 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f2b3c4d5e6a'
down_revision: Union[str, Sequence[str], None] = '6e1a2b3c4d5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the payment_history table."""
    op.create_table(
        'payment_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('invoice_number', sa.String(length=100), nullable=False),
        sa.Column('pages_purchased', sa.Integer(), nullable=False),
        sa.Column('payment_amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default='BDT'),
        sa.Column(
            'status',
            sa.Enum('pending', 'success', 'failed', 'cancelled', name='paymentstatus'),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('initiation_response', sa.JSON(), nullable=True),
        sa.Column('callback_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_payment_history_id'), 'payment_history', ['id'], unique=False)
    op.create_index(op.f('ix_payment_history_invoice_number'), 'payment_history', ['invoice_number'], unique=True)
    op.create_index(op.f('ix_payment_history_user_id'), 'payment_history', ['user_id'], unique=False)
    op.create_index(op.f('ix_payment_history_status'), 'payment_history', ['status'], unique=False)


def downgrade() -> None:
    """Drop the payment_history table."""
    op.drop_index(op.f('ix_payment_history_status'), table_name='payment_history')
    op.drop_index(op.f('ix_payment_history_user_id'), table_name='payment_history')
    op.drop_index(op.f('ix_payment_history_invoice_number'), table_name='payment_history')
    op.drop_index(op.f('ix_payment_history_id'), table_name='payment_history')
    op.drop_table('payment_history')
    op.execute("DROP TYPE IF EXISTS paymentstatus")
