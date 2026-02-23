"""Application configuration"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Database Configuration
    DATABASE_USER = os.getenv("DATABASE_USER", "postgres")
    DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "123456")
    DATABASE_HOST = os.getenv("DATABASE_HOST", "localhost")
    DATABASE_PORT = os.getenv("DATABASE_PORT", "5432")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "OCR")
    
    @property
    def DATABASE_URL(self) -> str:
        """Construct PostgreSQL database URL"""
        return f"postgresql://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
    
    # Google Document AI Configuration (Optional)
    GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
    GOOGLE_LOCATION = os.getenv("GOOGLE_LOCATION", "us")
    GOOGLE_PROCESSOR_ID = os.getenv("GOOGLE_PROCESSOR_ID")

    # Google OAuth2 (Sign in with Google)
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    
    # OCR Performance Configuration
    OCR_MAX_PARALLEL_PAGES = int(os.getenv("OCR_MAX_PARALLEL_PAGES", max(1, min(4, (os.cpu_count() or 4)))))
    OCR_MAX_CONVERSION_THREADS = int(os.getenv("OCR_MAX_CONVERSION_THREADS", 4))
    OCR_ENGINE_MAX_WORKERS = int(os.getenv("OCR_ENGINE_MAX_WORKERS", max(2, min(8, (os.cpu_count() or 4)))))
    
    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "app/logs/logs.txt")
    
    # File Storage Configuration
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "app/uploads")
    
    # API Configuration
    # No global request timeout — large PDFs (up to 1000 pages) need unlimited time.
    MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", 500))
    
    # PayStation Payment Gateway
    PAYSTATION_MERCHANT_ID = os.getenv("PAYSTATION_MERCHANT_ID", "").strip()
    PAYSTATION_MERCHANT_PASSWORD = os.getenv("PAYSTATION_MERCHANT_PASSWORD", "").strip()
    PAYSTATION_API_URL = os.getenv("PAYSTATION_API_URL", "https://api.paystation.com.bd/initiate-payment")
    # Public base URL of this API (used to build callback_url)
    API_BASE_URL = os.getenv("API_BASE_URL")

    # Development/Production Settings
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    # Project Metadata
    PROJECT_NAME = "OCR Pipeline API"
    PROJECT_VERSION = "2.0.0"
    API_V1_STR = "/api/v1"
    
    # JWT Authentication
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production-min-32-chars")
    ALGORITHM = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))  # 7 days
    
    # Super Admin Configuration (Initial Setup)
    SUPER_ADMIN_USERNAME = os.getenv("SUPER_ADMIN_USERNAME", "admin")
    SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "admin@ocrpipeline.com")
    SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "SuperSecure@Admin123!")
    SUPER_ADMIN_FULL_NAME = os.getenv("SUPER_ADMIN_FULL_NAME", "Super Administrator")

    # SMTP / Email configuration
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.maileroo.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@doceanai.cloud")

    # OTP expiry (minutes)
    OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", 10))


settings = Settings()
