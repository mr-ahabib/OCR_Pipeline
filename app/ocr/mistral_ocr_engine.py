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

    Uses three weighted signals so scores vary meaningfully across documents:

    Signal 1 — Bad character ratio  (weight 50%):
        Counts Unicode replacement chars (U+FFFD) and non-printable control
        characters (except \\n, \\r, \\t).  Clean text scores 1.0 here.

    Signal 2 — Alphanumeric density  (weight 30%):
        Fraction of the *plain* text (markdown stripped) that consists of
        letters or digits.  Garbage/symbol-heavy output scores lower.

    Signal 3 — Word plausibility  (weight 20%):
        Ratio of 2–20 character word-like tokens to all whitespace-separated
        tokens.  Very short or very long "words" (rubbish sequences) reduce
        this score.

    Empty page  → 0.0
    Typical clean page → ~85–95  (not always 99.9)
    Heavy noise → proportionally lower
    """
    if not text:
        return 0.0

    total = len(text)

    # --- Signal 1: bad characters ---
    bad = sum(
        1 for c in text
        if c == "\ufffd"
        or (ord(c) < 32 and c not in ("\n", "\r", "\t"))
    )
    bad_score = 1.0 - (bad / total)

    # Strip markdown constructs to measure actual content
    plain = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)   # image refs
    plain = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", plain)   # links
    plain = re.sub(r"```[\s\S]*?```", " ", plain)         # fenced code blocks
    plain = re.sub(r"`[^`]+`", " ", plain)                # inline code
    plain = re.sub(r"[#*_~|<>{}\\\-=+]", " ", plain)     # markup symbols
    plain = re.sub(r"\s+", " ", plain).strip()

    if not plain:
        return round(min(99.9, max(0.0, bad_score * 50.0)), 2)

    # --- Signal 2: alphanumeric density ---
    alnum_count = sum(1 for c in plain if c.isalnum())
    alnum_ratio = alnum_count / len(plain)

    # --- Signal 3: word plausibility ---
    all_tokens = plain.split()
    plausible_words = [t for t in all_tokens if 2 <= len(t) <= 20]
    word_score = len(plausible_words) / max(len(all_tokens), 1)

    confidence = (
        bad_score   * 50.0
        + alnum_ratio * 30.0
        + word_score  * 20.0
    )
    return round(min(99.9, max(0.0, confidence)), 2)


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
    """Return the absolute directory where OCR-extracted images are stored (created if needed)."""
    p = Path(settings.UPLOAD_DIR).resolve() / OCR_IMAGES_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build_image_url(filename: str) -> str:
    """Build the URL for a saved OCR image.

    Uses API_BASE_URL if configured (e.g. https://api.example.com), otherwise
    falls back to a relative path that works for same-origin frontend requests.
    """
    base = (settings.API_BASE_URL or "").rstrip("/")
    if base:
        return f"{base}/api/v1/ocr/images/{filename}"
    return f"/api/v1/ocr/images/{filename}"


def save_ocr_image_b64(b64_str: str, page_num: int) -> dict:
    """Decode a base64 image string, save it to disk, and return metadata.

    Mistral returns image_base64 with a data URI prefix such as
    ``data:image/jpeg;base64,/9j/4AAQ...`` — this function strips it before
    decoding so the saved file is a valid image.
    """
    # Strip data URI prefix if present: "data:<mime>;base64,<data>"
    if b64_str.startswith("data:"):
        # everything after the first comma is the actual base64 payload
        b64_str = b64_str.split(",", 1)[-1]

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
    """Save each extracted image to disk and replace Mistral's internal
    ``![id](id)`` tokens with standard ``![alt](url)`` pointing to the
    image-serving endpoint.
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

    def _lookup(ref: str):
        if ref in record_map:
            return record_map[ref]
        for k, v in record_map.items():
            if k.startswith(ref) or ref.startswith(k):
                return v
        return None

    def _replace(match: re.Match) -> str:
        alt = match.group(1) or "image"
        ref = match.group(2)
        rec = _lookup(ref)
        if rec is None:
            return match.group(0)
        return f"![{alt}]({rec['url']})"

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
