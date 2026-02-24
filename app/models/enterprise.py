"""Enterprise OCR models — enterprise contracts, OCR documents, and billing."""
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Date,
    JSON, ForeignKey, Boolean, Enum as SQLEnum
)
from sqlalchemy.sql import func
from enum import Enum

from app.db.base import Base


class EnterprisePaymentStatus(str, Enum):
    PAID         = "paid"
    PARTIAL_PAID = "partial_paid"
    DUE          = "due"


class Enterprise(Base):
    """
    An enterprise contract created by an ADMIN (or SUPER_USER).
    Holds all billing, quota, and contact information for the client.
    """
    __tablename__ = "enterprises"

    id              = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # ── Contact & description ──────────────────────────────────────────────────
    name            = Column(String(255), nullable=False, index=True)
    phone           = Column(String(50),  nullable=True)
    email           = Column(String(255), nullable=True, index=True)
    description     = Column(Text,        nullable=True)

    # ── Contract / quota ──────────────────────────────────────────────────────
    total_pages     = Column(Integer, nullable=False, default=0)        # pages allocated
    unit_price      = Column(Float,   nullable=False, default=10.0)     # BDT per page
    total_cost      = Column(Float,   nullable=False, default=0.0)      # total_pages × unit_price

    start_date      = Column(Date, nullable=True)
    end_date        = Column(Date, nullable=True)
    duration_days   = Column(Integer, nullable=True)                    # auto from dates

    # ── Billing ───────────────────────────────────────────────────────────────
    advance_bill    = Column(Float,   nullable=False, default=0.0)
    due_amount      = Column(Float,   nullable=False, default=0.0)      # total_cost - advance_bill

    payment_status  = Column(
        SQLEnum(
            EnterprisePaymentStatus,
            name="enterprisepaymentstatus",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=EnterprisePaymentStatus.DUE,
        index=True,
    )

    # ── Operational ───────────────────────────────────────────────────────────
    no_of_documents = Column(Integer, nullable=False, default=0)        # expected docs
    pages_used      = Column(Integer, nullable=False, default=0)        # actual pages consumed

    # ── Ownership ─────────────────────────────────────────────────────────────
    created_by      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    is_deleted      = Column(Boolean, default=False, nullable=False, index=True)

    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    def __repr__(self):
        return (
            f"<Enterprise(id={self.id}, name='{self.name}', "
            f"pages={self.total_pages}, status={self.payment_status})>"
        )


class EnterpriseOCRDocument(Base):
    """
    Stores every OCR processing event executed under an enterprise contract.
    Mirrors OCRDocument but scoped to an enterprise instead of a regular user.
    """
    __tablename__ = "enterprise_ocr_documents"

    id             = Column(Integer, primary_key=True, index=True, autoincrement=True)
    enterprise_id  = Column(Integer, ForeignKey("enterprises.id"), nullable=False, index=True)
    processed_by   = Column(Integer, ForeignKey("users.id"),        nullable=False, index=True)

    filename       = Column(String(255), nullable=False, index=True)
    file_path      = Column(String(512), nullable=True)
    file_type      = Column(String(50),  nullable=False)
    file_size      = Column(Integer,     nullable=False)

    ocr_mode       = Column(String(50),  nullable=False)
    ocr_engine     = Column(String(255), nullable=False)
    languages      = Column(JSON,        nullable=False)

    extracted_text  = Column(Text,    nullable=False)
    confidence      = Column(Float,   nullable=False)
    total_pages     = Column(Integer, nullable=False, default=1)
    pages_data      = Column(JSON,    nullable=True)

    processing_time = Column(Float,   nullable=True)
    character_count = Column(Integer, nullable=True)

    created_at     = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return (
            f"<EnterpriseOCRDocument(id={self.id}, enterprise_id={self.enterprise_id}, "
            f"file='{self.filename}', pages={self.total_pages})>"
        )
