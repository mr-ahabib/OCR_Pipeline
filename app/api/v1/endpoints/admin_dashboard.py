"""Admin Dashboard endpoints — enterprise management and OCR activity views."""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.middleware.auth import require_admin
from app.models.enterprise import Enterprise, EnterprisePaymentStatus
from app.models.ocr_document import OCRDocument
from app.models.user import User, UserRole
from app.schemas.auth_schemas import UserResponse
from app.schemas.dashboard_schemas import AdminDashboardStats
from app.services.enterprise_service import list_enterprises
from app.services.ocr_crud import get_ocr_documents

router = APIRouter()


@router.get(
    "/stats",
    response_model=AdminDashboardStats,
    summary="Admin overview statistics",
)
async def get_admin_dashboard_stats(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    **Role:** ADMIN only. Returns the logged-in admin's enterprise portfolio stats
    and personal OCR activity — scoped to enterprises they created.
    """
    enterprises = (
        db.query(Enterprise)
        .filter(
            Enterprise.created_by == current_user.id,
            Enterprise.is_deleted == False,
        )
        .all()
    )

    total_enterprises = len(enterprises)
    total_pages_allocated = sum(e.total_pages for e in enterprises)
    total_pages_used = sum(e.pages_used for e in enterprises)
    total_pages_remaining = max(0, total_pages_allocated - total_pages_used)
    total_revenue_collected = sum(e.advance_bill or 0.0 for e in enterprises)
    total_due_amount = sum(e.due_amount or 0.0 for e in enterprises)
    paid_count = sum(
        1 for e in enterprises if e.payment_status == EnterprisePaymentStatus.PAID
    )
    partial_paid_count = sum(
        1
        for e in enterprises
        if e.payment_status == EnterprisePaymentStatus.PARTIAL_PAID
    )
    due_count = sum(
        1 for e in enterprises if e.payment_status == EnterprisePaymentStatus.DUE
    )

    total_ocr_documents_processed = (
        db.query(OCRDocument)
        .filter(
            OCRDocument.user_id == current_user.id,
            OCRDocument.is_deleted == False,
        )
        .count()
    )

    return AdminDashboardStats(
        total_enterprises=total_enterprises,
        total_pages_allocated=total_pages_allocated,
        total_pages_used=total_pages_used,
        total_pages_remaining=total_pages_remaining,
        total_revenue_collected=total_revenue_collected,
        total_due_amount=total_due_amount,
        paid_count=paid_count,
        partial_paid_count=partial_paid_count,
        due_count=due_count,
        total_ocr_documents_processed=total_ocr_documents_processed,
    )


@router.get(
    "/enterprises",
    summary="List enterprises created by this admin",
)
async def get_admin_enterprises(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    **Role:** ADMIN only. Returns enterprise contracts created by this admin, paginated.

    | Param | Default | Description |
    |-------|---------|-------------|
    | skip  | 0       | Offset |
    | limit | 50      | Max records |
    """
    total, enterprises = list_enterprises(
        db, created_by=current_user.id, skip=skip, limit=limit
    )
    return {"total": total, "enterprises": enterprises}


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="List regular users (read-only)",
)
async def get_users_list(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    **Role:** ADMIN only. Read-only list of `USER`-role accounts, paginated.

    | Param | Default | Description |
    |-------|---------|-------------|
    | skip  | 0       | Offset |
    | limit | 50      | Max records |
    """
    users = (
        db.query(User)
        .filter(User.role == UserRole.USER)
        .order_by(User.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return users


@router.get(
    "/ocr-documents",
    summary="Admin's own OCR document history",
)
async def get_admin_ocr_documents(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    **Role:** ADMIN only. Returns OCR documents processed by this admin account, paginated.

    | Param | Default | Description |
    |-------|---------|-------------|
    | skip  | 0       | Offset |
    | limit | 50      | Max records |
    """
    total = (
        db.query(OCRDocument)
        .filter(
            OCRDocument.user_id == current_user.id,
            OCRDocument.is_deleted == False,
        )
        .count()
    )
    docs = get_ocr_documents(db, user_id=current_user.id, skip=skip, limit=limit)
    return {"total": total, "documents": docs}
