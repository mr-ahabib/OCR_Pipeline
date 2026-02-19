"""Pydantic schemas for request/response validation"""
from app.schemas.ocr_schemas import (
    PageData,
    PlainTextResponse,
    PageByPageResponse,
    OCRResponse,
    OCRDocumentCreate,
    OCRDocumentResponse
)

__all__ = [
    "PageData",
    "PlainTextResponse",
    "PageByPageResponse",
    "OCRResponse",
    "OCRDocumentCreate",
    "OCRDocumentResponse"
]
