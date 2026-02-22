"""Subscription service — free-trial & paid-page quota management for regular users."""
import logging
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.schemas.subscription_schemas import (
    SubscriptionStatus,
    SubscriptionCostResponse,
    PAGE_COST,
    FREE_OCR_LIMIT,
)

logger = logging.getLogger(__name__)


def get_subscription_status(user: User) -> SubscriptionStatus:
    """Return a full quota snapshot for *user*.

    Admin and super-user roles have unlimited access — the snapshot reflects
    that with ``can_do_ocr=True`` and a descriptive message.
    """
    if user.role in (UserRole.ADMIN, UserRole.SUPER_USER):
        return SubscriptionStatus(
            free_ocr_limit=FREE_OCR_LIMIT,
            free_ocr_used=0,
            free_ocr_remaining=FREE_OCR_LIMIT,
            subscription_pages_total=0,
            subscription_pages_used=0,
            subscription_pages_remaining=0,
            has_active_subscription=False,
            can_do_ocr=True,
            message="Unlimited OCR access (admin / super-user).",
        )
    free_remaining = user.free_ocr_remaining
    sub_remaining = user.subscription_pages_remaining
    can_do = free_remaining > 0 or sub_remaining > 0

    if free_remaining > 0:
        msg = f"You have {free_remaining} free OCR request(s) remaining."
    elif sub_remaining > 0:
        msg = f"You have {sub_remaining} subscription page(s) remaining."
    else:
        msg = (
            "You have used all your free OCR requests and your subscription pages are exhausted. "
            "Please subscribe to continue."
        )

    return SubscriptionStatus(
        free_ocr_limit=FREE_OCR_LIMIT,
        free_ocr_used=user.free_ocr_used or 0,
        free_ocr_remaining=free_remaining,
        subscription_pages_total=user.subscription_pages_total or 0,
        subscription_pages_used=user.subscription_pages_used or 0,
        subscription_pages_remaining=sub_remaining,
        has_active_subscription=user.has_active_subscription,
        can_do_ocr=can_do,
        message=msg,
    )


def calculate_subscription_cost(pages: int) -> SubscriptionCostResponse:
    """Return cost breakdown for *pages* pages."""
    return SubscriptionCostResponse(
        pages=pages,
        cost_per_page=PAGE_COST,
        total_cost=pages * PAGE_COST,
    )


def add_subscription_pages(db: Session, user: User, pages: int) -> SubscriptionStatus:
    """
    Top-up (or create) a subscription for *user* by adding *pages* pages.
    Returns the updated SubscriptionStatus.
    """
    user.subscription_pages_total = (user.subscription_pages_total or 0) + pages
    db.commit()
    db.refresh(user)
    logger.info(
        f"Subscription top-up: user_id={user.id}, added={pages} pages, "
        f"total={user.subscription_pages_total}, used={user.subscription_pages_used}"
    )
    return get_subscription_status(user)


def check_and_consume_quota(db: Session, user: User, pages_needed: int) -> None:
    """
    Verify the user has enough quota for *pages_needed* pages and atomically
    consume it.  Raises ``ValueError`` with a descriptive message on failure.

    Admin and super-user roles bypass all quota checks (unlimited access).

    Priority for regular users:
      1. If free OCR requests remain (free_ocr_used < 3) → use one free slot.
      2. Else consume *pages_needed* from subscription.

    NOTE: A single free OCR request covers the entire uploaded file regardless
    of page count.  Subscription pages are deducted page-by-page.
    """
    if user.role in (UserRole.ADMIN, UserRole.SUPER_USER):
        logger.info(f"Quota bypass for {user.role.value}: user_id={user.id}")
        return

    if user.free_ocr_remaining > 0:
        user.free_ocr_used = (user.free_ocr_used or 0) + 1
        db.commit()
        logger.info(
            f"Free OCR used: user_id={user.id}, "
            f"free_used={user.free_ocr_used}/{FREE_OCR_LIMIT}"
        )
        return

    sub_remaining = user.subscription_pages_remaining
    if sub_remaining < pages_needed:
        raise ValueError(
            f"Insufficient subscription pages. "
            f"You need {pages_needed} page(s) but only have {sub_remaining} remaining. "
            f"Please subscribe to get more pages."
        )

    user.subscription_pages_used = (user.subscription_pages_used or 0) + pages_needed
    db.commit()
    logger.info(
        f"Subscription pages consumed: user_id={user.id}, "
        f"consumed={pages_needed}, "
        f"remaining={user.subscription_pages_remaining}"
    )
