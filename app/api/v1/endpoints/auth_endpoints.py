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
    ## Register a new user account (Step 1 of 2)

    **Role:** Public — no authentication required.

    Validates the submitted data and dispatches a 6-digit OTP to the provided
    email address. The user account is **not** created at this stage.

    ### Required fields (JSON body)
    | Field     | Type   | Description                         |
    |-----------|--------|-------------------------------------|
    | username  | string | Unique username                     |
    | email     | string | Valid email — OTP is sent here      |
    | password  | string | Minimum 6 characters                |
    | full_name | string | User's display name (optional)      |

    ### Response
    `{ "message": "...", "email": "<submitted email>" }`

    ### Frontend integration
    1. POST with the registration form data (JSON).
    2. HTTP 200 → navigate to an OTP entry screen, carry `email` in state.
    3. HTTP 409 → "Username / Email already taken".
    4. Next: **POST /auth/verify-otp** with the received OTP code.
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
    ## Verify OTP and complete registration (Step 2 of 2)

    **Role:** Public — no authentication required.

    Validates the 6-digit OTP emailed during `/auth/register`. On success the
    user account is created, marked as verified, and a JWT is returned so the
    client is immediately logged in (no extra login step needed).

    ### Required fields (JSON body)
    | Field | Type   | Description                               |
    |-------|--------|-------------------------------------------|
    | email | string | Same email used at registration           |
    | otp   | string | 6-digit code from the verification email  |

    ### Response
    ```json
    { "access_token": "<JWT>", "token_type": "bearer", "user": { ...UserResponse } }
    ```

    ### Frontend integration
    1. POST `{ email, otp }` from the OTP entry screen.
    2. HTTP 201 → store `access_token`, redirect to dashboard.
    3. HTTP 400 → "Invalid or expired OTP" — let user retry or resend.
    4. HTTP 409 → account already exists, redirect to login.
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
    ## Resend OTP verification email

    **Role:** Public — no authentication required.

    Generates a new 6-digit OTP and invalidates any previously issued code for
    the same email. Only works while the email is still in a *pending
    registration* state (not yet a confirmed account).

    ### Required fields (JSON body)
    | Field | Type   | Description                              |
    |-------|--------|------------------------------------------|
    | email | string | Email used during the original register  |

    ### Response
    `{ "message": "A new verification code has been sent...", "email": "..." }`

    ### Frontend integration
    - Render a "Resend Code" button on the OTP entry screen.
    - Disable for ~60 s after each click to prevent spam.
    - HTTP 404 → no pending registration found — send user back to `/register`.
    - HTTP 409 → account already exists — redirect to login.
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
    ## Login with email and password

    **Role:** Public — no authentication required.

    Authenticates the user with their **email address** and password and returns
    a JWT access token. The form field is named `username` for OAuth2
    compatibility but **must contain the user's email**.

    ### Required fields (form-data — application/x-www-form-urlencoded)
    | Field    | Type   | Description              |
    |----------|--------|--------------------------|
    | username | string | User's **email address** |
    | password | string | Account password         |

    ### Response
    ```json
    { "access_token": "<JWT>", "token_type": "bearer", "user": { ...UserResponse } }
    ```

    ### Frontend integration
    - Send as `application/x-www-form-urlencoded` (standard OAuth2 password flow).
    - Persist the token (`localStorage` or an HTTP-only cookie).
    - Attach to every subsequent request: `Authorization: Bearer <token>`.
    - Axios example:
      ```js
      const params = new URLSearchParams({ username: email, password });
      const { data } = await axios.post('/api/v1/auth/login', params);
      localStorage.setItem('token', data.access_token);
      ```
    - HTTP 401 → "Incorrect email or password".
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
    """
    ## Get the currently authenticated user's profile

    **Role:** Any authenticated user (USER / ADMIN / SUPER_USER).

    **Auth:** `Authorization: Bearer <token>` header required.

    Returns the full profile belonging to the owner of the provided JWT,
    including quota / subscription details.

    ### Response — UserResponse
    `id`, `username`, `email`, `full_name`, `role`, `is_active`, `is_verified`,
    `free_ocr_remaining`, `ocr_quota`, `subscription_expires_at`, etc.

    ### Frontend integration
    - Call on app startup / route guard to hydrate the logged-in user context.
    - HTTP 401 → token missing or expired — redirect to login.
    """
    return current_user


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    ## Change the current user's password

    **Role:** Any authenticated user (USER / ADMIN / SUPER_USER).

    **Auth:** `Authorization: Bearer <token>` header required.

    ### Required fields (JSON body)
    | Field        | Type   | Description                 |
    |--------------|--------|-----------------------------|
    | old_password | string | Current (existing) password |
    | new_password | string | Desired new password        |

    ### Response
    `{ "message": "Password changed successfully" }`

    ### Frontend integration
    - Use in a "Change Password" settings screen.
    - HTTP 400 → "Incorrect old password".
    - After a successful change, consider clearing stored tokens and forcing
      re-login to issue a fresh JWT scoped to the new credentials.
    """
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
    """
    ## Sign in / sign up via Google OAuth2

    **Role:** Public — no authentication required.

    Accepts a Google **ID token** (obtained on the frontend via the Google
    Sign-In button / `google.accounts.id` SDK). The token is verified
    server-side; the endpoint then either logs in the existing account linked
    to that Google identity or automatically creates a new one.

    ### Required fields (JSON body)
    | Field    | Type   | Description                                     |
    |----------|--------|-------------------------------------------------|
    | id_token | string | Google ID token from `google.accounts.id` SDK   |

    ### Response
    ```json
    { "access_token": "<JWT>", "token_type": "bearer", "user": { ...UserResponse } }
    ```

    ### Frontend integration
    ```js
    google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: async ({ credential }) => {
        const { data } = await axios.post('/api/v1/auth/google', { id_token: credential });
        localStorage.setItem('token', data.access_token);
      }
    });
    ```
    - HTTP 400 → Google Sign-In is not configured on this server.
    - HTTP 401 → invalid / expired Google token, or email not verified by Google.
    - HTTP 401 → account deactivated.
    """
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

