"""CRUD operations for OCR documents"""
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.ocr_document import OCRDocument
from app.schemas.ocr_schemas import OCRDocumentCreate
from app.utils.file_storage import delete_uploaded_file


def create_ocr_document(db: Session, ocr_data: OCRDocumentCreate) -> OCRDocument:
    """
    Create a new OCR document record in the database
    """
    db_document = OCRDocument(
        user_id=ocr_data.user_id,
        filename=ocr_data.filename,
        file_path=ocr_data.file_path,
        file_type=ocr_data.file_type,
        file_size=ocr_data.file_size,
        ocr_mode=ocr_data.ocr_mode,
        ocr_engine=ocr_data.ocr_engine,
        languages=ocr_data.languages,
        extracted_text=ocr_data.extracted_text,
        confidence=ocr_data.confidence,
        total_pages=ocr_data.total_pages,
        pages_data=ocr_data.pages_data,
        processing_time=ocr_data.processing_time,
        character_count=ocr_data.character_count
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    return db_document


def get_ocr_document(db: Session, document_id: int, user_id: Optional[int] = None, include_deleted: bool = False) -> Optional[OCRDocument]:
    """Get an OCR document by ID, optionally filtered by user and deleted status."""
    query = db.query(OCRDocument).filter(OCRDocument.id == document_id)
    
    if user_id is not None:
        query = query.filter(OCRDocument.user_id == user_id)
    
    if not include_deleted:
        query = query.filter(OCRDocument.is_deleted == False)
    
    return query.first()


def get_ocr_documents(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    ocr_mode: Optional[str] = None,
    user_id: Optional[int] = None,
    include_deleted: bool = False
) -> List[OCRDocument]:
    """Get list of OCR documents with optional filtering by user, mode, and deleted status."""
    query = db.query(OCRDocument)
    
    if user_id is not None:
        query = query.filter(OCRDocument.user_id == user_id)
    
    if not include_deleted:
        query = query.filter(OCRDocument.is_deleted == False)
    
    if ocr_mode:
        query = query.filter(OCRDocument.ocr_mode == ocr_mode)
    
    return query.order_by(OCRDocument.created_at.desc()).offset(skip).limit(limit).all()


def delete_ocr_document(db: Session, document_id: int, user_id: Optional[int] = None, delete_from_storage: bool = False) -> bool:
    """
    Delete an OCR document. If delete_from_storage is True, hard-deletes the file and record.
    Otherwise performs a soft delete (marks is_deleted=True).
    """
    query = db.query(OCRDocument).filter(OCRDocument.id == document_id)
    
    if user_id is not None:
        query = query.filter(OCRDocument.user_id == user_id)
    
    document = query.first()
    if document:
        if delete_from_storage:
            if document.file_path:
                delete_uploaded_file(document.file_path)
            db.delete(document)
        else:
            document.is_deleted = True
        
        db.commit()
        return True
    return False
