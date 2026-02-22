"""PaymentHistory database model."""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.sql import func
from enum import Enum
from app.db.base import Base


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentHistory(Base):
    """Tracks every payment attempt made by users for subscription pages."""
    __tablename__ = "payment_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Transaction identifiers
    invoice_number = Column(String(100), unique=True, nullable=False, index=True)

    # What was purchased
    pages_purchased = Column(Integer, nullable=False)
    payment_amount = Column(Float, nullable=False)   # in BDT
    currency = Column(String(10), nullable=False, default="BDT")

    status = Column(
        SQLEnum(
            PaymentStatus,
            name="paymentstatus",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )

    initiation_response = Column(JSON, nullable=True)
    callback_payload = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return (
            f"<PaymentHistory(id={self.id}, user_id={self.user_id}, "
            f"invoice={self.invoice_number}, status={self.status})>"
        )
