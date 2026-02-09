from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import logging
import time
import json
from typing import Literal, Union, Dict, Any
from app.service import process_file, detect_file_type
from app.utils.logger import log_ocr_operation
from app.schema import OCRResponse

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
    
    return json_response


# Remove ocr_unified - endpoints will work independently with direct OCR processing


@router.post("/ocr/text")
async def ocr_plain_text(
    file: UploadFile = File(...),
    mode: Literal["bangla", "english", "mixed"] = Form("english"),
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
        
        return format_plain_text_response(result)
        
    except HTTPException as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR HTTP ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {e.detail}")
        raise
        
    except Exception as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR INTERNAL ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during OCR processing")


@router.post("/ocr/pages") 
async def ocr_page_by_page(
    file: UploadFile = File(...),
    mode: Literal["bangla", "english", "mixed"] = Form("english"),
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
        
        return format_page_by_page_response(result)
        
    except HTTPException as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR HTTP ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {e.detail}")
        raise
        
    except Exception as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR INTERNAL ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during OCR processing")


@router.post("/ocr/json", response_model=dict)
async def ocr_full_json(
    file: UploadFile = File(...),
    mode: Literal["bangla", "english", "mixed"] = Form("english"),
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
        
        return format_json_response(result)
        
    except HTTPException as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR HTTP ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {e.detail}")
        raise
        
    except Exception as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR INTERNAL ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during OCR processing")

