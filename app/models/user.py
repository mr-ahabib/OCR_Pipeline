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
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    
    # Role and permissions
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.USER)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
    
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
