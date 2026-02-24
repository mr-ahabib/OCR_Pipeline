"""API v1 router aggregation"""
from fastapi import APIRouter
from app.api.v1.endpoints import ocr_endpoints, document_endpoints, auth_endpoints, super_user_api
from app.api.v1.endpoints import subscription_endpoints
from app.api.v1.endpoints import payment_endpoints
from app.api.v1.endpoints import enterprise_endpoints

api_router = APIRouter()

api_router.include_router(auth_endpoints.router,        prefix="/auth",        tags=["Authentication"])
api_router.include_router(super_user_api.router,        prefix="/super-user",  tags=["Super User"])
api_router.include_router(ocr_endpoints.router,         prefix="/ocr",         tags=["OCR"])
api_router.include_router(document_endpoints.router,    prefix="/documents",   tags=["Documents"])
api_router.include_router(subscription_endpoints.router,prefix="/subscription",tags=["Subscription"])
api_router.include_router(payment_endpoints.router,     prefix="/payment",     tags=["Payment"])
api_router.include_router(enterprise_endpoints.router,  prefix="/enterprise",  tags=["Enterprise"])
