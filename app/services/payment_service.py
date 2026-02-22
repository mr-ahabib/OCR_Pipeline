from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import PaymentHistory, PaymentStatus
from app.models.user import User
from app.schemas.payment_schemas import (
    PAGE_COST,
    PaymentHistoryItem,
    PaymentHistoryResponse,
    PaymentInitiateResponse,
)

logger = logging.getLogger(__name__)

PAYSTATION_CURRENCY = "BDT"

def _generate_invoice_number(user_id: int) -> str:
    """
    Create a short, unique invoice number that embeds user_id for easy lookup.
    Format: <user_id>-<8-hex-chars>   e.g. "42-a3f09c1b"
    """
    random_part = uuid.uuid4().hex[:12].upper()
    return f"{user_id}-{random_part}"


def _build_callback_url() -> str:
    """Return the absolute URL PayStation will POST the result to."""
    if not settings.API_BASE_URL:
        raise ValueError("API_BASE_URL is not configured. Set it in your .env file.")
    return f"{settings.API_BASE_URL.rstrip('/')}/api/v1/payment/callback"

async def initiate_payment(
    db: Session,
    user: User,
    pages: int,
    cust_name: str,
    cust_phone: str,
    cust_address: Optional[str] = None,
) -> PaymentInitiateResponse:
    """
    1. Insert a PENDING PaymentHistory row (so we always have an audit trail).
    2. Call PayStation to create a checkout link.
    3. Store the initiation response on the row and return the payment_url.

    Raises httpx.HTTPError or ValueError on failure (DB is rolled back cleanly).
    """
    amount = float(pages * PAGE_COST)
    invoice_number = _generate_invoice_number(user.id)
    callback_url = _build_callback_url()

    payment_row = PaymentHistory(
        user_id=user.id,
        invoice_number=invoice_number,
        pages_purchased=pages,
        payment_amount=amount,
        currency=PAYSTATION_CURRENCY,
        status=PaymentStatus.PENDING,
    )
    try:
        db.add(payment_row)
        db.commit()
        db.refresh(payment_row)
    except Exception as exc:
        db.rollback()
        logger.error(f"[Payment] DB insert PENDING failed: {exc}")
        raise

    payload = {
        "merchantId": settings.PAYSTATION_MERCHANT_ID,
        "password": settings.PAYSTATION_MERCHANT_PASSWORD,
        "invoice_number": invoice_number,
        "currency": PAYSTATION_CURRENCY,
        "payment_amount": int(amount),        # PayStation expects integer
        "pay_with_charge": 1,
        "cust_name": cust_name,
        "cust_phone": cust_phone,
        "cust_email": user.email,
        "cust_address": cust_address or "",
        "callback_url": callback_url,
        "reference": f"OCR Subscription – {pages} pages",
        "checkout_items": f"OCR Subscription: {pages} pages @ {PAGE_COST} BDT/page",
        "opt_a": str(user.id),
        "opt_b": str(pages),
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(settings.PAYSTATION_API_URL, data=payload)
            resp.raise_for_status()
            ps_data = resp.json()
    except Exception as exc:
        try:
            payment_row.status = PaymentStatus.FAILED
            payment_row.initiation_response = {"error": str(exc)}
            db.commit()
        except Exception as db_exc:
            db.rollback()
            logger.error(f"[Payment] Could not mark FAILED after PayStation error: {db_exc}")
        logger.error(f"[Payment] PayStation API call failed for invoice {invoice_number}: {exc}")
        raise ValueError(f"Payment gateway error: {exc}") from exc


    status_code = str(ps_data.get("status_code", ""))
    payment_url = ps_data.get("payment_url") or ps_data.get("redirectGatewayURL")

    try:
        payment_row.initiation_response = ps_data
        if status_code == "200" and payment_url:
            db.commit()
        else:
            payment_row.status = PaymentStatus.FAILED
            db.commit()
            error_msg = ps_data.get("message", "Unknown PayStation error")
            logger.error(f"[Payment] PayStation rejected invoice {invoice_number}: {error_msg}")
            raise ValueError(f"Payment gateway rejected the request: {error_msg}")
    except ValueError:
        raise
    except Exception as exc:
        db.rollback()
        logger.error(f"[Payment] DB update after PayStation response failed: {exc}")
        raise

    logger.info(
        f"[Payment] Initiated invoice={invoice_number} user_id={user.id} "
        f"pages={pages} amount={amount} BDT → {payment_url}"
    )

    return PaymentInitiateResponse(
        invoice_number=invoice_number,
        pages=pages,
        total_amount=amount,
        currency=PAYSTATION_CURRENCY,
        payment_url=payment_url,
    )


def process_payment_callback(
    db: Session,
    invoice_number: str,
    reported_status: str,
    reported_amount: Optional[float],
    raw_payload: dict,
) -> dict:
    """
    Handle the POST callback from PayStation after a payment attempt.

    Returns a dict with {"success": bool, "message": str}.

    Transaction safety
    ───────────────────
    • Entire handler runs inside a single DB transaction.
    • On any exception → db.rollback() + log + return failure response.
      (We never raise to the caller so PayStation always gets HTTP 200.)
    """
    try:
        # ── 1. Look up the invoice ────────────────────────────────────────────
        payment_row: Optional[PaymentHistory] = (
            db.query(PaymentHistory)
            .filter(PaymentHistory.invoice_number == invoice_number)
            .with_for_update()          # row-level lock for concurrent callbacks
            .first()
        )

        if not payment_row:
            logger.warning(f"[Callback] Unknown invoice: {invoice_number}")
            return {"success": False, "message": "Invoice not found"}

        # ── 2. Idempotency guard ──────────────────────────────────────────────
        if payment_row.status == PaymentStatus.SUCCESS:
            logger.info(f"[Callback] Duplicate callback for already-SUCCESS invoice {invoice_number}")
            return {"success": True, "message": "Payment already processed"}

        # ── 3. Store raw callback payload ─────────────────────────────────────
        payment_row.callback_payload = raw_payload

        # ── 4. Verify amount ──────────────────────────────────────────────────
        if reported_amount is not None:
            try:
                if abs(float(reported_amount) - payment_row.payment_amount) > 0.01:
                    logger.error(
                        f"[Callback] Amount mismatch for {invoice_number}: "
                        f"expected {payment_row.payment_amount}, got {reported_amount}"
                    )
                    payment_row.status = PaymentStatus.FAILED
                    db.commit()
                    return {"success": False, "message": "Payment amount mismatch"}
            except (TypeError, ValueError):
                pass  # Skip amount check if parsing fails

        ps_status = (reported_status or "").strip().lower()
        if ps_status not in ("successful", "success", "1", "200"):
            payment_row.status = PaymentStatus.FAILED if ps_status == "failed" else PaymentStatus.CANCELLED
            db.commit()
            logger.info(f"[Callback] Non-success payment for {invoice_number}: {ps_status}")
            return {"success": False, "message": f"Payment status: {ps_status}"}

        user: Optional[User] = db.query(User).filter(User.id == payment_row.user_id).with_for_update().first()
        if not user:
            logger.error(f"[Callback] User {payment_row.user_id} not found for invoice {invoice_number}")
            payment_row.status = PaymentStatus.FAILED
            db.commit()
            return {"success": False, "message": "User not found"}

        user.subscription_pages_total = (user.subscription_pages_total or 0) + payment_row.pages_purchased
        payment_row.status = PaymentStatus.SUCCESS
        payment_row.paid_at = datetime.now(timezone.utc)

        db.commit()

        logger.info(
            f"[Callback] SUCCESS invoice={invoice_number} user_id={user.id} "
            f"pages_added={payment_row.pages_purchased} "
            f"new_total={user.subscription_pages_total}"
        )
        return {"success": True, "message": "Payment confirmed and subscription activated"}

    except Exception as exc:
        db.rollback()
        logger.error(f"[Callback] Unhandled exception for invoice {invoice_number}: {exc}", exc_info=True)
        return {"success": False, "message": "Internal processing error"}


def get_user_payment_history(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 50,
) -> PaymentHistoryResponse:
    """Return paginated payment history for a single user."""
    query = db.query(PaymentHistory).filter(PaymentHistory.user_id == user_id)
    total = query.count()
    rows = query.order_by(PaymentHistory.created_at.desc()).offset(skip).limit(limit).all()
    return PaymentHistoryResponse(
        total=total,
        payments=[PaymentHistoryItem.from_orm(r) for r in rows],
    )


def get_all_payment_history(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
) -> PaymentHistoryResponse:
    """Return paginated payment history across all users (super_user view)."""
    query = db.query(PaymentHistory)
    if status_filter:
        try:
            query = query.filter(PaymentHistory.status == PaymentStatus(status_filter))
        except ValueError:
            pass  # ignore invalid filter value
    total = query.count()
    rows = query.order_by(PaymentHistory.created_at.desc()).offset(skip).limit(limit).all()
    return PaymentHistoryResponse(
        total=total,
        payments=[PaymentHistoryItem.from_orm(r) for r in rows],
    )
