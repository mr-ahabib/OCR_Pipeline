"""Authentication service with password hashing and JWT"""
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.models.user import User, UserRole
from app.schemas.auth_schemas import UserCreate, TokenData
from app.core.config import settings
import re

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=14
)


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Verify a plain password against a hashed password"""
    if not hashed_password:
        return False  # OAuth-only users have no password
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt with 14 rounds"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """
    Decode and validate a JWT access token
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str: str = payload.get("sub")
        username: str = payload.get("username")
        role: str = payload.get("role")
        
        if user_id_str is None:
            return None
        
        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            return None
        
        return TokenData(user_id=user_id, username=username, role=UserRole(role) if role else None)
    except JWTError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"JWT decode error: {str(e)}")
        return None
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error decoding token: {str(e)}")
        return None


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user with email and password
    """
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    
    user.last_login = datetime.utcnow()
    db.commit()
    
    return user


def create_user(db: Session, user_data: UserCreate) -> User:
    """
    Create a new user with hashed password
    """
    hashed_password = get_password_hash(user_data.password)
    
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
        role=user_data.role,
        is_active=True,
        is_verified=False
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """
    Get user by username
    """
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Get user by email
    """
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """
    Get user by ID
    """
    return db.query(User).filter(User.id == user_id).first()


def get_or_create_google_user(db: Session, google_id: str, email: str, full_name: Optional[str]) -> User:
    """
    Find an existing user by google_id or email, or create a new one.
    Links an existing email-based account to Google if not yet linked.
    """
    # 1. Look up by google_id
    user = db.query(User).filter(User.google_id == google_id).first()
    if user:
        user.last_login = datetime.utcnow()
        db.commit()
        return user

    # 2. Look up by email – link the Google account to the existing user
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.google_id = google_id
        user.auth_provider = "google"
        user.is_verified = True
        if full_name and not user.full_name:
            user.full_name = full_name
        user.last_login = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user

    # 3. Create a brand-new user
    base_username = re.sub(r'[^a-zA-Z0-9_]', '', (full_name or email.split('@')[0]).replace(' ', '_'))[:40] or 'user'
    username = base_username
    counter = 1
    while db.query(User).filter(User.username == username).first():
        username = f"{base_username}{counter}"
        counter += 1

    new_user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=None,
        google_id=google_id,
        auth_provider="google",
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
