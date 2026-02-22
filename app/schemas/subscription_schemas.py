"""Subscription Pydantic schemas"""
from pydantic import BaseModel, Field


PAGE_COST = 10  # currency units per page
FREE_OCR_LIMIT = 3


class SubscriptionCostRequest(BaseModel):
    """Calculate cost for a given number of pages."""
    pages: int = Field(..., gt=0, description="Number of pages to subscribe for")


class SubscriptionCostResponse(BaseModel):
    """Cost breakdown for a subscription."""
    pages: int
    cost_per_page: int = PAGE_COST
    total_cost: int


class SubscriptionRequest(BaseModel):
    """Create / top-up a subscription for the authenticated user."""
    pages: int = Field(..., gt=0, description="Number of pages to purchase")


class SubscriptionStatus(BaseModel):
    """Current quota status for the authenticated user."""
    # Free-tier
    free_ocr_limit: int = FREE_OCR_LIMIT
    free_ocr_used: int
    free_ocr_remaining: int

    # Paid subscription
    subscription_pages_total: int
    subscription_pages_used: int
    subscription_pages_remaining: int
    has_active_subscription: bool

    # Convenience
    can_do_ocr: bool  # True if any quota remains
    message: str
