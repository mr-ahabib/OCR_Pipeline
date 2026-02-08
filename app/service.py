import asyncio
import logging
import io
import os
from PIL import Image
import numpy as np

from app.ocr.tesseract_engine import run_tesseract
from app.ocr.google_docai_engine import run_docai
from app.ocr.layout_engine import extract_layout_text
from app.utils.pdf_utils import pdf_to_images
from app.config import settings


# =====================================================
# Logging
# =====================================================

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# =====================================================
# Concurrency tuning
# =====================================================
MAX_PARALLEL_PAGES = int(os.getenv("OCR_MAX_PARALLEL_PAGES", max(1, min(4, (os.cpu_count() or 4)))))
MAX_CONVERSION_THREADS = int(os.getenv("OCR_MAX_CONVERSION_THREADS", 4))


# =====================================================
# Process single page - MAXIMUM ACCURACY
# =====================================================

def process_page(image, langs, raw_bytes, mode="english"):
    """
    Process a single page with multiple extraction strategies
    Performs up to 3 passes if needed to achieve best results:
    1. OCRmyPDF + Tesseract (primary)
    2. Multiple PSM modes and preprocessing (if confidence < 90)
    3. DocAI fallback (if confidence < threshold)
    
    Optimized for:
    - Mixed Bangla+English content
    - Multi-column layouts
    - Maximum accuracy
    - Mode-based language filtering
    """

    # Convert PIL Image to numpy array if needed
    if isinstance(image, Image.Image):
        img = np.array(image)
    else:
        img = image

    # -------------------------------------------------
    # PASS 1: OCRmyPDF + Tesseract (with multiple strategies)
    # -------------------------------------------------
    logger.info(f"Pass 1: OCRmyPDF + Tesseract (langs: {langs}, mode: {mode})")
    
    text, conf = run_tesseract(img, langs, use_ocrmypdf=True, mode=mode)
    
    logger.info(f"Pass 1 confidence: {conf:.2f}%")

    # -------------------------------------------------
    # PASS 2: Try without OCRmyPDF if confidence is low
    # -------------------------------------------------
    if conf < 90:
        logger.info(f"Pass 2: Raw Tesseract (no preprocessing, mode: {mode})")
        text2, conf2 = run_tesseract(img, langs, use_ocrmypdf=False, mode=mode)
        logger.info(f"Pass 2 confidence: {conf2:.2f}%")
        
        # Use better result
        if conf2 > conf:
            text, conf = text2, conf2
            logger.info("Using Pass 2 result")

    # -------------------------------------------------
    # PASS 3: DocAI fallback for very low confidence
    # -------------------------------------------------
    if conf < settings.CONFIDENCE_THRESHOLD:
        logger.warning(f"⚠️ Low confidence ({conf:.2f}%) → Pass 3: DocAI fallback")
        try:
            docai_text = run_docai(raw_bytes)
            logger.info("✅ DocAI used")
            return docai_text, 100.0
        except Exception as ex:
            logger.error(f"DocAI failed: {str(ex)}")
            logger.info("Returning best Tesseract result")
    
    return text, conf


# =====================================================
# Process file
# =====================================================

async def _process_single_page(idx, img, langs, raw_bytes, sem, mode):
    async with sem:
        logger.info(f"========== Page {idx} (Mode: {mode}) ==========")
        return idx, await asyncio.to_thread(process_page, img, langs, raw_bytes, mode)


async def process_file(file_bytes, langs, preserve_layout: bool = False, mode: str = "english"):
    """
    Process file with multi-strategy OCR asynchronously:
    - Automatic column detection
    - Multiple extraction passes per page
    - Best result selection from all attempts
    - Support for mixed Bangla+English text
    - Parallel page processing for faster throughput
    - Optional layout-preserving extraction (Detectron2 PubLayNet)
    - Mode-based language handling (bangla/english/mixed)
    """

    if preserve_layout:
        return await _process_file_with_layout(file_bytes, langs, mode)

    try:
        images = await asyncio.to_thread(
            pdf_to_images,
            file_bytes,
            langs,
            600,
            MAX_CONVERSION_THREADS,
        )
        logger.info(f"PDF detected → {len(images)} pages")
    except Exception:
        single_image = await asyncio.to_thread(Image.open, io.BytesIO(file_bytes))
        images = [single_image]
        logger.info("Single image detected")

    sem = asyncio.Semaphore(MAX_PARALLEL_PAGES)
    tasks = [
        asyncio.create_task(_process_single_page(i, img, langs, file_bytes, sem, mode))
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
    logger.info(f"Overall average confidence: {avg_conf:.2f}%")

    return {
        "text": "\n\n".join(texts),
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


async def _process_file_with_layout(file_bytes, langs, mode):
    """Layout-preserving pipeline using PubLayNet + EasyOCR per block."""

    try:
        images = await asyncio.to_thread(
            pdf_to_images,
            file_bytes,
            langs,
            400,
            MAX_CONVERSION_THREADS,
        )
        logger.info(f"PDF detected → {len(images)} pages (layout mode)")
    except Exception:
        single_image = await asyncio.to_thread(Image.open, io.BytesIO(file_bytes))
        images = [single_image]
        logger.info("Single image detected (layout mode)")

    layout_pages = []
    texts = []
    confs = []

    for idx, img in enumerate(images, 1):
        logger.info(f"========== Layout Page {idx} (Mode: {mode}) ===========")
        page_text, page_conf, blocks = await asyncio.to_thread(
            extract_layout_text,
            img,
            langs,
            mode,
        )

        texts.append(page_text)
        confs.append(page_conf)
        layout_pages.append({
            "page": idx,
            "confidence": page_conf,
            "blocks": blocks,
        })

    avg_conf = sum(confs) / len(confs) if confs else 0

    return {
        "text": "\n\n".join(texts),
        "confidence": avg_conf,
        "pages": len(images),
        "languages": langs,
        "mode": mode,
        "engine": f"Layout-aware: PubLayNet + EasyOCR ({mode} mode)",
        "features": [
            "PubLayNet layout detection",
            "Reading-order block OCR",
            "EasyOCR per block",
            f"Language filtering ({mode} mode)",
        ],
        "layout": layout_pages,
    }
