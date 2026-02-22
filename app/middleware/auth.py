"""Authentication middleware and dependencies"""
from fastapi import Depends, Header, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional, Union

from app.core.dependencies import get_db
from app.services.auth_service import decode_access_token, get_user_by_id
from app.services.free_trial_service import (
    get_or_create_free_trial_user,
    check_and_increment_usage,
    generate_device_fingerprint,
    generate_cookie_id
)
from app.models.user import User, UserRole
from app.models.free_trial_user import FreeTrialUser
from app.errors.exceptions import UnauthorizedException, ForbiddenException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


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


async def get_user_or_trial(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> tuple[Union[User, FreeTrialUser], Optional[str], bool]:
    """
    Get authenticated user or free trial user
    Automatically generates device fingerprint and cookie ID
    Returns tuple of (user_or_trial, cookie_id_to_set, needs_cookie_consent)
    """
    if token:
        token_data = decode_access_token(token)
        if token_data and token_data.user_id:
            user = get_user_by_id(db, user_id=token_data.user_id)
            if user and user.is_active:
                return user, None, False
    
    client_ip = request.client.host if request.client else None
    accept_language = request.headers.get("Accept-Language")
    
    device_fingerprint = generate_device_fingerprint(
        ip_address=client_ip,
        accept_language=accept_language,
        screen_resolution=None
    )
    
    cookie_id = request.cookies.get("free_trial_id")
    needs_cookie_consent = False
    
    if not cookie_id:
        cookie_id = generate_cookie_id()
        needs_cookie_consent = True
    
    user_agent = request.headers.get("User-Agent")
    trial_user, is_new = get_or_create_free_trial_user(
        db=db,
        device_fingerprint=device_fingerprint,
        cookie_id=cookie_id if not needs_cookie_consent else None,
        user_agent=user_agent,
        ip_address=client_ip
    )
    
    if is_new or trial_user.cookie_consent_given is None:
        needs_cookie_consent = True
    
    cookie_to_set = cookie_id if not needs_cookie_consent else None
    return trial_user, cookie_to_set, needs_cookie_consent


async def require_user_or_trial(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> tuple[Union[User, FreeTrialUser], Optional[dict], Optional[str], bool]:
    """
    Require either authenticated user or valid free trial user
    Returns tuple of (user, trial_info, cookie_to_set, needs_cookie_consent)
    - trial_info is None for registered users
    - cookie_to_set is the cookie ID if it needs to be set, None otherwise
    - needs_cookie_consent: True if user needs to be shown cookie consent dialog
    """
    user_or_trial, cookie_to_set, needs_cookie_consent = await get_user_or_trial(request, token, db)
    
    if isinstance(user_or_trial, User):
        return (user_or_trial, None, None, False)
    
    trial_info = check_and_increment_usage(db, user_or_trial)
    
    if not trial_info["allowed"]:
        raise ForbiddenException(detail=trial_info["message"])
    
    return (user_or_trial, trial_info, cookie_to_set, needs_cookie_consent)

