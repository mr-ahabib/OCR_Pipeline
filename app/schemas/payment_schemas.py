"""Payment Pydantic schemas."""
from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, List
from datetime import datetime
from enum import Enum

PAGE_COST = 10  # BDT per page


class PaymentStatusEnum(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

class PaymentInitiateRequest(BaseModel):
    """Body sent by the authenticated user to start a payment."""
    pages: int = Field(..., gt=0, description="Number of subscription pages to purchase")
    cust_name: str = Field(..., min_length=2, max_length=100, description="Customer full name")
    cust_phone: str = Field(..., min_length=7, max_length=20, description="Customer phone number")
    cust_address: Optional[str] = Field(None, max_length=255, description="Customer address (optional)")


class PaymentInitiateResponse(BaseModel):
    invoice_number: str
    pages: int
    total_amount: float
    currency: str = "BDT"
    payment_url: str
    message: str = "Payment link created. Redirect the user to payment_url to complete payment."

class PaymentCallbackPayload(BaseModel):
    """
    PayStation delivers the callback as URL query parameters (GET request):
      ?status=Successful&invoice_number=<inv>&trx_id=<id>

    status values: Successful / Failed / Canceled
    """
    invoice_number: Optional[str] = None
    status: Optional[str] = None          # "Successful" / "Failed" / "Canceled"
    trx_id: Optional[str] = None

    class Config:
        extra = "allow"   # accept any extra query params PayStation may add


class PaymentCallbackResponse(BaseModel):
    success: bool
    message: str

class PaymentHistoryItem(BaseModel):
    """Single payment record returned to the caller."""
    id: int
    user_id: int
    invoice_number: str
    pages_purchased: int
    payment_amount: float
    currency: str
    status: PaymentStatusEnum
    created_at: datetime
    updated_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaymentHistoryResponse(BaseModel):
    total: int
    payments: List[PaymentHistoryItem]
