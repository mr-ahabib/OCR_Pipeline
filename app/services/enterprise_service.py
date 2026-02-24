"""Enterprise OCR service — CRUD, quota management, and billing helpers."""
from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.enterprise import Enterprise, EnterpriseOCRDocument, EnterprisePaymentStatus
from app.models.user import User
from app.schemas.enterprise_schemas import (
    EnterpriseCreate,
    EnterpriseOCRDocumentCreate,
    EnterprisePaymentStatusUpdate,
    EnterpriseResponse,
    EnterpriseOCRDocumentResponse,
    EnterpriseUpdate,
    EnterpriseBillingSummary,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _calc_duration(start: Optional[date], end: Optional[date]) -> Optional[int]:
    if start and end and end >= start:
        return (end - start).days
    return None


def _enrich_enterprise(db: Session, ent: Enterprise) -> EnterpriseResponse:
    """Build an EnterpriseResponse with computed/joined fields."""
    creator = db.query(User).filter(User.id == ent.created_by).first()
    data = {c.name: getattr(ent, c.name) for c in ent.__table__.columns}
    data["pages_remaining"] = max(0, ent.total_pages - ent.pages_used)
    data["created_by_name"] = creator.full_name or creator.username if creator else None
    return EnterpriseResponse(**data)


def _enrich_ocr_doc(db: Session, doc: EnterpriseOCRDocument) -> EnterpriseOCRDocumentResponse:
    processor = db.query(User).filter(User.id == doc.processed_by).first()
    data = {c.name: getattr(doc, c.name) for c in doc.__table__.columns}
    data["processor_name"] = processor.full_name or processor.username if processor else None
    return EnterpriseOCRDocumentResponse(**data)


# ─────────────────────────────────────────────────────────────────────────────
# Enterprise CRUD
# ─────────────────────────────────────────────────────────────────────────────

def create_enterprise(db: Session, payload: EnterpriseCreate, created_by: int) -> EnterpriseResponse:
    total_cost  = payload.total_pages * payload.unit_price
    due_amount  = total_cost - payload.advance_bill
    duration    = _calc_duration(payload.start_date, payload.end_date)

    ent = Enterprise(
        name            = payload.name,
        phone           = payload.phone,
        email           = payload.email,
        description     = payload.description,
        total_pages     = payload.total_pages,
        unit_price      = payload.unit_price,
        total_cost      = total_cost,
        start_date      = payload.start_date,
        end_date        = payload.end_date,
        duration_days   = duration,
        advance_bill    = payload.advance_bill,
        due_amount      = due_amount,
        payment_status  = EnterprisePaymentStatus(payload.payment_status.value),
        no_of_documents = payload.no_of_documents,
        pages_used      = 0,
        created_by      = created_by,
        is_deleted      = False,
    )
    db.add(ent)
    db.commit()
    db.refresh(ent)
    logger.info(f"[Enterprise] Created id={ent.id} name='{ent.name}' by user_id={created_by}")
    return _enrich_enterprise(db, ent)


def get_enterprise(
    db: Session,
    enterprise_id: int,
    created_by: Optional[int] = None,   # None → any (super_user)
    include_deleted: bool = False,
) -> Optional[EnterpriseResponse]:
    q = db.query(Enterprise).filter(Enterprise.id == enterprise_id)
    if not include_deleted:
        q = q.filter(Enterprise.is_deleted == False)
    if created_by is not None:
        q = q.filter(Enterprise.created_by == created_by)
    ent = q.first()
    return _enrich_enterprise(db, ent) if ent else None


def _get_enterprise_orm(
    db: Session,
    enterprise_id: int,
    created_by: Optional[int] = None,
    include_deleted: bool = False,
) -> Optional[Enterprise]:
    q = db.query(Enterprise).filter(Enterprise.id == enterprise_id)
    if not include_deleted:
        q = q.filter(Enterprise.is_deleted == False)
    if created_by is not None:
        q = q.filter(Enterprise.created_by == created_by)
    return q.first()


def list_enterprises(
    db: Session,
    created_by: Optional[int] = None,   # None → all (super_user)
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
) -> tuple[int, List[EnterpriseResponse]]:
    q = db.query(Enterprise)
    if not include_deleted:
        q = q.filter(Enterprise.is_deleted == False)
    if created_by is not None:
        q = q.filter(Enterprise.created_by == created_by)
    total = q.count()
    enterprises = q.order_by(Enterprise.created_at.desc()).offset(skip).limit(limit).all()
    return total, [_enrich_enterprise(db, e) for e in enterprises]


def update_enterprise(
    db: Session,
    enterprise_id: int,
    payload: EnterpriseUpdate,
    created_by: Optional[int] = None,  # None → any (super_user)
) -> Optional[EnterpriseResponse]:
    ent = _get_enterprise_orm(db, enterprise_id, created_by=created_by)
    if not ent:
        return None

    updated_fields = payload.model_dump(exclude_unset=True)
    for field, value in updated_fields.items():
        if field == "payment_status" and value is not None:
            value = EnterprisePaymentStatus(value)
        setattr(ent, field, value)

    # Recompute derived fields if billing inputs changed
    ent.total_cost   = ent.total_pages * ent.unit_price
    ent.duration_days = _calc_duration(ent.start_date, ent.end_date)
    ent.due_amount   = max(0.0, ent.total_cost - ent.advance_bill)

    db.commit()
    db.refresh(ent)
    return _enrich_enterprise(db, ent)


def update_payment_status(
    db: Session,
    enterprise_id: int,
    payload: EnterprisePaymentStatusUpdate,
    created_by: Optional[int] = None,
) -> Optional[EnterpriseResponse]:
    ent = _get_enterprise_orm(db, enterprise_id, created_by=created_by)
    if not ent:
        return None

    # ── accumulate advance payment (additive, not a replace) ──────────────────
    if payload.advance_bill is not None:
        ent.advance_bill = round((ent.advance_bill or 0.0) + payload.advance_bill, 2)
        ent.due_amount   = round(max(0.0, (ent.total_cost or 0.0) - ent.advance_bill), 2)

    # ── auto-derive payment_status from the resulting amounts ─────────────────
    if ent.due_amount <= 0:
        ent.payment_status = EnterprisePaymentStatus.PAID
    elif (ent.advance_bill or 0.0) > 0:
        ent.payment_status = EnterprisePaymentStatus.PARTIAL_PAID
    else:
        ent.payment_status = EnterprisePaymentStatus.DUE

    db.commit()
    db.refresh(ent)
    return _enrich_enterprise(db, ent)


def soft_delete_enterprise(
    db: Session,
    enterprise_id: int,
    created_by: Optional[int] = None,
) -> bool:
    ent = _get_enterprise_orm(db, enterprise_id, created_by=created_by)
    if not ent:
        return False
    ent.is_deleted = True
    db.commit()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Enterprise OCR Documents
# ─────────────────────────────────────────────────────────────────────────────

def save_enterprise_ocr_document(
    db: Session,
    payload: EnterpriseOCRDocumentCreate,
) -> EnterpriseOCRDocument:
    doc = EnterpriseOCRDocument(**payload.model_dump())
    db.add(doc)

    # Increment enterprise pages_used counter
    ent = db.query(Enterprise).filter(Enterprise.id == payload.enterprise_id).first()
    if ent:
        ent.pages_used = (ent.pages_used or 0) + payload.total_pages

    db.commit()
    db.refresh(doc)
    logger.info(
        f"[EnterpriseOCR] Saved doc id={doc.id} enterprise_id={doc.enterprise_id} "
        f"pages={doc.total_pages} processed_by={doc.processed_by}"
    )
    return doc


def get_enterprise_ocr_history(
    db: Session,
    enterprise_id: int,
    skip: int = 0,
    limit: int = 100,
    created_by: Optional[int] = None,   # verify enterprise ownership
) -> tuple[int, List[EnterpriseOCRDocumentResponse]]:
    # Ownership check: confirm enterprise belongs to caller (unless super_user)
    if created_by is not None:
        ent = _get_enterprise_orm(db, enterprise_id, created_by=created_by)
        if not ent:
            return 0, []

    q = db.query(EnterpriseOCRDocument).filter(
        EnterpriseOCRDocument.enterprise_id == enterprise_id
    )
    total = q.count()
    docs = q.order_by(EnterpriseOCRDocument.created_at.desc()).offset(skip).limit(limit).all()
    return total, [_enrich_ocr_doc(db, d) for d in docs]


# ─────────────────────────────────────────────────────────────────────────────
# Super-user billing summary
# ─────────────────────────────────────────────────────────────────────────────

def get_billing_summary(db: Session) -> EnterpriseBillingSummary:
    enterprises = db.query(Enterprise).filter(Enterprise.is_deleted == False).all()
    return EnterpriseBillingSummary(
        total_enterprises     = len(enterprises),
        total_pages_allocated = sum(e.total_pages   for e in enterprises),
        total_cost            = sum(e.total_cost     for e in enterprises),
        total_advance_billed  = sum(e.advance_bill   for e in enterprises),
        total_due_amount      = sum(e.due_amount     for e in enterprises),
        paid_count            = sum(1 for e in enterprises if e.payment_status == EnterprisePaymentStatus.PAID),
        partial_paid_count    = sum(1 for e in enterprises if e.payment_status == EnterprisePaymentStatus.PARTIAL_PAID),
        due_count             = sum(1 for e in enterprises if e.payment_status == EnterprisePaymentStatus.DUE),
    )
