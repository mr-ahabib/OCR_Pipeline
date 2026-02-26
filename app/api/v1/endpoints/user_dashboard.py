"""User Dashboard endpoints — personal quota, documents, and payment history."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.middleware.auth import require_user
from app.models.ocr_document import OCRDocument
from app.models.user import User
from app.schemas.dashboard_schemas import UserDashboardStats
from app.schemas.payment_schemas import PaymentHistoryResponse
from app.schemas.subscription_schemas import SubscriptionStatus
from app.services.ocr_crud import get_ocr_documents
from app.services.payment_service import get_user_payment_history
from app.services.subscription_service import get_subscription_status

router = APIRouter()


@router.get(
    "/stats",
    response_model=UserDashboardStats,
    summary="Personal dashboard statistics",
)
async def get_user_dashboard_stats(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** USER only. Returns the logged-in user's quota and document activity snapshot.

    Includes free OCR quota, paid subscription quota, total documents, total pages
    processed, and the most recent document filename.
    """
    total_documents = (
        db.query(OCRDocument)
        .filter(
            OCRDocument.user_id == current_user.id,
            OCRDocument.is_deleted == False,
        )
        .count()
    )

    total_pages_result = (
        db.query(func.sum(OCRDocument.total_pages))
        .filter(
            OCRDocument.user_id == current_user.id,
            OCRDocument.is_deleted == False,
        )
        .scalar()
    )
    total_pages_processed = int(total_pages_result or 0)

    last_doc = (
        db.query(OCRDocument)
        .filter(
            OCRDocument.user_id == current_user.id,
            OCRDocument.is_deleted == False,
        )
        .order_by(OCRDocument.created_at.desc())
        .first()
    )

    return UserDashboardStats(
        free_ocr_limit=current_user.FREE_OCR_LIMIT,
        free_ocr_used=current_user.free_ocr_used or 0,
        free_ocr_remaining=current_user.free_ocr_remaining,
        subscription_pages_total=current_user.subscription_pages_total or 0,
        subscription_pages_used=current_user.subscription_pages_used or 0,
        subscription_pages_remaining=current_user.subscription_pages_remaining,
        has_active_subscription=current_user.has_active_subscription,
        total_documents=total_documents,
        total_pages_processed=total_pages_processed,
        last_document_filename=last_doc.filename if last_doc else None,
        last_document_created_at=str(last_doc.created_at) if last_doc else None,
    )


@router.get(
    "/subscription",
    response_model=SubscriptionStatus,
    summary="Current subscription / quota status",
)
async def get_user_subscription(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** USER only. Returns full quota status including `can_do_ocr` flag
    and a human-readable `message`. Use to decide whether to show the Buy Pages prompt.
    """
    return get_subscription_status(current_user)


@router.get(
    "/payments",
    response_model=PaymentHistoryResponse,
    summary="Personal payment history",
)
async def get_user_payments(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** USER only. Returns this user's subscription payment history, paginated.

    | Param | Default | Description |
    |-------|---------|-------------|
    | skip  | 0       | Offset |
    | limit | 20      | Max records |
    """
    return get_user_payment_history(db, user_id=current_user.id, skip=skip, limit=limit)


@router.get(
    "/ocr-documents",
    summary="Personal OCR document history",
)
async def get_user_ocr_documents(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** USER only. Returns this user's OCR document history, paginated.
    Soft-deleted records are excluded.

    | Param | Default | Description |
    |-------|---------|-------------|
    | skip  | 0       | Offset |
    | limit | 20      | Max records |
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
