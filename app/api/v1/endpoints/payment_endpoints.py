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
    **Initiate a subscription payment** via PayStation.

    - Only available for regular users (role = USER).
    - Creates a payment record with status **pending**.
    - Returns a `payment_url` — redirect the user to this URL to complete payment.
    - Cost: **pages × 10 BDT**.

    After the user completes (or cancels) payment, PayStation will POST to our
    `/payment/callback` endpoint automatically.
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
    **PayStation payment callback** (internal — not called by end-users).

    PayStation redirects here via GET with query parameters after every payment
    attempt:  ?status=Successful&invoice_number=<inv>&trx_id=<id>

    We always return HTTP 200 so PayStation doesn't retry.
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
    **My payment history** — returns the authenticated user's own payment records.

    Records are returned newest-first.
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
    **All users' payment history** — available to super_user only.

    Results are newest-first and can be filtered by `status`.
    """
    return get_all_payment_history(db, skip=skip, limit=limit, status_filter=status)
