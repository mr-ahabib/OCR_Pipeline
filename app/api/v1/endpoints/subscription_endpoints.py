"""Subscription API endpoints — for regular users (UserRole.USER) only."""
from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import require_user
from app.models.user import User, UserRole
from app.schemas.subscription_schemas import (
    SubscriptionCostRequest,
    SubscriptionCostResponse,
    SubscriptionStatus,
)
from app.services.subscription_service import (
    get_subscription_status,
    calculate_subscription_cost,
)

router = APIRouter()


def _assert_regular_user(user: User) -> None:
    """Raise 403 if the caller is an admin or super_user."""
    if user.role != UserRole.USER:
        raise HTTPException(
            status_code=403,
            detail="Subscription management is only available for regular users. "
                   "Admins and super-users have unlimited OCR access.",
        )


@router.get("/status", response_model=SubscriptionStatus)
async def subscription_status(
    current_user: User = Depends(require_user),
):
    _assert_regular_user(current_user)
    return get_subscription_status(current_user)


@router.post("/calculate-cost", response_model=SubscriptionCostResponse)
async def calculate_cost(
    body: SubscriptionCostRequest,
    current_user: User = Depends(require_user),
):
    _assert_regular_user(current_user)
    return calculate_subscription_cost(body.pages)
