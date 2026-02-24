"""OCR service — engine selection, Google Document AI pipeline, and Mistral OCR.

Engine routing
--------------
  Mistral OCR (premium, structure-preserving)
      • UserRole.SUPER_USER
      • UserRole.ADMIN
      • Regular USER with an active subscription

  Google Document AI (fast, high-volume)
      • Regular USER on free tier (no subscription)
      • Free-trial users (no account)
      • Any unauthenticated caller

DocAI speed strategy for PDFs:
  1. Convert pages at 300 DPI (grayscale) — 3× smaller than RGB for the same
     quality, keeping DocAI uploads fast while preserving accuracy for complex
     scripts such as Bangla.
  2. Batches of CONVERT_BATCH (4) pages are dispatched to DocAI IMMEDIATELY
     after conversion — smaller batches mean earlier dispatch and tighter
     pipeline overlap.
  3. Up to MAX_PARALLEL (50) DocAI requests run concurrently.

Mistral strategy for PDFs:
  Entire PDF is sent as a single base64-encoded document in one API call.
  Mistral natively handles multi-page PDFs, extracts tables as HTML,
  equations as LaTeX/markdown, and embeds figures inline as base64 images.
"""
import asyncio
import io
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Union

from PIL import Image
from pdf2image import convert_from_bytes

from app.ocr.google_docai_engine import run_docai_page, run_docai_image
from app.ocr.mistral_ocr_engine import run_mistral_ocr
from app.utils.logger import setup_file_logging, log_ocr_operation, log_performance_metrics
from app.utils.pdf_utils import count_pdf_pages

# ── setup ─────────────────────────────────────────────────────────────────────
setup_file_logging(logging.INFO)
logger = logging.getLogger(__name__)

# DPI for PDF → image conversion.
# 300 DPI is the standard high-accuracy DPI for OCR — essential for complex
# scripts like Bangla. Grayscale mode (below) offsets the larger file size so
# uploads to DocAI remain fast (~60-120 KB/page as grayscale JPEG).
PDF_DPI = int(os.getenv("OCR_PDF_DPI", 300))

# Max concurrent DocAI requests.  50 concurrent requests keep the pipeline
# fully saturated at higher DPI without hitting quota limits.
MAX_PARALLEL = int(os.getenv("OCR_MAX_PARALLEL_PAGES", 50))

# Pages per conversion batch.  Smaller batches (4) dispatch to DocAI sooner,
# maximising pipeline overlap between conversion and network I/O.
CONVERT_BATCH = int(os.getenv("OCR_CONVERT_BATCH", 4))

# Thread-pool: use all available CPU cores for conversion; cap at 16.
_CONVERSION_THREADS = int(os.getenv("OCR_MAX_CONVERSION_THREADS", min(os.cpu_count() or 8, 16)))
_EXECUTOR = ThreadPoolExecutor(max_workers=_CONVERSION_THREADS)

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
        grayscale=True,   # Grayscale at 300 DPI ≈ same file size as RGB at 150 DPI
        first_page=first_page,
        last_page=last_page,
        thread_count=_CONVERSION_THREADS,
        use_pdftocairo=True,
        strict=False,
    )
    jpeg_list = []
    for img in images:
        if img.mode not in ("RGB", "L"):
            img = img.convert("L")  # keep grayscale
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        jpeg_list.append(buf.getvalue())
    return jpeg_list


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Fast page count via pikepdf without rendering."""
    import pikepdf
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


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

async def process_file(file_bytes: bytes, langs: list, mode: str = "english",
                       user_id: Optional[int] = None, user_email: Optional[str] = None):
    """
    Process a file with Google Document AI.

    PDF  → pipeline: convert batches of 4 pages (grayscale 300 DPI) → dispatch immediately to DocAI
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

        if file_type == 'pdf':
            loop = asyncio.get_running_loop()
            total_pages: int = await loop.run_in_executor(_EXECUTOR, _count_pdf_pages, file_bytes)
            file_info = f"PDF ({total_pages} pages, {PDF_DPI} DPI, {file_size // 1024}KB)"
            logger.info(f"{file_info} → pipeline: batch={CONVERT_BATCH}, parallel={MAX_PARALLEL}")

            all_pages: List[dict] = await _pipeline_pdf(file_bytes, total_pages)

            texts = [p["text"] for p in all_pages]
            confs = [p["confidence"] for p in all_pages]
            avg_conf = sum(confs) / len(confs) if confs else 0.0

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

        processing_time = time.time() - start_time
        if avg_conf < 80:
            logger.warning(f"LOW CONFIDENCE: {avg_conf:.2f}%")
        logger.info(f"OCR done: {len(all_pages)} pages in {processing_time:.1f}s (avg conf {avg_conf:.1f}%)")

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

        log_ocr_operation("COMPLETE", file_info, result,
                           user_id=user_id, user_email=user_email)
        log_performance_metrics("OCR_PROCESSING", processing_time, len(all_pages), file_size)
        return result

    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"OCR processing failed: {str(e)}"
        logger.error(error_msg)
        log_ocr_operation("FAILED", f"File ({file_size // 1024}KB)", error=error_msg,
                           user_id=user_id, user_email=user_email)
        log_performance_metrics("OCR_FAILED", processing_time, 0, file_size)
        raise


# ── language detection ────────────────────────────────────────────────────────

# Map langdetect codes to human-readable names for the "mode" field.
_LANG_NAMES: dict[str, str] = {
    "en": "english",
    "bn": "bangla",
    "ar": "arabic",
    "zh-cn": "chinese (simplified)",
    "zh-tw": "chinese (traditional)",
    "fr": "french",
    "de": "german",
    "hi": "hindi",
    "id": "indonesian",
    "it": "italian",
    "ja": "japanese",
    "ko": "korean",
    "ms": "malay",
    "nl": "dutch",
    "pl": "polish",
    "pt": "portuguese",
    "ru": "russian",
    "es": "spanish",
    "sv": "swedish",
    "th": "thai",
    "tr": "turkish",
    "uk": "ukrainian",
    "ur": "urdu",
    "vi": "vietnamese",
}


def detect_language(text: str) -> tuple[list[str], str]:
    """Auto-detect the language(s) in *text* using langdetect.

    Supports 55+ languages.  When multiple languages are detected with
    significant probability (>= 0.20), all are reported and mode is
    ``"mixed"``.

    Returns:
        ``(langs_list, mode_string)`` e.g.
        ``(["en"], "english")``,
        ``(["bn"], "bangla")``,
        ``(["en", "fr"], "mixed")``.

    Falls back to ``(["en"], "english")`` on very short or empty text.
    """
    if not text or len(text.strip()) < 10:
        return ["en"], "english"

    try:
        from langdetect import detect_langs
        from langdetect.lang_detect_exception import LangDetectException

        probs = detect_langs(text)  # list of Language(lang, prob)

        # Collect all languages with >= 20 % probability
        significant = [p for p in probs if p.prob >= 0.20]
        if not significant:
            significant = probs[:1]  # fall back to top result

        langs = [p.lang for p in significant]

        if len(langs) == 1:
            mode = _LANG_NAMES.get(langs[0], langs[0])
        else:
            mode = "mixed"

        return langs, mode

    except Exception:
        return ["en"], "english"


# ── engine selection ──────────────────────────────────────────────────────────

def select_ocr_engine(user) -> str:
    """Return ``"mistral"`` for premium users, ``"docai"`` for everyone else.

    Premium (Mistral OCR):
        • UserRole.SUPER_USER
        • UserRole.ADMIN
        • Regular USER with an active subscription

    Standard (Google Document AI):
        • Regular USER on free tier
        • Free-trial / unauthenticated callers (user is None or FreeTrialUser)
    """
    if user is None:
        return "docai"

    from app.models.user import User as UserModel, UserRole
    from app.models.free_trial_user import FreeTrialUser

    if isinstance(user, FreeTrialUser):
        return "docai"

    if isinstance(user, UserModel):
        if user.role in (UserRole.SUPER_USER, UserRole.ADMIN):
            return "mistral"
        if user.has_active_subscription:
            return "mistral"

    return "docai"


async def process_file_mistral(
    file_bytes: bytes,
    langs: list,
    mode: str = "english",
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
) -> dict:
    """Process a file with Mistral OCR (premium engine).

    Handles PDFs and images.  Returns a result dict compatible with all
    existing endpoints and the save-to-database helper.

    The ``text`` field contains structured Markdown with:
      - HTML tables  (from ``table_format="html"``)
      - Inline base64 images at their original positions
      - LaTeX / Unicode math equations
    """
    start_time = time.time()
    file_size = len(file_bytes)

    try:
        file_type = detect_file_type(file_bytes)
        if file_type == "unknown":
            raise ValueError("Unsupported file format — cannot identify file type.")

        if file_size > 10 * 1024 * 1024:
            logger.warning(
                f"LARGE FILE - Mistral OCR - Type: {file_type}, Size: {file_size // 1024}KB"
            )

        file_label = (
            f"PDF ({file_size // 1024}KB)" if file_type == "pdf"
            else f"Image ({file_size // 1024}KB)"
        )
        logger.info(f"Mistral OCR start: {file_label} | user_id={user_id} email={user_email}")

        raw = await run_mistral_ocr(file_bytes, file_type)

        processing_time = time.time() - start_time

        all_pages = raw["pages_data"]
        avg_conf = raw["confidence"]

        if len(all_pages) == 1:
            result = {
                "text": all_pages[0]["text"] if all_pages else "",
                "confidence": avg_conf,
                "pages": 1,
                "languages": langs,
                "mode": mode,
                "engine": raw["engine"],
                "features": raw["features"],
                "images_count": raw.get("images_count", 0),
            }
        else:
            result = {
                "text": raw["text"],
                "pages_data": all_pages,
                "confidence": avg_conf,
                "pages": len(all_pages),
                "languages": langs,
                "mode": mode,
                "engine": raw["engine"],
                "features": raw["features"],
                "images_count": raw.get("images_count", 0),
            }

        log_ocr_operation(
            "COMPLETE", file_label, result,
            user_id=user_id, user_email=user_email,
        )
        log_performance_metrics("MISTRAL_OCR", processing_time, len(all_pages), file_size)
        return result

    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Mistral OCR failed: {str(e)}"
        logger.error(error_msg)
        log_ocr_operation(
            "FAILED", f"File ({file_size // 1024}KB)", error=error_msg,
            user_id=user_id, user_email=user_email,
        )
        log_performance_metrics("MISTRAL_OCR_FAILED", processing_time, 0, file_size)
        raise


async def process_file_auto(
    file_bytes: bytes,
    langs: Optional[list] = None,
    mode: str = "auto",
    user=None,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
) -> dict:
    """Route to Mistral or DocAI based on the caller's role / subscription.

    Language is always auto-detected from the extracted text — callers should
    not pass ``langs`` or ``mode``; both are handled internally.

    Args:
        file_bytes:  Raw document bytes.
        langs:       Ignored — kept for backwards compatibility only.
        mode:        Ignored — language is always auto-detected.
        user:        ``User`` model instance, ``FreeTrialUser``, or ``None``.
        user_id:     User primary key (for logging).
        user_email:  User email address (for logging).

    Returns:
        Structured result dict from either engine, with ``mode`` and
        ``languages`` fields reflecting auto-detected values.
    """
    engine = select_ocr_engine(user)
    logger.info(
        f"OCR engine selected: {engine.upper()} | "
        f"user_id={user_id} email={user_email}"
    )

    # Pass a broad hint so both engines handle any script.
    # Caller-supplied langs/mode are intentionally ignored.
    _langs: list = ["en", "bn"]
    _mode:  str  = "mixed"

    if engine == "mistral":
        result = await process_file_mistral(
            file_bytes, _langs, _mode,
            user_id=user_id, user_email=user_email,
        )
    else:
        result = await process_file(
            file_bytes, _langs, _mode,
            user_id=user_id, user_email=user_email,
        )

    # Always override languages/mode with auto-detected values.
    detected_langs, detected_mode = detect_language(result.get("text", ""))
    result["languages"] = detected_langs
    result["mode"]      = detected_mode
    return result
