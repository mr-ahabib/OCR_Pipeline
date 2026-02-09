from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.utils.logger import setup_file_logging
from endpoints.ocr_endpoints import router as ocr_router

# Initialize structured file logging for important events only
setup_file_logging(logging.INFO)  # Console shows INFO+, file shows WARNING+
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Robust OCR Engine",
    description="Advanced OCR system with multiple output formats and language support",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for web requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include OCR endpoints router
app.include_router(ocr_router, tags=["OCR"])

@app.on_event("startup")
async def startup_event():
    """Log application startup"""
    logger.warning("FastAPI OCR Engine STARTED - Multiple output formats available")

@app.on_event("shutdown")
async def shutdown_event():
    """Log application shutdown"""
    logger.warning("FastAPI OCR Engine SHUTDOWN")

