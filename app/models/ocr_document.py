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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False, index=True)
    file_path = Column(String(512), nullable=True, index=True)
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer, nullable=False)
    
    ocr_mode = Column(String(50), nullable=False)
    ocr_engine = Column(String(255), nullable=False)
    languages = Column(JSON, nullable=False)
    
    extracted_text = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    total_pages = Column(Integer, nullable=False, default=1)
    pages_data = Column(JSON, nullable=True)
    
    processing_time = Column(Float, nullable=True)
    character_count = Column(Integer, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    def __repr__(self):
        return f"<OCRDocument(id={self.id}, filename='{self.filename}', confidence={self.confidence})>"
