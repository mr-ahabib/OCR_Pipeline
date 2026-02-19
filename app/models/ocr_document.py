"""OCR Document database model"""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.sql import func
from app.db.base import Base


class OCRDocument(Base):
    """
    Database model for storing OCR processed documents
    """
    __tablename__ = "ocr_documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # Owner of the document
    filename = Column(String(255), nullable=False, index=True)
    file_path = Column(String(512), nullable=True, index=True)  # Path to saved file on disk
    file_type = Column(String(50), nullable=False)  # pdf, image
    file_size = Column(Integer, nullable=False)  # in bytes
    
    # OCR Processing details
    ocr_mode = Column(String(50), nullable=False)  # bangla, english, mixed
    ocr_engine = Column(String(255), nullable=False)
    languages = Column(JSON, nullable=False)  # List of languages used
    
    # OCR Results
    extracted_text = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    total_pages = Column(Integer, nullable=False, default=1)
    pages_data = Column(JSON, nullable=True)  # Page-by-page results for multi-page docs
    
    # Processing metadata
    processing_time = Column(Float, nullable=True)  # in seconds
    character_count = Column(Integer, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)  # Soft delete flag
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    def __repr__(self):
        return f"<OCRDocument(id={self.id}, filename='{self.filename}', confidence={self.confidence})>"
