"""Initialize database tables and create initial data if needed"""
import logging
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.ocr_document import OCRDocument
from app.models.user import User, UserRole
from app.services.auth_service import get_password_hash
from app.core.config import settings

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Create all database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")
        raise


def create_initial_data() -> None:
    """Create initial super admin from .env configuration"""
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        
        if user_count == 0:
            super_user = User(
                username=settings.SUPER_ADMIN_USERNAME,
                email=settings.SUPER_ADMIN_EMAIL,
                full_name=settings.SUPER_ADMIN_FULL_NAME,
                hashed_password=get_password_hash(settings.SUPER_ADMIN_PASSWORD),
                role=UserRole.SUPER_USER,
                is_active=True,
                is_verified=True
            )
            db.add(super_user)
            db.commit()
            logger.info(f"Super admin created: {settings.SUPER_ADMIN_USERNAME}")
            logger.warning("Change default credentials in .env file!")
        
    except Exception as e:
        logger.error(f"Error creating initial data: {str(e)}")
        db.rollback()
    finally:
        db.close()
