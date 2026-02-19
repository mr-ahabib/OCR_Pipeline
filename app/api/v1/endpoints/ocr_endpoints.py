"""OCR API endpoints"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
import logging
import time
from typing import Literal, Dict, Any, List
from sqlalchemy.orm import Session

from app.services.ocr_service import process_file, detect_file_type
from app.services.ocr_crud import create_ocr_document
from app.utils.logger import log_ocr_operation
from app.schemas.ocr_schemas import (
    OCRDocumentCreate,
    OCRDocumentResponse,
    OCRResponse
)
from app.core.dependencies import get_db

# Initialize router
router = APIRouter()
logger = logging.getLogger(__name__)

# Define OCR modes
OCR_MODES = {
    "bangla": ["bn"],
    "english": ["en"],
    "mixed": ["bn", "en"]
}


def format_plain_text_response(result: Dict[str, Any]) -> Dict[str, str]:
    """Format response for plain text output mode"""
    return {"text": result['text']}


def format_page_by_page_response(result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Format response for page-by-page text output mode with detailed page info"""
    
    if result.get('pages_data') and len(result.get('pages_data', [])) > 1:
        # Multi-page format with detailed information
        pages_info = []
        
        for page_data in result['pages_data']:
            page_info = {
                "page_number": page_data['page_number'],
                "confidence": round(page_data['confidence'], 2),
                "character_count": page_data['character_count'],
                "text": page_data['text']
            }
            pages_info.append(page_info)
        
        return {
            "pages_info": pages_info,
            "summary": {
                "total_pages": result['pages'],
                "average_confidence": round(result['confidence'], 2),
                "total_characters": sum(p['character_count'] for p in result['pages_data']),
                "processing_details": f"{result['pages']} pages processed with {result['confidence']:.2f}% average confidence"
            }
        }
    else:
        # Single page format
        return {
            "pages_info": [{
                "page_number": 1,
                "confidence": round(result['confidence'], 2),
                "character_count": len(result['text']),
                "text": result['text']
            }],
            "summary": {
                "total_pages": 1,
                "average_confidence": round(result['confidence'], 2),
                "total_characters": len(result['text']),
                "processing_details": f"1 page processed with {result['confidence']:.2f}% confidence"
            }
        }


def format_json_response(result: Dict[str, Any]) -> Dict[str, Any]:
    """Format response for JSON output mode with clean structured data"""
    
    # Create clean JSON response
    json_response = {
        "text": result['text'],
        "confidence": round(result['confidence'], 2),
        "pages": result['pages'],
        "languages": result['languages'],
        "mode": result['mode'],
        "engine": result['engine']
    }
    
    # Add page-by-page data if available
    if result.get('pages_data') and len(result.get('pages_data', [])) > 1:
        json_response["pages_data"] = []
        for page_data in result['pages_data']:
            page_json = {
                "page_number": page_data['page_number'],
                "text": page_data['text'],
                "confidence": round(page_data['confidence'], 2),
                "character_count": page_data['character_count']
            }
            json_response["pages_data"].append(page_json)
    
    return json_response


def save_to_database(
    db: Session, 
    filename: str, 
    file_type: str, 
    file_size: int, 
    result: Dict[str, Any],
    processing_time: float
) -> OCRDocumentResponse:
    """
    Save OCR result to database
    """
    try:
        ocr_data = OCRDocumentCreate(
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            ocr_mode=result['mode'],
            ocr_engine=result['engine'],
            languages=result['languages'],
            extracted_text=result['text'],
            confidence=result['confidence'],
            total_pages=result['pages'],
            pages_data=result.get('pages_data'),
            processing_time=processing_time,
            character_count=len(result['text'])
        )
        
        db_document = create_ocr_document(db, ocr_data)
        logger.info(f"Saved OCR document to database: ID={db_document.id}, filename={filename}")
        
        return OCRDocumentResponse.from_orm(db_document)
    except Exception as e:
        logger.error(f"Failed to save OCR document to database: {str(e)}")
        # Don't fail the request if database save fails
        return None


@router.post("/text")
async def ocr_plain_text(
    file: UploadFile = File(...),
    mode: Literal["bangla", "english", "mixed"] = Form("english"),
    save_to_db: bool = Form(False),
    db: Session = Depends(get_db)
):
    """OCR endpoint that returns only plain text"""
    request_start_time = time.time()
    
    try:
        langs = OCR_MODES.get(mode, ["en"])
        content = await file.read()
        
        # Validate file size and content
        if len(content) == 0:
            logger.error(f"EMPTY FILE uploaded: {file.filename}")
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        
        if len(content) > 50 * 1024 * 1024:  # 50MB limit
            logger.error(f"FILE TOO LARGE: {file.filename} ({len(content)//1024//1024}MB)")
            raise HTTPException(status_code=413, detail="File too large (max 50MB)")

        # Detect and validate file type
        file_type = detect_file_type(content)
        if file_type == 'unknown':
            logger.error(f"UNSUPPORTED FILE TYPE: {file.filename} - Content-Type: {file.content_type}")
            raise HTTPException(
                status_code=415, 
                detail="Unsupported file format. Please upload PDF, JPEG, PNG, GIF, BMP, WebP, or TIFF files."
            )

        result = await process_file(content, langs, mode=mode)
        
        request_duration = time.time() - request_start_time
        
        # Log concerning results (low confidence or slow processing)
        if result['confidence'] < 80 or request_duration > 10.0:
            logger.warning(f"OCR CONCERN - File: {file.filename} ({file_type}) - Duration: {request_duration:.2f}s - Confidence: {result['confidence']:.2f}%")
        
        # Save to database if requested
        if save_to_db:
            save_to_database(db, file.filename, file_type, len(content), result, request_duration)
        
        return format_plain_text_response(result)
        
    except HTTPException as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR HTTP ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {e.detail}")
        raise
        
    except Exception as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR INTERNAL ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during OCR processing")


@router.post("/pages") 
async def ocr_page_by_page(
    file: UploadFile = File(...),
    mode: Literal["bangla", "english", "mixed"] = Form("english"),
    save_to_db: bool = Form(False),
    db: Session = Depends(get_db)
):
    """OCR endpoint that returns formatted page-by-page text with detailed information"""
    request_start_time = time.time()
    
    try:
        langs = OCR_MODES.get(mode, ["en"])
        content = await file.read()
        
        # Validate file size and content
        if len(content) == 0:
            logger.error(f"EMPTY FILE uploaded: {file.filename}")
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        
        if len(content) > 50 * 1024 * 1024:  # 50MB limit
            logger.error(f"FILE TOO LARGE: {file.filename} ({len(content)//1024//1024}MB)")
            raise HTTPException(status_code=413, detail="File too large (max 50MB)")

        # Detect and validate file type
        file_type = detect_file_type(content)
        if file_type == 'unknown':
            logger.error(f"UNSUPPORTED FILE TYPE: {file.filename} - Content-Type: {file.content_type}")
            raise HTTPException(
                status_code=415, 
                detail="Unsupported file format. Please upload PDF, JPEG, PNG, GIF, BMP, WebP, or TIFF files."
            )

        result = await process_file(content, langs, mode=mode)
        
        request_duration = time.time() - request_start_time
        
        # Log concerning results (low confidence or slow processing)
        if result['confidence'] < 80 or request_duration > 10.0:
            logger.warning(f"OCR CONCERN - File: {file.filename} ({file_type}) - Duration: {request_duration:.2f}s - Confidence: {result['confidence']:.2f}%")
        
        # Save to database if requested
        if save_to_db:
            save_to_database(db, file.filename, file_type, len(content), result, request_duration)
        
        return format_page_by_page_response(result)
        
    except HTTPException as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR HTTP ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {e.detail}")
        raise
        
    except Exception as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR INTERNAL ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during OCR processing")


@router.post("/json", response_model=dict)
async def ocr_full_json(
    file: UploadFile = File(...),
    mode: Literal["bangla", "english", "mixed"] = Form("english"),
    save_to_db: bool = Form(True),  # Default to True for JSON endpoint
    db: Session = Depends(get_db)
):
    """OCR endpoint that returns fully structured JSON with comprehensive metadata"""
    request_start_time = time.time()
    
    try:
        langs = OCR_MODES.get(mode, ["en"])
        content = await file.read()
        
        # Validate file size and content
        if len(content) == 0:
            logger.error(f"EMPTY FILE uploaded: {file.filename}")
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        
        if len(content) > 50 * 1024 * 1024:  # 50MB limit
            logger.error(f"FILE TOO LARGE: {file.filename} ({len(content)//1024//1024}MB)")
            raise HTTPException(status_code=413, detail="File too large (max 50MB)")

        # Detect and validate file type
        file_type = detect_file_type(content)
        if file_type == 'unknown':
            logger.error(f"UNSUPPORTED FILE TYPE: {file.filename} - Content-Type: {file.content_type}")
            raise HTTPException(
                status_code=415, 
                detail="Unsupported file format. Please upload PDF, JPEG, PNG, GIF, BMP, WebP, or TIFF files."
            )

        result = await process_file(content, langs, mode=mode)
        
        request_duration = time.time() - request_start_time
        
        # Log concerning results (low confidence or slow processing)
        if result['confidence'] < 80 or request_duration > 10.0:
            logger.warning(f"OCR CONCERN - File: {file.filename} ({file_type}) - Duration: {request_duration:.2f}s - Confidence: {result['confidence']:.2f}%")
        
        # Save to database if requested
        if save_to_db:
            save_to_database(db, file.filename, file_type, len(content), result, request_duration)
        
        return format_json_response(result)
        
    except HTTPException as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR HTTP ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {e.detail}")
        raise
        
    except Exception as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR INTERNAL ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during OCR processing")
