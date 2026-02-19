"""Pydantic schemas for request/response validation"""
from app.schemas.ocr_schemas import (
    PageData,
    PlainTextResponse,
    PageByPageResponse,
    OCRResponse,
    OCRDocumentCreate,
    OCRDocumentResponse
)
from app.schemas.free_trial_schemas import (
    FreeTrialInfo,
    FreeTrialUserResponse,
    DeviceInfoRequest
)

__all__ = [
    "PageData",
    "PlainTextResponse",
    "PageByPageResponse",
    "OCRResponse",
    "OCRDocumentCreate",
    "OCRDocumentResponse",
    "FreeTrialInfo",
    "FreeTrialUserResponse",
    "DeviceInfoRequest"
]
