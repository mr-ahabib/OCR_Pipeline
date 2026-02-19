"""OCR service - Business logic for OCR processing"""
import asyncio
import logging
import io
import os
import time
from PIL import Image
import numpy as np

from app.ocr.tesseract_engine import run_tesseract
from app.ocr.google_docai_engine import run_docai
from app.utils.pdf_utils import pdf_to_images
from app.utils.logger import setup_file_logging, log_ocr_operation, log_performance_metrics
from app.core.config import settings


def detect_file_type(file_bytes: bytes) -> str:
    """
    Detect file type based on file signature/magic bytes
    Returns: 'pdf', 'image', or 'unknown'
    """
    if len(file_bytes) < 10:
        return 'unknown'
    
    # PDF signature
    if file_bytes.startswith(b'%PDF'):
        return 'pdf'
    
    # Common image signatures
    if file_bytes.startswith(b'\xff\xd8\xff'):  # JPEG
        return 'image'
    if file_bytes.startswith(b'\x89PNG'):  # PNG
        return 'image'  
    if file_bytes.startswith(b'GIF87a') or file_bytes.startswith(b'GIF89a'):  # GIF
        return 'image'
    if file_bytes.startswith(b'BM'):  # BMP
        return 'image'
    if file_bytes.startswith(b'RIFF') and b'WEBP' in file_bytes[:12]:  # WebP
        return 'image'
    if file_bytes.startswith(b'II*\x00') or file_bytes.startswith(b'MM\x00*'):  # TIFF
        return 'image'
    
    return 'unknown'


# Initialize structured file logging for important events only
setup_file_logging(logging.INFO)  # Console shows INFO+, file shows WARNING+ 
logger = logging.getLogger(__name__)

MAX_PARALLEL_PAGES = int(os.getenv("OCR_MAX_PARALLEL_PAGES", max(1, min(4, (os.cpu_count() or 4)))))
MAX_CONVERSION_THREADS = int(os.getenv("OCR_MAX_CONVERSION_THREADS", 4))


def process_page(image, langs, raw_bytes, mode="english", use_ocrmypdf=True):
    """
    Process a single page with multiple extraction strategies
    Performs up to 3 passes if needed to achieve best results:
    1. OCRmyPDF + Tesseract (primary, if use_ocrmypdf=True)
    2. Multiple PSM modes and preprocessing (if confidence < 90)
    3. DocAI fallback (if confidence < threshold)
    
    Optimized for:
    - Mixed Bangla+English content
    - Multi-column layouts
    - Maximum accuracy
    - Mode-based language filtering
    - Fast processing for images (skips OCRmyPDF when not needed)
    
    ENHANCED: Better logging for Bangla text extraction debugging
    """

    # Convert PIL Image to numpy array if needed
    if isinstance(image, Image.Image):
        img = np.array(image)
    else:
        img = image

    
    text, conf = run_tesseract(img, langs, use_ocrmypdf=use_ocrmypdf, mode=mode)
    
    # Log if Bangla mode and text seems empty
    if mode == "bangla" and len(text.strip()) < 10:
        logger.warning(f"BANGLA MODE: Very little text extracted in Pass 1 ({len(text)} chars, conf={conf:.2f}%)")

    if conf < 90:
        logger.warning(f"LOW confidence Pass 1 ({conf:.2f}%) - trying raw Tesseract")
        text2, conf2 = run_tesseract(img, langs, use_ocrmypdf=False, mode=mode)
        
        # Use better result
        if conf2 > conf:
            text, conf = text2, conf2


    if conf < settings.CONFIDENCE_THRESHOLD:
        logger.warning(f"CRITICAL: Very low confidence ({conf:.2f}%) - using DocAI fallback")
        try:
            docai_text = run_docai(raw_bytes)
            logger.warning("DocAI fallback completed successfully")
            return docai_text, 100.0
        except Exception as ex:
            logger.error(f"DocAI FAILED: {str(ex)}")
    
    # Log final low confidence results
    if conf < 90:
        logger.warning(f"FINAL RESULT has low confidence: {conf:.2f}%")
    
    return text, conf


# =====================================================
# Process file
# =====================================================

async def _process_single_page(idx, img, langs, raw_bytes, sem, mode, use_ocrmypdf):
    async with sem:
        # Only log page processing for large documents
        if idx == 1:  # Log once for first page only
            return idx, await asyncio.to_thread(process_page, img, langs, raw_bytes, mode, use_ocrmypdf)
        else:
            return idx, await asyncio.to_thread(process_page, img, langs, raw_bytes, mode, use_ocrmypdf)


async def process_file(file_bytes, langs, mode: str = "english"):
    """
    Process file with multi-strategy OCR asynchronously:
    - Automatic file type detection (PDF vs Image)
    - Automatic column detection
    - Multiple extraction passes per page
    - Best result selection from all attempts
    - Support for mixed Bangla+English text
    - Parallel page processing for faster throughput
    - Mode-based language handling (bangla/english/mixed)
    """
    start_time = time.time()
    file_size = len(file_bytes)
    
    try:
        # Detect file type first to avoid unnecessary PDF conversion attempts
        file_type = detect_file_type(file_bytes)
        
        # Only log large files or potential issues
        if file_size > 10 * 1024 * 1024:  # Only log files larger than 10MB
            logger.warning(f"LARGE FILE Processing - Type: {file_type} - Mode: {mode} - Languages: {langs} - File size: {file_size//1024}KB")
        
        # Process based on detected file type
        if file_type == 'pdf':
            try:
                images = await asyncio.to_thread(
                    pdf_to_images,
                    file_bytes,
                    langs,
                    600,
                    MAX_CONVERSION_THREADS,
                )
                file_info = f"PDF ({len(images)} pages, {file_size//1024}KB)"
                # Only log if many pages
                if len(images) > 10:
                    logger.warning(f"LARGE PDF detected → {len(images)} pages")
                use_ocrmypdf = True  # Use OCRmyPDF for PDFs
            except Exception as e:
                logger.error(f"PDF processing failed: {str(e)}")
                # Try as image if PDF processing fails
                single_image = await asyncio.to_thread(Image.open, io.BytesIO(file_bytes))
                images = [single_image]
                file_info = f"PDF-fallback-Image (1 page, {file_size//1024}KB)"
                use_ocrmypdf = False  # Skip OCRmyPDF for images (faster)
                
        elif file_type == 'image':
            # Process directly as image - no PDF conversion attempt
            single_image = await asyncio.to_thread(Image.open, io.BytesIO(file_bytes))
            images = [single_image]
            file_info = f"Image (1 page, {file_size//1024}KB)"
            use_ocrmypdf = False  # Skip OCRmyPDF for images (faster)
            
        else:
            # Unknown file type - try both approaches
            logger.warning(f"Unknown file type detected - attempting processing")
            try:
                # Try PDF first
                images = await asyncio.to_thread(
                    pdf_to_images,
                    file_bytes,
                    langs,
                    600,
                    MAX_CONVERSION_THREADS,
                )
                file_info = f"Unknown-PDF ({len(images)} pages, {file_size//1024}KB)"
                use_ocrmypdf = True
            except Exception:
                # Fall back to image
                try:
                    single_image = await asyncio.to_thread(Image.open, io.BytesIO(file_bytes))
                    images = [single_image]
                    file_info = f"Unknown-Image (1 page, {file_size//1024}KB)"
                    use_ocrmypdf = False
                except Exception as e:
                    logger.error(f"Unable to process file as PDF or Image: {str(e)}")
                    raise ValueError("Unsupported file format")

        sem = asyncio.Semaphore(MAX_PARALLEL_PAGES)
        tasks = [
            asyncio.create_task(_process_single_page(i, img, langs, file_bytes, sem, mode, use_ocrmypdf))
            for i, img in enumerate(images, 1)
        ]

        results = await asyncio.gather(*tasks)

        # Maintain order by page index
        results_sorted = sorted(results, key=lambda x: x[0])
        texts = []
        confs = []

        for _, (page_text, page_conf) in results_sorted:
            texts.append(page_text)
            confs.append(page_conf)

        avg_conf = sum(confs) / len(confs) if confs else 0
        processing_time = time.time() - start_time
        
        # Only log if confidence is concerning or processing was slow
        if avg_conf < 80:
            logger.warning(f"LOW CONFIDENCE result: {avg_conf:.2f}%")
        if processing_time > (5.0 if len(images) == 1 else 10.0):
            logger.warning(f"SLOW PROCESSING: {processing_time:.2f} seconds for {len(images)} pages")

        # Build response based on number of pages
        if len(images) == 1:
            # Single page - return text directly
            result = {
                "text": texts[0] if texts else "",
                "confidence": avg_conf,
                "pages": len(images),
                "languages": langs,
                "mode": mode,
                "engine": f"Multi-strategy: OCRmyPDF + Tesseract ({mode} mode)",
                "features": [
                    "Multi-column detection",
                    "Multiple PSM modes",
                    "Image enhancement variants",
                    f"Language filtering ({mode} mode)"
                ]
            }
        else:
            # Multi-page PDF - return page-by-page results
            pages_data = []
            for i, (text, conf) in enumerate(zip(texts, confs), 1):
                pages_data.append({
                    "page_number": i,
                    "text": text,
                    "confidence": conf,
                    "character_count": len(text)
                })
            
            result = {
                "text": "\n\n".join(texts),  # Combined text for compatibility
                "pages_data": pages_data,  # Individual page results
                "confidence": avg_conf,
                "pages": len(images),
                "languages": langs,
                "mode": mode,
                "engine": f"Multi-strategy: OCRmyPDF + Tesseract ({mode} mode)",
                "features": [
                    "Multi-column detection",
                    "Multiple PSM modes", 
                    "Image enhancement variants",
                    f"Language filtering ({mode} mode)",
                    "Page-by-page OCR results"
                ]
            }
        
        # Log successful OCR operation
        log_ocr_operation("COMPLETE", file_info, result)
        log_performance_metrics("OCR_PROCESSING", processing_time, len(images), file_size)
        
        return result
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"OCR processing failed: {str(e)}"
        logger.error(error_msg)
        
        # Log failed OCR operation
        log_ocr_operation("FAILED", f"File ({file_size//1024}KB)", error=error_msg)
        log_performance_metrics("OCR_FAILED", processing_time, 0, file_size)
        
        # Re-raise the exception to be handled by the API
        raise
