"""Free trial user model for tracking anonymous users"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.db.base import Base


class FreeTrialUser(Base):
    """
    Model to track free trial users by device ID
    Allows 3 free OCR requests per device (not per browser) before requiring registration
    """
    __tablename__ = "free_trial_users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String(255), unique=True, nullable=False, index=True)
    usage_count = Column(Integer, default=0, nullable=False)
    max_usage = Column(Integer, default=3, nullable=False)
    
    first_used_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    cookie_id = Column(String(255), nullable=True, index=True)
    
    cookie_consent_given = Column(Boolean, nullable=True)
    cookie_consent_at = Column(DateTime(timezone=True), nullable=True)
    
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)
    
    is_blocked = Column(Boolean, default=False, nullable=False)
    
    def __repr__(self):
        return f"<FreeTrialUser(id={self.id}, device_id='{self.device_id[:20]}...', usage={self.usage_count}/{self.max_usage})>"
    
    def has_usage_left(self) -> bool:
        """Check if user has remaining free trial uses"""
        return self.usage_count < self.max_usage and not self.is_blocked
    
    def increment_usage(self) -> bool:
        """Increment usage count and return True if still within limit"""
        self.usage_count += 1
        return self.has_usage_left()
    
    def get_remaining_uses(self) -> int:
        """Get number of remaining free uses"""
        if self.is_blocked:
            return 0
        remaining = self.max_usage - self.usage_count
        return max(0, remaining)
