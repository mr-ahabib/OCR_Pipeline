import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Tesseract Configuration
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", "/usr/bin/tesseract")
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 90))

    # Google Document AI Configuration (Optional)
    GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
    GOOGLE_LOCATION = os.getenv("GOOGLE_LOCATION", "us")
    GOOGLE_PROCESSOR_ID = os.getenv("GOOGLE_PROCESSOR_ID")
    
    # OCR Performance Configuration
    OCR_MAX_PARALLEL_PAGES = int(os.getenv("OCR_MAX_PARALLEL_PAGES", max(1, min(4, (os.cpu_count() or 4)))))
    OCR_MAX_CONVERSION_THREADS = int(os.getenv("OCR_MAX_CONVERSION_THREADS", 4))
    OCR_ENGINE_MAX_WORKERS = int(os.getenv("OCR_ENGINE_MAX_WORKERS", max(2, min(8, (os.cpu_count() or 4)))))
    
    # OCR Quality & Accuracy Settings
    OCR_PDF_DPI = int(os.getenv("OCR_PDF_DPI", 600))
    OCRMYPDF_OVERSAMPLE_DPI = int(os.getenv("OCRMYPDF_OVERSAMPLE_DPI", 600))
    
    # Language-specific Configuration
    BANGLA_AGGRESSIVE_FILTERING = os.getenv("BANGLA_AGGRESSIVE_FILTERING", "true").lower() == "true"
    ENABLE_EASYOCR_BANGLA = os.getenv("ENABLE_EASYOCR_BANGLA", "true").lower() == "true"
    
    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "app/logs/logs.txt")
    
    # API Configuration
    MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", 50))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 300))
    
    # Development/Production Settings
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

settings = Settings()
