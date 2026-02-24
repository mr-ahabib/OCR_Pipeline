"""Payment API endpoints — PayStation integration."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.middleware.auth import require_user, require_super_user
from app.models.user import User, UserRole
from app.schemas.payment_schemas import (
    PaymentCallbackPayload,
    PaymentCallbackResponse,
    PaymentHistoryResponse,
    PaymentInitiateRequest,
    PaymentInitiateResponse,
)
from app.services.payment_service import (
    get_all_payment_history,
    get_user_payment_history,
    initiate_payment,
    process_payment_callback,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _assert_regular_user(user: User) -> None:
    """Raise 403 for admin / super-user — they have unlimited access and don't subscribe."""
    if user.role != UserRole.USER:
        raise HTTPException(
            status_code=403,
            detail="Payment and subscriptions are only for regular users. "
                   "Admins and super-users have unlimited OCR access.",
        )


@router.post("/initiate", response_model=PaymentInitiateResponse, status_code=201)
async def initiate_subscription_payment(
    body: PaymentInitiateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    ## Initiate a subscription payment via PayStation

    **Role:** Regular users (USER) only.

    **Auth:** `Authorization: Bearer <token>` header required.

    Creates a pending payment record and returns a `payment_url` that the
    frontend must redirect (or pop-up) the user to in order to complete the
    transaction. Pricing: **pages × 10 BDT**.

    After the user completes or cancels payment, PayStation posts back to
    **GET /payment/callback** automatically — no frontend action needed for
    the confirmation step.

    ### Required fields (JSON body)
    | Field        | Type   | Required | Description                          |
    |--------------|--------|----------|--------------------------------------|
    | pages        | int    | ✔        | Number of OCR pages to purchase      |
    | cust_name    | string | ✔        | Customer's full name                 |
    | cust_phone   | string | ✔        | Customer's phone number              |
    | cust_address | string |          | Customer's address (optional)        |

    ### Response — PaymentInitiateResponse
    | Field       | Description                                          |
    |-------------|------------------------------------------------------|
    | payment_url | URL to redirect the user to for payment completion   |
    | invoice_number | Unique invoice ID to track this transaction       |
    | amount      | Total amount in BDT                                  |

    ### Frontend integration
    ```js
    const { data } = await axios.post('/api/v1/payment/initiate',
      { pages: 100, cust_name: 'John', cust_phone: '017...' },
      { headers: { Authorization: `Bearer ${token}` } }
    );
    // Redirect to PayStation:
    window.location.href = data.payment_url;
    // OR open in a popup/iframe
    ```
    - HTTP 403 → admin / super-user — they cannot subscribe.
    - HTTP 502 → PayStation service unavailable.
    """
    _assert_regular_user(current_user)

    try:
        response = await initiate_payment(
            db=db,
            user=current_user,
            pages=body.pages,
            cust_name=body.cust_name,
            cust_phone=body.cust_phone,
            cust_address=body.cust_address,
        )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.error(f"[/payment/initiate] Unexpected error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Payment initiation failed. Please try again.")


@router.get("/callback", response_model=PaymentCallbackResponse)
async def payment_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    ## PayStation payment callback (internal — not called by frontend)

    **Role:** Public — called automatically by PayStation, not by end-users.

    PayStation redirects here via GET after every payment attempt, with query
    parameters: `?status=Successful&invoice_number=<inv>&trx_id=<id>`.

    The endpoint updates the payment record and, on success, credits the
    user's OCR quota. Always returns HTTP 200 so PayStation does not retry.

    ### Query parameters (set by PayStation)
    | Param          | Description                              |
    |----------------|------------------------------------------|
    | status         | `Successful`, `Failed`, or `Canceled`    |
    | invoice_number | The invoice ID from `/payment/initiate`  |
    | trx_id         | PayStation transaction reference         |

    ### Frontend integration
    - **Do not call this endpoint from the frontend.**
    - After redirecting the user to `payment_url`, listen for the user
      returning to your site (via PayStation's success/failure redirect URL).
    - On return, call **GET /subscription/status** to check the updated quota.
    """
    raw = dict(request.query_params)
    logger.info(f"[Callback] Received params: {raw}")

    payload = PaymentCallbackPayload(**raw)

    if not payload.invoice_number:
        logger.warning("[Callback] Received callback without invoice_number")
        return PaymentCallbackResponse(success=False, message="Missing invoice_number")

    # PayStation status values: Successful / Failed / Canceled
    result = process_payment_callback(
        db=db,
        invoice_number=payload.invoice_number,
        reported_status=payload.status or "",
        reported_amount=None,  # not provided in query params
        raw_payload=raw,
    )
    return PaymentCallbackResponse(**result)


@router.get("/history", response_model=PaymentHistoryResponse)
async def my_payment_history(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    ## My payment history

    **Role:** Any authenticated user (USER / ADMIN / SUPER_USER).

    **Auth:** `Authorization: Bearer <token>` header required.

    Returns the authenticated user's own payment records, newest first.

    ### Query parameters
    | Param | Type | Default | Description                   |
    |-------|------|---------|-------------------------------|
    | skip  | int  | 0       | Pagination offset             |
    | limit | int  | 50      | Max records to return (max 200)|

    ### Response — PaymentHistoryResponse
    Contains a `payments` list with `invoice_number`, `amount`, `status`,
    `pages_purchased`, `created_at`, and `transaction_id` for each record.

    ### Frontend integration
    - Render in a "Billing History" or "Payment Records" section in settings.
    - Use `skip` + `limit` for pagination.
    - Example: `GET /payment/history?skip=0&limit=20`
    """
    return get_user_payment_history(db, user_id=current_user.id, skip=skip, limit=limit)


@router.get("/admin/all", response_model=PaymentHistoryResponse)
async def all_payment_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending | success | failed | cancelled",
    ),
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db),
):
    """
    ## All users' payment history (admin view)

    **Role:** SUPER_USER only.

    **Auth:** `Authorization: Bearer <token>` header required.

    Returns payment records for *all* users across the platform,
    newest first. Available only to super-users for admin / auditing purposes.

    ### Query parameters
    | Param  | Type   | Default | Description                                      |
    |--------|--------|---------|--------------------------------------------------|
    | skip   | int    | 0       | Pagination offset                                |
    | limit  | int    | 100     | Max records to return (max 500)                  |
    | status | string | null    | Filter: `pending`, `success`, `failed`, `cancelled` |

    ### Frontend integration
    - Use in an admin dashboard payments table.
    - Example: `GET /payment/admin/all?status=success&limit=50`
    - HTTP 403 → caller is not a SUPER_USER.
    """
    return get_all_payment_history(db, skip=skip, limit=limit, status_filter=status)
