"""User model with role-based access control"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
from enum import Enum
from app.db.base import Base


class UserRole(str, Enum):
    """User role enumeration"""
    SUPER_USER = "super_user"
    ADMIN = "admin"
    USER = "user"


class User(Base):
    """
    User model with role-based access control
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)  # nullable for OAuth-only users
    full_name = Column(String(255), nullable=True)

    # OAuth fields
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    auth_provider = Column(String(50), nullable=False, default="local")  # "local" or "google"
    
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.USER)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    free_ocr_used = Column(Integer, default=0, nullable=False)

    subscription_pages_total = Column(Integer, default=0, nullable=False)
    subscription_pages_used = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"

    # ── quota helpers ──────────────────────────────────────────
    FREE_OCR_LIMIT = 3
    PAGE_COST = 10  # currency units per page

    @property
    def free_ocr_remaining(self) -> int:
        return max(0, self.FREE_OCR_LIMIT - (self.free_ocr_used or 0))

    @property
    def subscription_pages_remaining(self) -> int:
        return max(0, (self.subscription_pages_total or 0) - (self.subscription_pages_used or 0))

    @property
    def has_active_subscription(self) -> bool:
        return self.subscription_pages_remaining > 0
    # ───────────────────────────────────────────────────────────

    def has_permission(self, required_role: UserRole) -> bool:
        """
        Check if user has required permission level
        Hierarchy: SUPER_USER > ADMIN > USER
        """
        role_hierarchy = {
            UserRole.SUPER_USER: 3,
            UserRole.ADMIN: 2,
            UserRole.USER: 1
        }
        return role_hierarchy.get(self.role, 0) >= role_hierarchy.get(required_role, 0)
