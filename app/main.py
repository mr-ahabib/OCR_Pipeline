"""Main FastAPI application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from fastapi.openapi.utils import get_openapi
import logging

from app.core.config import settings
from app.utils.logger import setup_file_logging
from app.api.v1.api import api_router
from app.db.init_db import init_db, create_initial_data
from app.errors.handlers import (
    validation_exception_handler,
    sqlalchemy_exception_handler,
    general_exception_handler
)

setup_file_logging(logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Advanced OCR system with authentication, authorization, and PostgreSQL storage",
    version=settings.PROJECT_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)


def custom_openapi():
    """Customize OpenAPI schema to use email instead of username in OAuth2"""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        description="Advanced OCR system with email-based authentication",
        routes=app.routes,
    )
    
    if "components" in openapi_schema:
        if "securitySchemes" in openapi_schema["components"]:
            if "OAuth2PasswordBearer" in openapi_schema["components"]["securitySchemes"]:
                openapi_schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["description"] = \
                    "OAuth2 password bearer authentication. Use your **email** and password to login."
    
    if "paths" in openapi_schema:
        if "/api/v1/auth/login" in openapi_schema["paths"]:
            if "post" in openapi_schema["paths"]["/api/v1/auth/login"]:
                login_endpoint = openapi_schema["paths"]["/api/v1/auth/login"]["post"]
                login_endpoint["summary"] = "Login with Email"
                login_endpoint["description"] = "Authenticate using **email** and password. Use this endpoint for the Swagger 'Authorize' button."
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def startup_event():
    """Initialize database and log application startup"""
    try:
        init_db()
        create_initial_data()
        logger.warning(f"{settings.PROJECT_NAME} STARTED - Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        logger.warning(f"{settings.PROJECT_NAME} STARTED - Database initialization failed, but API is running")


@app.on_event("shutdown")
async def shutdown_event():
    """Log application shutdown"""
    logger.warning(f"{settings.PROJECT_NAME} SHUTDOWN")


