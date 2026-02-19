"""OCR API endpoints"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request, Header, Response
import logging
import time
from typing import Literal, Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session

from app.services.ocr_service import process_file, detect_file_type
from app.services.ocr_crud import create_ocr_document
from app.services.free_trial_service import (
    get_trial_user_info,
    generate_device_fingerprint,
    generate_cookie_id,
    update_cookie_consent
)
from app.utils.logger import log_ocr_operation
from app.utils.file_storage import save_uploaded_file
from app.utils.pdf_utils import count_pdf_pages
from app.middleware.auth import require_user, require_user_or_trial
from app.models.user import User
from app.models.free_trial_user import FreeTrialUser
from app.schemas.ocr_schemas import (
    OCRDocumentCreate,
    OCRDocumentResponse,
    OCRResponse
)
from app.schemas.free_trial_schemas import FreeTrialInfo, CookieConsentRequest
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
    user_id: int,
    filename: str,
    file_content: bytes,
    file_type: str, 
    file_size: int, 
    result: Dict[str, Any],
    processing_time: float
) -> OCRDocumentResponse:
    """
    Save OCR result to database and file to disk
    """
    try:
        # Save file to disk
        file_path = save_uploaded_file(file_content, filename)
        
        ocr_data = OCRDocumentCreate(
            user_id=user_id,
            filename=filename,
            file_path=file_path,
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
        logger.info(f"Saved OCR document to database: ID={db_document.id}, user_id={user_id}, filename={filename}, path={file_path}")
        
        return OCRDocumentResponse.from_orm(db_document)
    except Exception as e:
        logger.error(f"Failed to save OCR document to database: {str(e)}")
        # Don't fail the request if database save fails
        return None


@router.post("/pages") 
async def ocr_page_by_page(
    file: UploadFile = File(...),
    mode: Literal["bangla", "english", "mixed"] = Form("english"),
    save_to_db: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user)
):
    """OCR endpoint that returns formatted page-by-page text with detailed information (requires authentication)"""
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
            save_to_database(db, current_user.id, file.filename, content, file_type, len(content), result, request_duration)
        
        return format_page_by_page_response(result)
        
    except HTTPException as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR HTTP ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {e.detail}")
        raise
        
    except Exception as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR INTERNAL ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during OCR processing")


@router.post("/free-trial") 
async def ocr_free_trial(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    mode: Literal["bangla", "english", "mixed"] = Form("english"),
    db: Session = Depends(get_db)
):
    """
    OCR endpoint for free trial users (no authentication required)
    Allows 3 free OCR requests per DEVICE (not per browser)
    
    Automatically tracks usage via:
    - Device fingerprint (IP + Accept-Language, NOT User-Agent)
    - Secure HTTP-only cookie (if user accepts)
    
    Returns trial info automatically in response including remaining trials and messages.
    """
    request_start_time = time.time()
    
    try:
        # Get user or trial user and check limits
        # This automatically generates device fingerprint and handles cookies
        user_or_trial, trial_info, cookie_to_set, needs_cookie_consent = await require_user_or_trial(
            request=request,
            token=None,
            db=db
        )
        
        # Set cookie if needed (new user or cookie not present)
        if cookie_to_set:
            response.set_cookie(
                key="free_trial_id",
                value=cookie_to_set,
                max_age=365 * 24 * 60 * 60,  # 1 year
                httponly=True,
                samesite="lax",
                secure=False  # Set to True in production with HTTPS
            )
        
        # Determine if this is a registered user or trial user
        is_registered = isinstance(user_or_trial, User)
        user_id = user_or_trial.id if is_registered else None
        
        langs = OCR_MODES.get(mode, ["en"])
        content = await file.read()
        
        # Validate file size and content
        if len(content) == 0:
            logger.error(f"EMPTY FILE uploaded: {file.filename}")
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        
        # Stricter file size limit for free trial users (10MB)
        max_file_size = 50 * 1024 * 1024 if is_registered else 10 * 1024 * 1024
        if len(content) > max_file_size:
            size_limit = "50MB" if is_registered else "10MB"
            logger.error(f"FILE TOO LARGE: {file.filename} ({len(content)//1024//1024}MB)")
            raise HTTPException(
                status_code=413, 
                detail=f"File too large (max {size_limit} for {'registered users' if is_registered else 'free trial'})"
            )

        # Detect and validate file type
        file_type = detect_file_type(content)
        if file_type == 'unknown':
            logger.error(f"UNSUPPORTED FILE TYPE: {file.filename} - Content-Type: {file.content_type}")
            raise HTTPException(
                status_code=415, 
                detail="Unsupported file format. Please upload PDF, JPEG, PNG, GIF, BMP, WebP, or TIFF files."
            )

        # Enforce 3-page limit for free trial users
        FREE_TRIAL_MAX_PAGES = 3
        if not is_registered and file_type == 'pdf':
            try:
                page_count = count_pdf_pages(content)
                if page_count > FREE_TRIAL_MAX_PAGES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Free trial is limited to {FREE_TRIAL_MAX_PAGES} pages. "
                               f"Your PDF has {page_count} pages. "
                               f"Please register for an account to process larger documents."
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Could not count PDF pages for trial check: {e}")

        result = await process_file(content, langs, mode=mode)
        
        request_duration = time.time() - request_start_time
        
        # Log concerning results
        user_type = "registered" if is_registered else "trial"
        if result['confidence'] < 80 or request_duration > 10.0:
            logger.warning(
                f"OCR CONCERN ({user_type}) - File: {file.filename} ({file_type}) - "
                f"Duration: {request_duration:.2f}s - Confidence: {result['confidence']:.2f}%"
            )
        
        # Save to database for registered users only
        if is_registered:
            save_to_database(
                db, user_id, file.filename, content, 
                file_type, len(content), result, request_duration
            )
        
        # Build response with trial info
        response_data = format_page_by_page_response(result)
        
        # Add trial information for trial users - AUTOMATIC SYSTEM RESPONSE
        if not is_registered and trial_info:
            response_data["trial_info"] = {
                "usage_count": trial_info["usage_count"],
                "remaining": trial_info["remaining"],
                "message": trial_info["message"],
                "needs_cookie_consent": needs_cookie_consent
            }
        
        # Set cookie only if user has accepted (or will accept via frontend)
        # Frontend should call /cookie-consent endpoint before using trials
        if cookie_to_set and not needs_cookie_consent:
            response.set_cookie(
                key="free_trial_id",
                value=cookie_to_set,
                max_age=365 * 24 * 60 * 60,  # 1 year
                httponly=True,
                samesite="lax",
                secure=False  # Set to True in production with HTTPS
            )
        
        return response_data
        
    except HTTPException as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR HTTP ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {e.detail}")
        raise
        
    except Exception as e:
        request_duration = time.time() - request_start_time
        logger.error(f"OCR INTERNAL ERROR - File: {file.filename} - Duration: {request_duration:.2f}s - Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during OCR processing")


@router.post("/cookie-consent")
async def record_cookie_consent(
    consent_request: "CookieConsentRequest",
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Record user's cookie consent decision (accept or reject)
    
    This endpoint is called when the user responds to the cookie consent dialog.
    The consent decision is stored in the database along with the timestamp.
    """
    # Get device characteristics for fingerprinting
    client_ip = request.client.host if request.client else None
    accept_language = request.headers.get("Accept-Language")
    
    # Generate device fingerprint
    device_fingerprint = generate_device_fingerprint(
        ip_address=client_ip,
        accept_language=accept_language,
        screen_resolution=None
    )
    
    # Get cookie ID from request
    cookie_id = request.cookies.get("free_trial_id")
    
    if not cookie_id:
        raise HTTPException(
            status_code=400,
            detail="No cookie ID found. Please use the service first to get a cookie."
        )
    
    # Update cookie consent in database
    success = update_cookie_consent(
        db=db,
        device_fingerprint=device_fingerprint,
        cookie_id=cookie_id,
        consent_given=consent_request.consent_given
    )
    
    if success:
        consent_status = "accepted" if consent_request.consent_given else "rejected"
        return {
            "success": True,
            "message": f"Cookie consent {consent_status} and recorded successfully"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail="Trial user not found. Please use the free trial service first."
        )