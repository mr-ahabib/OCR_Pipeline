"""API v1 router aggregation"""
from fastapi import APIRouter
from app.api.v1.endpoints import ocr_endpoints, document_endpoints, auth_endpoints, super_user_api

api_router = APIRouter()

api_router.include_router(auth_endpoints.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(super_user_api.router, prefix="/super-user", tags=["Super User"])
api_router.include_router(ocr_endpoints.router, prefix="/ocr", tags=["OCR"])
api_router.include_router(document_endpoints.router, prefix="/documents", tags=["Documents"])
