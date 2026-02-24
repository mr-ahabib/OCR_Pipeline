"""Mistral OCR engine — premium document processing via Mistral OCR API.

Used for: SUPER_USER, ADMIN, and subscribed regular users.

Capabilities:
  - Faithfully preserves document structure (headings, paragraphs, lists)
  - Tables extracted as HTML (<table> tags) — preserves row/column layout
  - Equations extracted as LaTeX / Unicode inline math in markdown
  - Embedded images (charts, figures, photos) saved to disk and referenced
    by a serve-able URL so the front-end can display / verify them
  - Multi-page PDFs AND standalone images processed in a single API call
  - Per-page confidence computed dynamically from text quality (no hardcoding)

The output "text" field is structured Markdown with HTML tables and
``![alt](url)`` image references pointing to the image-serving endpoint.
``extracted_images`` carries the full list of saved images with their URLs,
page numbers, and MIME types.
"""
import base64
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Thread-pool for offloading blocking Mistral SDK calls from async handlers.
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mistral_ocr")

# Sub-directory under settings.UPLOAD_DIR where OCR-extracted images are stored.
OCR_IMAGES_SUBDIR = "ocr_images"


# ── confidence calculation ────────────────────────────────────────────────────

def _compute_page_confidence(text: str) -> float:
    """Compute a confidence score (0–100) from the extracted markdown text.

    Measures the ratio of clean, printable content to total characters.
    Characters that indicate OCR degradation:
      - U+FFFD  Unicode replacement character (unrecognised byte sequences)
      - ASCII control characters other than \\n, \\r, \\t

    Formula:
        confidence = (1 - bad_ratio) * 100, clamped to [50.0, 99.9]

    A perfectly clean page returns ~99.9; heavy noise / encoding failures
    return proportionally lower values.  No value is ever hardcoded.
    """
    if not text:
        return 0.0
    total = len(text)
    bad = sum(
        1 for c in text
        if c == "\ufffd"                                   # replacement char
        or (ord(c) < 32 and c not in ("\n", "\r", "\t"))  # non-printable control
    )
    ratio = bad / total
    return round(min(99.9, max(50.0, (1.0 - ratio) * 100)), 2)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_client():
    """Return a Mistral client using the configured API key."""
    try:
        from mistralai import Mistral
    except ImportError as exc:
        raise ImportError(
            "mistralai package is not installed. Run: pip install mistralai"
        ) from exc

    api_key = settings.MISTRAL_API_KEY
    if not api_key:
        raise ValueError(
            "MISTRAL_API_KEY is not configured. "
            "Add MISTRAL_API_KEY=<your-key> to your .env file."
        )
    return Mistral(api_key=api_key)


def _detect_image_mime(file_bytes: bytes) -> str:
    """Detect the MIME type of an image from its magic bytes."""
    if file_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if file_bytes[:4] in (b"GIF8",):
        return "image/gif"
    if file_bytes[:2] == b"BM":
        return "image/bmp"
    if file_bytes[:4] == b"RIFF" and b"WEBP" in file_bytes[:12]:
        return "image/webp"
    if file_bytes[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return "image/jpeg"


def _detect_base64_mime(b64_str: str) -> str:
    """Guess image MIME from the first bytes of a base64 string."""
    try:
        header = base64.b64decode(b64_str[:16] + "==")
        return _detect_image_mime(header)
    except Exception:
        return "image/jpeg"


def _mime_to_ext(mime: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png":  "png",
        "image/gif":  "gif",
        "image/bmp":  "bmp",
        "image/webp": "webp",
        "image/tiff": "tiff",
    }.get(mime, "jpg")


def get_ocr_images_dir() -> Path:
    """Return the directory where OCR-extracted images are stored (created if needed)."""
    p = Path(settings.UPLOAD_DIR) / OCR_IMAGES_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build_image_url(filename: str) -> str:
    """Build the full public URL for a saved OCR image."""
    base = (settings.API_BASE_URL or "").rstrip("/")
    return f"{base}/api/v1/ocr/images/{filename}"


def save_ocr_image_b64(b64_str: str, page_num: int) -> dict:
    """Decode a base64 image string, save it to disk, and return metadata.

    Returns::

        {
            "filename": "ocr_img_<uuid>.jpg",
            "url":      "https://…/api/v1/ocr/images/ocr_img_<uuid>.jpg",
            "mime":     "image/jpeg",
            "page":     1,
            "size_kb":  45.3,
        }
    """
    mime      = _detect_base64_mime(b64_str)
    ext       = _mime_to_ext(mime)
    filename  = f"ocr_img_{uuid.uuid4().hex}.{ext}"
    save_path = get_ocr_images_dir() / filename

    img_bytes = base64.b64decode(b64_str)
    save_path.write_bytes(img_bytes)

    return {
        "filename": filename,
        "url":      _build_image_url(filename),
        "mime":     mime,
        "page":     page_num,
        "size_kb":  round(len(img_bytes) / 1024, 1),
    }


def _replace_images_with_urls(
    markdown: str, images: list, page_num: int
) -> tuple[str, list]:
    """Save each extracted image to disk and replace ``![id](id)`` tokens with
    a serve-able URL reference.

    Returns:
        (updated_markdown, image_records_list)
    """
    if not images:
        return markdown, []

    record_map: dict[str, dict] = {}
    image_records: list[dict] = []

    for img in images:
        img_id = getattr(img, "id", None)
        b64    = getattr(img, "image_base64", None) or ""
        if not img_id or not b64:
            continue
        try:
            rec = save_ocr_image_b64(b64, page_num)
            rec["image_id"] = img_id
            record_map[img_id] = rec
            image_records.append(rec)
        except Exception as exc:
            logger.warning(f"Failed to save OCR image {img_id} on page {page_num}: {exc}")

    if not record_map:
        return markdown, image_records

    def _replace(match: re.Match) -> str:
        alt = match.group(1)
        ref = match.group(2)
        rec = record_map.get(ref)
        if rec is None:
            for k, v in record_map.items():
                if k.startswith(ref) or ref.startswith(k):
                    rec = v
                    break
        if rec:
            return f"![{alt or 'extracted image'}]({rec['url']})"
        return match.group(0)

    updated_md = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", _replace, markdown)
    return updated_md, image_records


# ── main sync worker (runs in thread pool) ───────────────────────────────────

def _run_mistral_ocr_sync(file_bytes: bytes, file_type: str) -> dict:
    """Blocking Mistral OCR call.  Called via ``run_mistral_ocr`` (async wrapper).

    Accepts both ``"pdf"`` and ``"image"`` (JPEG, PNG, BMP, WebP, TIFF, GIF).

    Returns a dict with:
        pages_data       – list of per-page dicts; confidence is computed
                           dynamically, not hardcoded
        text             – full document markdown (pages separated by ``---``)
        confidence       – float average across pages (0–100)
        pages            – int
        images_count     – int (extracted figures saved to disk)
        extracted_images – list[dict] — url / filename / mime / page / size_kb
        usage            – dict with Mistral usage info
        engine           – str
        features         – list[str]
    """
    client = _get_client()
    b64_doc = base64.b64encode(file_bytes).decode("utf-8")

    if file_type == "pdf":
        document = {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{b64_doc}",
        }
    elif file_type == "image":
        mime = _detect_image_mime(file_bytes)
        document = {
            "type": "image_url",
            "image_url": f"data:{mime};base64,{b64_doc}",
        }
    else:
        raise ValueError(f"Unsupported file type for Mistral OCR: {file_type!r}")

    logger.info(
        f"Mistral OCR → sending {file_type.upper()} "
        f"({len(file_bytes) // 1024}KB) to mistral-ocr-latest"
    )
    t0 = time.time()

    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document=document,
        table_format="html",        # Tables as <table> HTML — preserves structure
        include_image_base64=True,  # Return extracted images as base64
    )

    elapsed = time.time() - t0
    logger.info(f"Mistral OCR ← response received in {elapsed:.2f}s")

    pages_data:        list[dict]  = []
    all_image_records: list[dict]  = []
    page_texts:        list[str]   = []
    page_confidences:  list[float] = []

    for page in ocr_response.pages:
        page_num = page.index + 1   # Mistral pages are 0-indexed
        raw_md   = page.markdown or ""
        images   = page.images or []

        # Save images to disk → replace markdown refs with public URLs
        md_with_urls, page_image_records = _replace_images_with_urls(
            raw_md, images, page_num
        )
        all_image_records.extend(page_image_records)

        # Compute confidence dynamically from actual text quality
        conf = _compute_page_confidence(md_with_urls)
        page_confidences.append(conf)

        pages_data.append({
            "page_number":     page_num,
            "text":            md_with_urls,
            "confidence":      conf,
            "character_count": len(md_with_urls),
        })
        page_texts.append(md_with_urls)

    full_text = "\n\n---\n\n".join(page_texts)
    avg_conf  = round(
        sum(page_confidences) / len(page_confidences)
        if page_confidences else 0.0,
        2,
    )

    usage: dict = {}
    if hasattr(ocr_response, "usage_info") and ocr_response.usage_info:
        u = ocr_response.usage_info
        usage = {
            "pages_processed": getattr(u, "pages_processed", None),
            "doc_size_bytes":  getattr(u, "doc_size_bytes",  None),
        }

    logger.info(
        f"Mistral OCR complete: {len(pages_data)} pages, "
        f"{len(all_image_records)} images saved, "
        f"avg confidence {avg_conf:.1f}%, {elapsed:.2f}s"
    )

    return {
        "pages_data":       pages_data,
        "text":             full_text,
        "confidence":       avg_conf,
        "pages":            len(pages_data),
        "images_count":     len(all_image_records),
        "extracted_images": all_image_records,
        "usage":            usage,
        "engine":           "Mistral OCR",
        "features": [
            "Structure-preserving markdown output",
            "HTML table extraction",
            "LaTeX / math equation extraction",
            "Extracted images served via URL",
            "Dynamic per-page confidence scoring",
            "Auto language detection",
            "Multi-page PDF and standalone image support",
        ],
    }


# ── public async API ──────────────────────────────────────────────────────────

async def run_mistral_ocr(file_bytes: bytes, file_type: str) -> dict:
    """Async wrapper: run Mistral OCR in a thread pool.

    Args:
        file_bytes: Raw document bytes (PDF or any image format).
        file_type:  ``"pdf"`` or ``"image"``.

    Returns the structured dict from ``_run_mistral_ocr_sync``.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _EXECUTOR, _run_mistral_ocr_sync, file_bytes, file_type
    )
