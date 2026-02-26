"""Dashboard response schemas for SuperUser, Admin, and User roles."""
from pydantic import BaseModel
from typing import Optional


class SuperUserDashboardStats(BaseModel):
    """Platform-wide statistics for the superuser overview card."""

    # Users
    total_users: int
    total_admins: int
    total_regular_users: int

    # OCR
    total_ocr_documents: int

    # Payments (individual subscriptions)
    total_revenue_bdt: float
    active_subscriptions: int
    free_trial_users: int

    # Enterprise
    total_enterprises: int
    total_enterprise_revenue_collected: float
    total_enterprise_due: float


class AdminDashboardStats(BaseModel):
    """Admin-level stats: their enterprises and OCR activity."""

    # Enterprise summary
    total_enterprises: int
    total_pages_allocated: int
    total_pages_used: int
    total_pages_remaining: int

    # Billing
    total_revenue_collected: float
    total_due_amount: float
    paid_count: int
    partial_paid_count: int
    due_count: int

    # Own OCR activity
    total_ocr_documents_processed: int


class UserDashboardStats(BaseModel):
    """Personal stats for a regular user's dashboard overview."""

    # Free-tier quota
    free_ocr_limit: int
    free_ocr_used: int
    free_ocr_remaining: int

    # Paid subscription quota
    subscription_pages_total: int
    subscription_pages_used: int
    subscription_pages_remaining: int
    has_active_subscription: bool

    # Document activity
    total_documents: int
    total_pages_processed: int
    last_document_filename: Optional[str] = None
    last_document_created_at: Optional[str] = None
