"""Authentication endpoints - Simplified and production-ready"""
from fastapi import APIRouter, Depends, status, Form
from sqlalchemy.orm import Session
from datetime import timedelta

from app.core.dependencies import get_db
from app.services.auth_service import (
    authenticate_user,
    create_user,
    create_access_token,
    get_user_by_username,
    get_user_by_email,
    get_password_hash,
    verify_password
)
from app.schemas.auth_schemas import (
    UserCreate,
    UserResponse,
    Token,
    PasswordChange,
)
from app.middleware.auth import get_current_active_user
from app.models.user import User, UserRole
from app.core.config import settings
from app.errors.exceptions import (
    ConflictException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException
)

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user (role will be set to USER)"""
    if get_user_by_username(db, user_data.username):
        raise ConflictException(detail="Username already registered")
    
    if get_user_by_email(db, user_data.email):
        raise ConflictException(detail="Email already registered")
    
    user_data.role = UserRole.USER
    user = create_user(db, user_data)
    return user


@router.post("/login", response_model=Token)
async def login(
    username: str = Form(..., description="Enter your EMAIL address here"),
    password: str = Form(..., description="Your password"),
    db: Session = Depends(get_db)
):
    """
    Login with email and password to get access token.
    
    **For Swagger UI Authorize**: Enter your **email address** in the 'username' field.
    This endpoint uses email-based authentication.
    """
    user = authenticate_user(db, username, password)
    
    if not user:
        raise UnauthorizedException(detail="Incorrect email or password")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role.value},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information"""
    return current_user


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Change current user's password"""
    if not verify_password(password_data.old_password, current_user.hashed_password):
        raise BadRequestException(detail="Incorrect old password")
    
    current_user.hashed_password = get_password_hash(password_data.new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}

