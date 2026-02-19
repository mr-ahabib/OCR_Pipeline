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
    """
    Get an OCR document by ID
    If user_id is provided, only return document if it belongs to that user
    If include_deleted is False, filter out soft-deleted documents
    """
    query = db.query(OCRDocument).filter(OCRDocument.id == document_id)
    
    if user_id is not None:
        query = query.filter(OCRDocument.user_id == user_id)
    
    # Filter out soft-deleted documents unless include_deleted is True
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
    """
    Get list of OCR documents with optional filtering
    If user_id is provided, only return documents belonging to that user
    If include_deleted is False, filter out soft-deleted documents
    """
    query = db.query(OCRDocument)
    
    if user_id is not None:
        query = query.filter(OCRDocument.user_id == user_id)
    
    # Filter out soft-deleted documents unless include_deleted is True
    if not include_deleted:
        query = query.filter(OCRDocument.is_deleted == False)
    
    if ocr_mode:
        query = query.filter(OCRDocument.ocr_mode == ocr_mode)
    
    return query.order_by(OCRDocument.created_at.desc()).offset(skip).limit(limit).all()


def get_ocr_documents_by_filename(db: Session, filename: str, user_id: Optional[int] = None, include_deleted: bool = False) -> List[OCRDocument]:
    """
    Get OCR documents by filename
    If user_id is provided, only return documents belonging to that user
    If include_deleted is False, exclude soft-deleted documents
    """
    query = db.query(OCRDocument).filter(OCRDocument.filename.like(f"%{filename}%"))
    
    if user_id is not None:
        query = query.filter(OCRDocument.user_id == user_id)
    
    if not include_deleted:
        query = query.filter(OCRDocument.is_deleted == False)
    
    return query.all()


def delete_ocr_document(db: Session, document_id: int, user_id: Optional[int] = None, delete_from_storage: bool = False) -> bool:
    """
    Delete an OCR document by ID
    
    Args:
        db: Database session
        document_id: ID of document to delete
        user_id: If provided, only delete if document belongs to this user
        delete_from_storage: If True, permanently delete (hard delete - removes file and record)
                           If False, soft delete (marks as deleted, keeps file and record)
    
    Returns:
        bool: True if document was deleted, False otherwise
    """
    query = db.query(OCRDocument).filter(OCRDocument.id == document_id)
    
    if user_id is not None:
        query = query.filter(OCRDocument.user_id == user_id)
    
    document = query.first()
    if document:
        if delete_from_storage:
            # Hard delete: Remove physical file and database record
            if document.file_path:
                delete_uploaded_file(document.file_path)
            db.delete(document)
        else:
            # Soft delete: Mark as deleted, keep file and record
            document.is_deleted = True
        
        db.commit()
        return True
    return False


def get_documents_count(db: Session, user_id: Optional[int] = None, include_deleted: bool = False) -> int:
    """
    Get total count of OCR documents
    If user_id is provided, only count documents belonging to that user
    If include_deleted is False, exclude soft-deleted documents
    """
    query = db.query(OCRDocument)
    
    if user_id is not None:
        query = query.filter(OCRDocument.user_id == user_id)
    
    if not include_deleted:
        query = query.filter(OCRDocument.is_deleted == False)
    
    return query.count()


def get_average_confidence(db: Session, user_id: Optional[int] = None, include_deleted: bool = False) -> float:
    """
    Get average confidence across all documents
    If user_id is provided, only calculate for documents belonging to that user
    If include_deleted is False, exclude soft-deleted documents
    """
    from sqlalchemy import func
    query = db.query(func.avg(OCRDocument.confidence))
    
    if user_id is not None:
        query = query.filter(OCRDocument.user_id == user_id)
    
    if not include_deleted:
        query = query.filter(OCRDocument.is_deleted == False)
    
    result = query.scalar()
    return result if result else 0.0
