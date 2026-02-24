"""Super User API endpoints"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_db
from app.services.auth_service import (
    create_user,
    get_user_by_username,
    get_user_by_email
)
from app.schemas.auth_schemas import (
    UserCreate,
    UserResponse
)
from app.middleware.auth import require_super_user
from app.models.user import User, UserRole
from app.errors.exceptions import (
    ConflictException,
    NotFoundException,
    BadRequestException
)

router = APIRouter()


@router.post("/create-admin", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    user_data: UserCreate,
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db)
):
    """
    ## Create an ADMIN or USER account

    **Role:** SUPER_USER only.

    **Auth:** `Authorization: Bearer <token>` header required.

    Directly creates an account with role `ADMIN` or `USER` — bypassing the
    OTP email flow used by the public `/auth/register` endpoint. Useful for
    provisioning staff accounts from the admin panel.

    ### Required fields (JSON body)
    | Field     | Type   | Description                              |
    |-----------|--------|------------------------------------------|
    | username  | string | Unique username                          |
    | email     | string | Unique email address                     |
    | password  | string | Initial password (min 6 chars)           |
    | full_name | string | Display name (optional)                  |
    | role      | string | `ADMIN` or `USER` — cannot create SUPER_USER |

    ### Response — UserResponse
    Full profile of the newly created user.

    ### Frontend integration
    - Use in a "Create User" form in the admin dashboard.
    - HTTP 409 → username or email already taken.
    - HTTP 400 → invalid role (only `ADMIN` / `USER` allowed).
    - HTTP 403 → caller is not a SUPER_USER.
    """
    if get_user_by_username(db, user_data.username):
        raise ConflictException(detail="Username already registered")
    
    if get_user_by_email(db, user_data.email):
        raise ConflictException(detail="Email already registered")
    
    if user_data.role not in [UserRole.ADMIN, UserRole.USER]:
        raise BadRequestException(detail="Can only create ADMIN or USER roles")
    
    user = create_user(db, user_data)
    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db)
):
    """
    ## Delete a user account (hard delete)

    **Role:** SUPER_USER only.

    **Auth:** `Authorization: Bearer <token>` header required.

    Permanently removes the user record from the database. This is a
    hard delete — the action is irreversible.

    ### Path parameter
    | Param   | Type | Description        |
    |---------|------|--------------------|
    | user_id | int  | ID of the user     |

    ### Response
    `{ "message": "User deleted successfully" }`

    ### Frontend integration
    - Trigger from an admin "Users" table with a "Delete" action.
    - Show a confirmation dialog before calling.
    - HTTP 400 → cannot delete your own account.
    - HTTP 404 → user not found.
    - HTTP 403 → caller is not a SUPER_USER.
    """
    if user_id == current_user.id:
        raise BadRequestException(detail="Cannot delete your own account")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundException(detail="User not found")
    
    db.delete(user)
    db.commit()
    
    return {"message": "User deleted successfully"}


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_super_user),
    db: Session = Depends(get_db)
):
    """
    ## List all users

    **Role:** SUPER_USER only.

    **Auth:** `Authorization: Bearer <token>` header required.

    Returns a paginated list of every user account in the system regardless
    of role or status.

    ### Query parameters
    | Param | Type | Default | Description              |
    |-------|------|---------|--------------------------|
    | skip  | int  | 0       | Pagination offset        |
    | limit | int  | 100     | Max records to return    |

    ### Response — List[UserResponse]
    Each entry includes `id`, `username`, `email`, `role`, `is_active`,
    `is_verified`, subscription fields, and quota balances.

    ### Frontend integration
    - Render in an admin "Users" management table.
    - Use `skip` + `limit` for pagination.
    - Example: `GET /super-user/users?skip=0&limit=25`
    - HTTP 403 → caller is not a SUPER_USER.
    """
    users = db.query(User).offset(skip).limit(limit).all()
    return users
