"""OCR service — Google Document AI, pipelined batch conversion + parallel dispatch.

Speed strategy for PDFs:
  1. Convert pages in batches of CONVERT_BATCH (8) using pdf2image at 200 DPI.
  2. Each batch is dispatched to DocAI IMMEDIATELY as it finishes converting,
     so DocAI processes pages 1-8 while pages 9-16 are still being converted.
  3. Up to MAX_PARALLEL (32) DocAI requests run concurrently.

Pipeline overlap for 46 pages:
  Batch 1 (p1-8)  → convert → dispatch ──────────────────► DocAI
  Batch 2 (p9-16) → convert ──────────────────────────────► DocAI  (overlap!)
  Batch 3 ...
  Total ≈ max(conversion_time, docai_time)  instead of  sum(both)
"""
import asyncio
import io
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

from PIL import Image
from pdf2image import convert_from_bytes

from app.ocr.google_docai_engine import run_docai_page, run_docai_image
from app.utils.logger import setup_file_logging, log_ocr_operation, log_performance_metrics
from app.utils.pdf_utils import count_pdf_pages

# ── setup ─────────────────────────────────────────────────────────────────────
setup_file_logging(logging.INFO)
logger = logging.getLogger(__name__)

# DPI for PDF → image conversion. 200 DPI gives good OCR quality while keeping
# JPEG sizes small enough for fast DocAI uploads (~80-150 KB/page).
PDF_DPI = int(os.getenv("OCR_PDF_DPI", 200))

# Max concurrent DocAI requests.  32 concurrent single-image requests keep
# the pipeline saturated without hitting quota limits.
MAX_PARALLEL = int(os.getenv("OCR_MAX_PARALLEL_PAGES", 32))

# Pages per conversion batch.  Each batch is converted then immediately
# dispatched to DocAI, overlapping conversion with network I/O.
CONVERT_BATCH = int(os.getenv("OCR_CONVERT_BATCH", 8))

# Thread-pool: used for both pdf2image conversion AND DocAI calls (blocking I/O).
_EXECUTOR = ThreadPoolExecutor(max_workers=int(os.getenv("OCR_MAX_CONVERSION_THREADS", 6)))


# ── helpers ───────────────────────────────────────────────────────────────────

def detect_file_type(file_bytes: bytes) -> str:
    """Detect file type based on magic bytes. Returns 'pdf', 'image', or 'unknown'."""
    if len(file_bytes) < 10:
        return 'unknown'
    if file_bytes.startswith(b'%PDF'):
        return 'pdf'
    if file_bytes.startswith(b'\xff\xd8\xff'):
        return 'image'
    if file_bytes.startswith(b'\x89PNG'):
        return 'image'
    if file_bytes.startswith(b'GIF87a') or file_bytes.startswith(b'GIF89a'):
        return 'image'
    if file_bytes.startswith(b'BM'):
        return 'image'
    if file_bytes.startswith(b'RIFF') and b'WEBP' in file_bytes[:12]:
        return 'image'
    if file_bytes.startswith(b'II*\x00') or file_bytes.startswith(b'MM\x00*'):
        return 'image'
    return 'unknown'


def _convert_page_range(pdf_bytes: bytes, first_page: int, last_page: int) -> List[bytes]:
    """
    Convert a specific page range (1-based, inclusive) to JPEG bytes.
    Uses pdf2image's first_page/last_page to avoid decoding the whole PDF.
    """
    images = convert_from_bytes(
        pdf_bytes,
        dpi=PDF_DPI,
        fmt="jpeg",
        grayscale=False,
        first_page=first_page,
        last_page=last_page,
        thread_count=int(os.getenv("OCR_MAX_CONVERSION_THREADS", 6)),
        use_pdftocairo=True,
        strict=False,
    )
    jpeg_list = []
    for img in images:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        jpeg_list.append(buf.getvalue())
    return jpeg_list


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Fast page count via pikepdf without rendering."""
    import pikepdf
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


# ── async workers ─────────────────────────────────────────────────────────────

async def _process_page(page_num: int, jpeg_bytes: bytes, sem: asyncio.Semaphore) -> dict:
    """Send one JPEG page to DocAI inside a semaphore slot."""
    async with sem:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_EXECUTOR, run_docai_page, jpeg_bytes, page_num)


async def _pipeline_pdf(pdf_bytes: bytes, total_pages: int) -> List[dict]:
    """
    Pipelined PDF processing:
      - Convert CONVERT_BATCH pages at a time in a thread-pool.
      - Dispatch each batch to DocAI immediately after conversion.
      - Conversion of the next batch overlaps with DocAI calls for the current batch.
    """
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(MAX_PARALLEL)
    all_tasks = []

    for batch_start in range(1, total_pages + 1, CONVERT_BATCH):
        batch_end = min(batch_start + CONVERT_BATCH - 1, total_pages)

        # Convert this batch (blocking, runs in thread pool)
        jpeg_batch: List[bytes] = await loop.run_in_executor(
            _EXECUTOR, _convert_page_range, pdf_bytes, batch_start, batch_end
        )
        logger.debug(
            f"Batch converted: pages {batch_start}-{batch_end} "
            f"({sum(len(j) for j in jpeg_batch)//1024}KB total)"
        )

        # Dispatch each page to DocAI immediately (non-blocking tasks)
        for i, jpeg in enumerate(jpeg_batch):
            page_num = batch_start + i
            all_tasks.append(asyncio.create_task(_process_page(page_num, jpeg, sem)))

    # Wait for all DocAI tasks (many are already done due to pipelining)
    results = await asyncio.gather(*all_tasks)
    results.sort(key=lambda p: p["page_number"])
    return results


# ── main entry point ──────────────────────────────────────────────────────────

async def process_file(file_bytes: bytes, langs: list, mode: str = "english"):
    """
    Process a file with Google Document AI.

    PDF  → pipeline: convert batches of 8 pages → dispatch immediately to DocAI
    Image → single DocAI image request

    Returns a structured result dict compatible with all existing endpoints.
    """
    start_time = time.time()
    file_size = len(file_bytes)

    try:
        file_type = detect_file_type(file_bytes)

        if file_size > 10 * 1024 * 1024:
            logger.warning(f"LARGE FILE - Type: {file_type}, Size: {file_size // 1024}KB")

        ENGINE = "Google Document AI"
        FEATURES = ["Native cloud OCR", "Automatic language detection", "Per-page extraction"]

        # ── PDF ───────────────────────────────────────────────────────────────
        if file_type == 'pdf':
            loop = asyncio.get_running_loop()
            total_pages: int = await loop.run_in_executor(_EXECUTOR, _count_pdf_pages, file_bytes)
            file_info = f"PDF ({total_pages} pages, {PDF_DPI} DPI, {file_size // 1024}KB)"
            logger.info(f"{file_info} → pipeline: batch={CONVERT_BATCH}, parallel={MAX_PARALLEL}")

            all_pages: List[dict] = await _pipeline_pdf(file_bytes, total_pages)

            texts = [p["text"] for p in all_pages]
            confs = [p["confidence"] for p in all_pages]
            avg_conf = sum(confs) / len(confs) if confs else 0.0

        # ── IMAGE ─────────────────────────────────────────────────────────────
        else:
            if file_type == 'unknown':
                logger.warning("Unknown file type — attempting to process as image")
            try:
                loop = asyncio.get_running_loop()
                img = await loop.run_in_executor(_EXECUTOR, lambda: Image.open(io.BytesIO(file_bytes)))
            except Exception as e:
                raise ValueError(f"Unsupported file format: {e}")

            file_info = f"Image (1 page, {file_size // 1024}KB)"
            text, conf = await loop.run_in_executor(_EXECUTOR, run_docai_image, img)
            all_pages = [{"page_number": 1, "text": text, "confidence": conf, "character_count": len(text)}]
            texts = [text]
            confs = [conf]
            avg_conf = conf

        # ── logging ───────────────────────────────────────────────────────────
        processing_time = time.time() - start_time
        if avg_conf < 80:
            logger.warning(f"LOW CONFIDENCE: {avg_conf:.2f}%")
        logger.info(f"OCR done: {len(all_pages)} pages in {processing_time:.1f}s (avg conf {avg_conf:.1f}%)")

        # ── build response ────────────────────────────────────────────────────
        if len(all_pages) == 1:
            result = {
                "text": texts[0] if texts else "",
                "confidence": avg_conf,
                "pages": 1,
                "languages": langs,
                "mode": mode,
                "engine": ENGINE,
                "features": FEATURES,
            }
        else:
            result = {
                "text": "\n\n".join(texts),
                "pages_data": all_pages,
                "confidence": avg_conf,
                "pages": len(all_pages),
                "languages": langs,
                "mode": mode,
                "engine": ENGINE,
                "features": FEATURES + ["Multi-page parallel processing"],
            }

        log_ocr_operation("COMPLETE", file_info, result)
        log_performance_metrics("OCR_PROCESSING", processing_time, len(all_pages), file_size)
        return result

    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"OCR processing failed: {str(e)}"
        logger.error(error_msg)
        log_ocr_operation("FAILED", f"File ({file_size // 1024}KB)", error=error_msg)
        log_performance_metrics("OCR_FAILED", processing_time, 0, file_size)
        raise
