"""EmailOTP — stores pending registration OTP codes."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String
from sqlalchemy.sql import func

from app.db.base import Base


class EmailOTP(Base):
    """
    Holds a one-time 6-digit code sent to a user's email before account creation.

    Lifecycle
    ---------
    1. User submits registration form → row inserted (is_used=False).
    2. User enters code   → is_used=True, user account created, token returned.
    3. Expired / used rows can be cleaned up by a background job.
    """

    __tablename__ = "email_otps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    otp_code = Column(String(6), nullable=False)

    # Full UserCreate payload stored as JSON so we can reconstruct the user
    # without asking the client to resend all fields at verification time.
    user_data = Column(JSON, nullable=False)

    expires_at = Column(DateTime(timezone=False), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<EmailOTP(id={self.id}, email={self.email!r}, "
            f"expires_at={self.expires_at}, is_used={self.is_used})>"
        )
