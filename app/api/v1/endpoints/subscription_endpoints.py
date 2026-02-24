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
    """
    ## Get current subscription status

    **Role:** Regular users (USER) only.

    **Auth:** `Authorization: Bearer <token>` header required.

    Returns the caller's current quota balance and subscription tier.
    ADMIN and SUPER_USER calls are rejected with HTTP 403 (they have
    unlimited access and do not subscribe).

    ### Response — SubscriptionStatus
    | Field                  | Description                                      |
    |------------------------|--------------------------------------------------|
    | plan                   | `free` or `paid`                                 |
    | ocr_quota_remaining    | Pages remaining in current subscription          |
    | free_ocr_remaining     | One-time free pages still available              |
    | subscription_expires_at| ISO timestamp when the paid plan expires (or null)|
    | is_active              | Whether the subscription is currently active     |

    ### Frontend integration
    - Poll or call after every OCR request to refresh the quota display.
    - Show a "Buy More Pages" CTA when `ocr_quota_remaining` reaches 0.
    - Example: `GET /subscription/status`
    """
    _assert_regular_user(current_user)
    return get_subscription_status(current_user)


@router.post("/calculate-cost", response_model=SubscriptionCostResponse)
async def calculate_cost(
    body: SubscriptionCostRequest,
    current_user: User = Depends(require_user),
):
    """
    ## Calculate subscription cost before purchasing

    **Role:** Regular users (USER) only.

    **Auth:** `Authorization: Bearer <token>` header required.

    Returns the total price in BDT for a given number of pages without
    initiating a payment. Use this to show a live price preview on the
    checkout/top-up screen.

    Pricing formula: **pages × 10 BDT**.

    ### Required fields (JSON body)
    | Field | Type | Description                    |
    |-------|------|--------------------------------|
    | pages | int  | Number of OCR pages to price   |

    ### Response — SubscriptionCostResponse
    | Field       | Description                        |
    |-------------|------------------------------------|
    | pages       | Pages submitted in the request     |
    | cost_bdt    | Total cost in BDT                  |
    | price_per_page | Unit price (10 BDT)             |

    ### Frontend integration
    - Call on every keystroke / change in the "number of pages" input field
      to show a real-time cost preview.
    - Pass the same `pages` value to **POST /payment/initiate** to start the
      actual payment.
    """
    _assert_regular_user(current_user)
    return calculate_subscription_cost(body.pages)
