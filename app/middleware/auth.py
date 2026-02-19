"""Authentication middleware and dependencies"""
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional

from app.core.dependencies import get_db
from app.services.auth_service import decode_access_token, get_user_by_id
from app.models.user import User, UserRole
from app.errors.exceptions import UnauthorizedException, ForbiddenException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token"""
    token_data = decode_access_token(token)
    
    if token_data is None or token_data.user_id is None:
        raise UnauthorizedException(detail="Could not validate credentials")
    
    user = get_user_by_id(db, user_id=token_data.user_id)
    
    if user is None:
        raise UnauthorizedException(detail="User not found")
    
    if not user.is_active:
        raise ForbiddenException(detail="Inactive user")
    
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise ForbiddenException(detail="Inactive user")
    return current_user


def require_role(required_role: UserRole):
    """Dependency to require a specific role or higher"""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.has_permission(required_role):
            raise ForbiddenException(
                detail=f"Insufficient permissions. Required role: {required_role.value}"
            )
        return current_user
    return role_checker


require_super_user = require_role(UserRole.SUPER_USER)
require_admin = require_role(UserRole.ADMIN)
require_user = require_role(UserRole.USER)


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None"""
    if not token:
        return None
    
    token_data = decode_access_token(token)
    
    if token_data is None or token_data.user_id is None:
        return None
    
    user = get_user_by_id(db, user_id=token_data.user_id)
    
    if user is None or not user.is_active:
        return None
    
    return user
