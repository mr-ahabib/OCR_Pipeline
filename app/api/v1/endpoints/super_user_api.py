"""Super User API endpoints - Admin management and privileged operations"""
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.dependencies import get_db
from app.services.auth_service import (
    create_user,
    get_user_by_username,
    get_user_by_email
)
from app.services.free_trial_service import (
    get_trial_user_by_device_id,
    block_trial_user
)
from app.schemas.auth_schemas import (
    UserCreate,
    UserResponse
)
from app.schemas.free_trial_schemas import FreeTrialUserResponse
from app.middleware.auth import require_super_user
from app.models.user import User, UserRole
from app.models.free_trial_user import FreeTrialUser
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
    """Create an admin user (super user only)"""
    if get_user_by_username(db, user_data.username):
        raise ConflictException(detail="Username already registered")
    
    if get_user_by_email(db, user_data.email):
        raise ConflictException(detail="Email already registered")
    
    # Super user can create admin users
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
    """Delete any user (super user only)"""
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
    """List all users (super user only)"""
    users = db.query(User).offset(skip).limit(limit).all()
    return users
