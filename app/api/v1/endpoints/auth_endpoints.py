"""Authentication endpoints - Simplified and production-ready"""
from fastapi import APIRouter, Depends, status, Form
from sqlalchemy.orm import Session
from datetime import timedelta
import logging

from app.core.dependencies import get_db
from app.services.auth_service import (
    authenticate_user,
    create_user,
    create_access_token,
    get_user_by_username,
    get_user_by_email,
    get_password_hash,
    verify_password,
    get_or_create_google_user,
    create_email_otp,
    verify_email_otp,
)
from app.schemas.auth_schemas import (
    UserCreate,
    UserResponse,
    Token,
    PasswordChange,
    GoogleAuthRequest,
    OTPRequest,
    OTPVerifyRequest,
    ResendOTPRequest,
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
from app.utils.email import send_otp_email
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/register", response_model=OTPRequest, status_code=status.HTTP_200_OK)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Start registration — validates the submitted data and sends a 6-digit OTP
    to the user's email. The account is **not** created yet.

    Call **/auth/verify-otp** with the code to complete registration and receive
    an access token (auto-login).
    """
    if get_user_by_username(db, user_data.username):
        raise ConflictException(detail="Username already registered")

    if get_user_by_email(db, user_data.email):
        raise ConflictException(detail="Email already registered")

    user_data.role = UserRole.USER
    otp = create_email_otp(db, user_data.email, user_data.model_dump())

    sent = send_otp_email(
        to=user_data.email,
        otp=otp,
        full_name=user_data.full_name or "",
    )
    if not sent:
        logger.warning(f"[Register] OTP email delivery failed for {user_data.email}")

    return OTPRequest(
        message="Verification code sent to your email. Please check your inbox and enter the 6-digit code to complete registration.",
        email=user_data.email,
    )


@router.post("/verify-otp", response_model=Token, status_code=status.HTTP_201_CREATED)
async def verify_otp(body: OTPVerifyRequest, db: Session = Depends(get_db)):
    """
    Verify the 6-digit OTP sent to the user's email.

    On success the user account is created, marked as verified, and an access
    token is returned so the client is immediately logged in.
    """
    try:
        user_payload = verify_email_otp(db, body.email, body.otp)
    except ValueError as exc:
        raise BadRequestException(detail=str(exc))

    if not user_payload:
        raise BadRequestException(detail="OTP verification failed.")

    # Double-check in case another request sneaked in
    if get_user_by_email(db, body.email):
        raise ConflictException(detail="An account with this email already exists. Please log in.")

    from app.schemas.auth_schemas import UserCreate as UC
    new_user = create_user(db, UC(**user_payload))

    # Mark as verified immediately (OTP proves email ownership)
    new_user.is_verified = True
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(
        data={
            "sub": str(new_user.id),
            "username": new_user.username,
            "role": new_user.role.value,
        },
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer", "user": new_user}


@router.post("/resend-otp", response_model=OTPRequest, status_code=status.HTTP_200_OK)
async def resend_otp(body: ResendOTPRequest, db: Session = Depends(get_db)):
    """
    Resend a fresh OTP to *email*.  Only works if the email is not yet registered.
    The previously issued OTP is invalidated automatically.
    """
    from app.models.otp import EmailOTP
    from app.models.otp import EmailOTP

    if get_user_by_email(db, body.email):
        raise ConflictException(detail="An account with this email already exists. Please log in.")

    # Retrieve the pending user_data from the most recent OTP row
    existing = (
        db.query(EmailOTP)
        .filter(EmailOTP.email == body.email)
        .order_by(EmailOTP.created_at.desc())
        .first()
    )
    if not existing:
        raise NotFoundException(detail="No pending registration found for this email. Please register first.")

    otp = create_email_otp(db, body.email, existing.user_data)
    full_name = (existing.user_data or {}).get("full_name", "")
    sent = send_otp_email(to=body.email, otp=otp, full_name=full_name)
    if not sent:
        logger.warning(f"[ResendOTP] Email delivery failed for {body.email}")

    return OTPRequest(
        message="A new verification code has been sent to your email.",
        email=body.email,
    )


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


@router.post("/google", response_model=Token, status_code=status.HTTP_200_OK)
async def google_sign_in(
    payload: GoogleAuthRequest,
    db: Session = Depends(get_db),
):
    if not settings.GOOGLE_CLIENT_ID:
        raise BadRequestException(detail="Google Sign-In is not configured on this server.")

    try:
        idinfo = google_id_token.verify_oauth2_token(
            payload.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise UnauthorizedException(detail=f"Invalid Google ID token: {exc}")

    google_id = idinfo.get("sub")
    email = idinfo.get("email")
    full_name = idinfo.get("name")
    email_verified = idinfo.get("email_verified", False)

    if not email or not email_verified:
        raise UnauthorizedException(detail="Google account email is not verified.")

    user = get_or_create_google_user(db, google_id=google_id, email=email, full_name=full_name)

    if not user.is_active:
        raise UnauthorizedException(detail="This account has been deactivated.")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role.value},
        expires_delta=access_token_expires,
    )

    return {"access_token": access_token, "token_type": "bearer", "user": user}

