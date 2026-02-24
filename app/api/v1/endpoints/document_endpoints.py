"""Document management endpoints - Simplified and production-ready"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.middleware.auth import require_user
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
    """
    ## List OCR documents

    **Role:** Any authenticated user (USER / ADMIN / SUPER_USER).

    **Auth:** `Authorization: Bearer <token>` header required.

    - **Regular users (USER/ADMIN):** returns only their own non-deleted documents.
    - **SUPER_USER:** returns *all* documents across all users, including
      soft-deleted ones.

    ### Query parameters
    | Param    | Type   | Default | Description                                     |
    |----------|--------|---------|-------------------------------------------------|
    | skip     | int    | 0       | Pagination offset (number of records to skip)   |
    | limit    | int    | 100     | Max records to return (max 500)                 |
    | ocr_mode | string | null    | Filter by mode: `bangla`, `english`, or `mixed` |

    ### Frontend integration
    - Use `skip` + `limit` to implement paginated document history.
    - Pass `ocr_mode` to filter results by language mode.
    - Example: `GET /documents/?skip=0&limit=20&ocr_mode=bangla`
    """

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
    """
    ## Get a single OCR document by ID

    **Role:** Any authenticated user (USER / ADMIN / SUPER_USER).

    **Auth:** `Authorization: Bearer <token>` header required.

    - **Regular users:** can only retrieve their own non-deleted documents.
    - **SUPER_USER:** can retrieve any document including soft-deleted ones.

    ### Path parameter
    | Param       | Type | Description           |
    |-------------|------|-----------------------|
    | document_id | int  | ID of the OCR document|

    ### Response — OCRDocumentResponse
    Full document record including `extracted_text`, `confidence`,
    `total_pages`, `pages_data`, `file_type`, `ocr_mode`, etc.

    ### Frontend integration
    - Use when opening a document detail / result view.
    - HTTP 404 → document does not exist or does not belong to the user.
    """

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
    """
    ## Delete an OCR document

    **Role:** Any authenticated user (USER / ADMIN / SUPER_USER).

    **Auth:** `Authorization: Bearer <token>` header required.

    - **Regular users (USER/ADMIN):** soft-delete their own documents only
      (record remains in DB but is hidden from list/get queries).
    - **SUPER_USER:** hard-delete any document — permanently removes the record
      **and** the file from storage.

    ### Path parameter
    | Param       | Type | Description            |
    |-------------|------|------------------------|
    | document_id | int  | ID of the OCR document |

    ### Response
    `{ "message": "Document deleted from database successfully" }` (regular user)
    `{ "message": "Document permanently deleted successfully" }` (super user)

    ### Frontend integration
    - Show a confirmation dialog before calling this endpoint.
    - HTTP 404 → document not found or doesn't belong to the current user.
    - Remove the deleted document from the local list state on success.
    """

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
