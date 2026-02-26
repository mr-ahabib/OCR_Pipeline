"""Super User Dashboard endpoints — platform-wide statistics and management views."""
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.errors.exceptions import NotFoundException
from app.middleware.auth import require_super_user
from app.models.enterprise import Enterprise, EnterprisePaymentStatus
from app.models.free_trial_user import FreeTrialUser
from app.models.ocr_document import OCRDocument
from app.models.payment import PaymentHistory, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.auth_schemas import UserResponse
from app.schemas.dashboard_schemas import SuperUserDashboardStats
from app.schemas.payment_schemas import PaymentHistoryResponse
from app.services.enterprise_service import get_billing_summary, list_enterprises
from app.services.ocr_crud import get_ocr_documents
from app.services.payment_service import get_all_payment_history

router = APIRouter()


@router.get(
    "/stats",
    response_model=SuperUserDashboardStats,
    summary="Platform-wide statistics",
)
async def get_superuser_dashboard_stats(
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** SUPER_USER only. Returns platform-wide stats for dashboard overview cards.

    Includes user counts, OCR document totals, subscription revenue, free-trial count,
    and enterprise billing summary.
    """
    total_users = db.query(User).count()
    total_admins = db.query(User).filter(User.role == UserRole.ADMIN).count()
    total_regular_users = db.query(User).filter(User.role == UserRole.USER).count()

    total_ocr_documents = (
        db.query(OCRDocument).filter(OCRDocument.is_deleted == False).count()
    )

    # Sum of successful individual payments
    revenue_result = (
        db.query(func.sum(PaymentHistory.payment_amount))
        .filter(PaymentHistory.status == PaymentStatus.SUCCESS)
        .scalar()
    )
    total_revenue = float(revenue_result or 0.0)

    # Users with at least one subscription page remaining
    active_subscriptions = (
        db.query(User)
        .filter(User.subscription_pages_total > User.subscription_pages_used)
        .count()
    )

    try:
        free_trial_users = db.query(FreeTrialUser).count()
    except Exception:
        free_trial_users = 0

    enterprises = (
        db.query(Enterprise).filter(Enterprise.is_deleted == False).all()
    )
    total_enterprises = len(enterprises)
    total_enterprise_revenue = sum(e.advance_bill or 0.0 for e in enterprises)
    total_enterprise_due = sum(e.due_amount or 0.0 for e in enterprises)

    return SuperUserDashboardStats(
        total_users=total_users,
        total_admins=total_admins,
        total_regular_users=total_regular_users,
        total_ocr_documents=total_ocr_documents,
        total_revenue_bdt=total_revenue,
        active_subscriptions=active_subscriptions,
        free_trial_users=free_trial_users,
        total_enterprises=total_enterprises,
        total_enterprise_revenue_collected=total_enterprise_revenue,
        total_enterprise_due=total_enterprise_due,
    )


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="List all users (paginated, filterable by role)",
)
async def list_all_users(
    skip: int = 0,
    limit: int = 50,
    role: Optional[str] = None,
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** SUPER_USER only. Returns all users, paginated.

    | Param | Default | Description |
    |-------|---------|-------------|
    | skip  | 0       | Offset |
    | limit | 50      | Max records |
    | role  | —       | Filter: `super_user`, `admin`, `user` |
    """
    query = db.query(User)
    if role:
        try:
            query = query.filter(User.role == UserRole(role))
        except ValueError:
            pass  # Ignore unknown role values — return unfiltered

    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    return users


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Get a specific user's profile",
)
async def get_user_detail(
    user_id: int,
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** SUPER_USER only. Returns full profile of any user by ID.

    - HTTP 404 → user not found
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundException(detail="User not found")
    return user


@router.get(
    "/users/{user_id}/ocr-documents",
    summary="Get all OCR documents for a specific user",
)
async def get_user_ocr_documents(
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** SUPER_USER only. Returns paginated OCR documents for any user.

    - HTTP 404 → user not found
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundException(detail="User not found")

    total = (
        db.query(OCRDocument)
        .filter(OCRDocument.user_id == user_id, OCRDocument.is_deleted == False)
        .count()
    )
    docs = get_ocr_documents(db, user_id=user_id, skip=skip, limit=limit)
    return {"total": total, "documents": docs}


@router.get(
    "/payments",
    response_model=PaymentHistoryResponse,
    summary="All payment history (platform-wide)",
)
async def get_all_payments(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** SUPER_USER only. Returns platform-wide payment history, paginated.

    | Param  | Default | Description |
    |--------|---------|-------------|
    | skip   | 0       | Offset |
    | limit  | 50      | Max records |
    | status | —       | Filter: `pending`, `success`, `failed`, `cancelled` |
    """
    return get_all_payment_history(db, skip=skip, limit=limit, status_filter=status)


@router.get(
    "/enterprises",
    summary="All enterprise contracts with billing summary",
)
async def get_all_enterprises(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db),
):
    """
    **Role:** SUPER_USER only. Returns all enterprise contracts (from every admin)
    plus a platform-level billing summary (`total_cost`, `total_due_amount`, etc.).
    """
    total, enterprises = list_enterprises(
        db, created_by=None, skip=skip, limit=limit
    )
    billing = get_billing_summary(db)
    return {
        "total": total,
        "billing_summary": billing,
        "enterprises": enterprises,
    }
