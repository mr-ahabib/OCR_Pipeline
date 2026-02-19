"""File storage utilities"""
import os
import uuid
from pathlib import Path
from datetime import datetime
from app.core.config import settings


def generate_unique_filename(original_filename: str) -> str:
    """
    Generate a unique filename using timestamp and UUID
    Format: YYYYMMDD_HHMMSS_uuid_originalname
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    
    # Clean original filename and preserve extension
    name_parts = original_filename.rsplit('.', 1)
    if len(name_parts) == 2:
        name, ext = name_parts
        # Sanitize filename - remove special characters
        safe_name = "".join(c for c in name if c.isalnum() or c in ('-', '_'))[:50]
        unique_filename = f"{timestamp}_{unique_id}_{safe_name}.{ext}"
    else:
        safe_name = "".join(c for c in original_filename if c.isalnum() or c in ('-', '_'))[:50]
        unique_filename = f"{timestamp}_{unique_id}_{safe_name}"
    
    return unique_filename


def save_uploaded_file(file_content: bytes, original_filename: str) -> str:
    """
    Save uploaded file to disk and return the file path
    
    Args:
        file_content: The file content as bytes
        original_filename: Original filename from upload
        
    Returns:
        str: Relative path to saved file (e.g., 'app/uploads/20260219_123456_abc123_document.pdf')
    """
    # Ensure uploads directory exists
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    unique_filename = generate_unique_filename(original_filename)
    
    # Full path to save file
    file_path = upload_dir / unique_filename
    
    # Write file to disk
    with open(file_path, 'wb') as f:
        f.write(file_content)
    
    # Return relative path as string
    return str(file_path)


def delete_uploaded_file(file_path: str) -> bool:
    """
    Delete a file from disk
    
    Args:
        file_path: Path to the file to delete
        
    Returns:
        bool: True if file was deleted, False otherwise
    """
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception as e:
        # Log error but don't fail
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to delete file {file_path}: {str(e)}")
        return False


def get_file_size(file_path: str) -> int:
    """
    Get the size of a file in bytes
    
    Args:
        file_path: Path to the file
        
    Returns:
        int: File size in bytes, or 0 if file doesn't exist
    """
    try:
        if file_path and os.path.exists(file_path):
            return os.path.getsize(file_path)
        return 0
    except Exception:
        return 0
