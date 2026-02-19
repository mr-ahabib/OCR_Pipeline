"""Document management endpoints - Simplified and production-ready"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.middleware.auth import require_super_user, require_user, require_admin
from app.models.user import User, UserRole
from app.services.ocr_crud import (
    get_ocr_document,
    get_ocr_documents,
    delete_ocr_document
)
from app.schemas.ocr_schemas import OCRDocumentResponse
from app.core.dependencies import get_db
from app.errors.exceptions import NotFoundException

router = APIRouter()


@router.get("/", response_model=List[OCRDocumentResponse])
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    ocr_mode: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):

    # Only Superusers can see all documents (including deleted), others only see their own (non-deleted)
    is_superuser = current_user.role == UserRole.SUPER_USER
    user_id = None if is_superuser else current_user.id
    include_deleted = is_superuser  # Superusers can see soft-deleted documents
    
    documents = get_ocr_documents(db, skip=skip, limit=limit, ocr_mode=ocr_mode, user_id=user_id, include_deleted=include_deleted)
    return documents


@router.get("/{document_id}", response_model=OCRDocumentResponse)
async def get_document(
    document_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):

    # Only Superusers can access any document (including deleted), others only their own (non-deleted)
    is_superuser = current_user.role == UserRole.SUPER_USER
    user_id = None if is_superuser else current_user.id
    include_deleted = is_superuser  # Superusers can see soft-deleted documents
    
    document = get_ocr_document(db, document_id, user_id=user_id, include_deleted=include_deleted)
    if not document:
        raise NotFoundException(detail="Document not found")
    return document


@router.delete("/{document_id}")
async def delete_document(
    document_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):

    # Only Superusers can perform hard delete (permanent deletion from storage)
    is_superuser = current_user.role == UserRole.SUPER_USER
    delete_from_storage = is_superuser
    
    # Only Superusers can delete any document, others can only delete their own
    user_id = None if is_superuser else current_user.id
    
    success = delete_ocr_document(db, document_id, user_id=user_id, delete_from_storage=delete_from_storage)
    if not success:
        raise NotFoundException(detail="Document not found")
    
    delete_type = "permanently deleted" if delete_from_storage else "deleted from database"
    return {"message": f"Document {delete_type} successfully"}
