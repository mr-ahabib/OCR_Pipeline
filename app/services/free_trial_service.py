"""Free trial service for managing anonymous user trials"""
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import hashlib
import uuid

from app.models.free_trial_user import FreeTrialUser
from app.errors.exceptions import ForbiddenException


def generate_device_fingerprint(
    ip_address: Optional[str] = None,
    accept_language: Optional[str] = None,
    screen_resolution: Optional[str] = None
) -> str:
    """
    Generate a device fingerprint from available data.
    Excludes User-Agent so the same device maps to the same fingerprint
    regardless of which browser is used.
    """
    fingerprint_data = (
        f"{ip_address or 'unknown'}|"
        f"{accept_language or 'unknown'}|"
        f"{screen_resolution or 'unknown'}"
    )
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()


def get_or_create_free_trial_user(
    db: Session,
    device_fingerprint: str,
    cookie_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> tuple[FreeTrialUser, bool]:
    """
    Get existing free trial user or create new one.
    Looks up by device_fingerprint first, then cookie_id as fallback.
    Returns (trial_user, is_new) tuple.
    """
    trial_user = None
    is_new = False
    
    trial_user = db.query(FreeTrialUser).filter(
        FreeTrialUser.device_id == device_fingerprint
    ).first()
    
    if trial_user:
        trial_user.last_used_at = datetime.now(timezone.utc)
        if cookie_id and not trial_user.cookie_id:
            trial_user.cookie_id = cookie_id
        if user_agent:
            trial_user.user_agent = user_agent
        if ip_address:
            trial_user.ip_address = ip_address
        db.commit()
        db.refresh(trial_user)
        return trial_user, False
    
    if cookie_id:
        trial_user = db.query(FreeTrialUser).filter(
            FreeTrialUser.cookie_id == cookie_id
        ).first()
        
        if trial_user:
            trial_user.device_id = device_fingerprint
            trial_user.last_used_at = datetime.now(timezone.utc)
            if user_agent:
                trial_user.user_agent = user_agent
            if ip_address:
                trial_user.ip_address = ip_address
            db.commit()
            db.refresh(trial_user)
            return trial_user, False
    
    trial_user = FreeTrialUser(
        device_id=device_fingerprint,
        cookie_id=cookie_id,
        user_agent=user_agent,
        ip_address=ip_address,
        usage_count=0,
        max_usage=3,
        cookie_consent_given=None
    )
    
    db.add(trial_user)
    db.commit()
    db.refresh(trial_user)
    
    return trial_user, True


def check_and_increment_usage(
    db: Session,
    trial_user: FreeTrialUser
) -> Dict[str, Any]:
    """
    Check if user has usage left and increment counter
    Returns dict with usage info and whether request is allowed
    """
    if trial_user.is_blocked:
        return {
            "allowed": False,
            "usage_count": trial_user.usage_count,
            "max_usage": trial_user.max_usage,
            "remaining": 0,
            "message": "Your device has been blocked. Please contact support or register for an account."
        }
    
    if trial_user.usage_count >= trial_user.max_usage:
        return {
            "allowed": False,
            "usage_count": trial_user.usage_count,
            "max_usage": trial_user.max_usage,
            "remaining": 0,
            "message": "Free trial limit reached. Please register to continue using our service."
        }
    
    trial_user.usage_count += 1
    trial_user.last_used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(trial_user)
    
    remaining = trial_user.max_usage - trial_user.usage_count
    
    message = ""
    if remaining == 0:
        message = "This was your last free trial. Please register to continue."
    elif remaining == 1:
        message = f"You have {remaining} free trial remaining. Register to get unlimited access."
    else:
        message = f"You have {remaining} free trials remaining."
    
    return {
        "allowed": True,
        "usage_count": trial_user.usage_count,
        "max_usage": trial_user.max_usage,
        "remaining": remaining,
        "message": message
    }


def get_trial_user_by_device_id(
    db: Session,
    device_id: str
) -> Optional[FreeTrialUser]:
    """Get free trial user by device ID"""
    return db.query(FreeTrialUser).filter(
        FreeTrialUser.device_id == device_id
    ).first()


def get_trial_user_info(
    db: Session,
    device_id: str
) -> Optional[Dict[str, Any]]:
    """Get usage information for a free trial user"""
    trial_user = get_trial_user_by_device_id(db, device_id)
    
    if not trial_user:
        return {
            "usage_count": 0,
            "max_usage": 3,
            "remaining": 3,
            "is_new": True
        }
    
    return {
        "usage_count": trial_user.usage_count,
        "max_usage": trial_user.max_usage,
        "remaining": trial_user.get_remaining_uses(),
        "is_blocked": trial_user.is_blocked,
        "is_new": False
    }


def block_trial_user(
    db: Session,
    device_id: str
) -> bool:
    """Block a free trial user (admin function)"""
    trial_user = get_trial_user_by_device_id(db, device_id)
    
    if trial_user:
        trial_user.is_blocked = True
        db.commit()
        return True
    
    return False


def generate_cookie_id() -> str:
    """Generate a unique cookie ID for tracking"""
    return str(uuid.uuid4())


def update_cookie_consent(
    db: Session,
    device_fingerprint: str,
    cookie_id: Optional[str],
    consent_given: bool
) -> bool:
    """
    Update cookie consent for a trial user
    
    Args:
        db: Database session
        device_fingerprint: Device fingerprint hash
        cookie_id: Cookie ID (if available)
        consent_given: True if user accepted, False if rejected
    
    Returns:
        True if updated successfully, False if user not found
    """
    # Try to find user by fingerprint or cookie
    trial_user = db.query(FreeTrialUser).filter(
        FreeTrialUser.device_id == device_fingerprint
    ).first()
    
    if not trial_user and cookie_id:
        trial_user = db.query(FreeTrialUser).filter(
            FreeTrialUser.cookie_id == cookie_id
        ).first()
    
    if not trial_user:
        return False
    
    # Update consent information
    trial_user.cookie_consent_given = consent_given
    trial_user.cookie_consent_at = datetime.now(timezone.utc)
    
    # If accepted, ensure cookie_id is set
    if consent_given and cookie_id:
        trial_user.cookie_id = cookie_id
    # If rejected, clear cookie_id
    elif not consent_given:
        trial_user.cookie_id = None
    
    db.commit()
    db.refresh(trial_user)
    
    return True