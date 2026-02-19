"""Database models"""
from app.models.ocr_document import OCRDocument
from app.models.user import User, UserRole

__all__ = ["OCRDocument", "User", "UserRole"]
