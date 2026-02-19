"""CRUD operations for OCR documents"""
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.ocr_document import OCRDocument
from app.schemas.ocr_schemas import OCRDocumentCreate


def create_ocr_document(db: Session, ocr_data: OCRDocumentCreate) -> OCRDocument:
    """
    Create a new OCR document record in the database
    """
    db_document = OCRDocument(
        filename=ocr_data.filename,
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


def get_ocr_document(db: Session, document_id: int) -> Optional[OCRDocument]:
    """
    Get an OCR document by ID
    """
    return db.query(OCRDocument).filter(OCRDocument.id == document_id).first()


def get_ocr_documents(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    ocr_mode: Optional[str] = None
) -> List[OCRDocument]:
    """
    Get list of OCR documents with optional filtering
    """
    query = db.query(OCRDocument)
    
    if ocr_mode:
        query = query.filter(OCRDocument.ocr_mode == ocr_mode)
    
    return query.order_by(OCRDocument.created_at.desc()).offset(skip).limit(limit).all()


def get_ocr_documents_by_filename(db: Session, filename: str) -> List[OCRDocument]:
    """
    Get OCR documents by filename
    """
    return db.query(OCRDocument).filter(OCRDocument.filename.like(f"%{filename}%")).all()


def delete_ocr_document(db: Session, document_id: int) -> bool:
    """
    Delete an OCR document by ID
    """
    document = db.query(OCRDocument).filter(OCRDocument.id == document_id).first()
    if document:
        db.delete(document)
        db.commit()
        return True
    return False


def get_documents_count(db: Session) -> int:
    """
    Get total count of OCR documents
    """
    return db.query(OCRDocument).count()


def get_average_confidence(db: Session) -> float:
    """
    Get average confidence across all documents
    """
    from sqlalchemy import func
    result = db.query(func.avg(OCRDocument.confidence)).scalar()
    return result if result else 0.0
