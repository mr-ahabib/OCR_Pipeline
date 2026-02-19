"""Document management endpoints - Simplified and production-ready"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

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
    db: Session = Depends(get_db)
):
    """Get list of all OCR documents with pagination and filtering"""
    documents = get_ocr_documents(db, skip=skip, limit=limit, ocr_mode=ocr_mode)
    return documents


@router.get("/{document_id}", response_model=OCRDocumentResponse)
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get a specific OCR document by ID"""
    document = get_ocr_document(db, document_id)
    if not document:
        raise NotFoundException(detail="Document not found")
    return document


@router.delete("/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Delete an OCR document by ID"""
    success = delete_ocr_document(db, document_id)
    if not success:
        raise NotFoundException(detail="Document not found")
    return {"message": "Document deleted successfully"}
