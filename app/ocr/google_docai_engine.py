"""Google Document AI engine — per-page JPEG image requests.

Speed strategy:
  Every page (from a PDF or a standalone image) is converted to a JPEG and
  sent to DocAI as a single image request.  Single-image requests complete
  in 1-3 s each and never hit the sync-API timeout that kills multi-page
  PDF submissions.
"""
from google.cloud import documentai
from google.api_core import retry as api_retry
from PIL import Image
import io
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Kept for backward compat / image endpoints
DOCAI_MAX_PAGES = 15          # not used for PDF any more, retained for import safety


# Timeout in seconds for each individual DocAI image request.
# Single-page JPEG calls complete in 1-3 s; 60 s gives very generous headroom.
_DOCAI_CALL_TIMEOUT = 60


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_client_and_name():
    client = documentai.DocumentProcessorServiceClient()
    name = client.processor_path(
        settings.GOOGLE_PROJECT_ID,
        settings.GOOGLE_LOCATION,
        settings.GOOGLE_PROCESSOR_ID,
    )
    return client, name


def _pil_to_jpeg(image: Image.Image, quality: int = 85) -> bytes:
    """Convert PIL Image to JPEG bytes at the given quality."""
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _extract_confidence(doc: documentai.Document) -> float:
    """Average token confidence across all pages, scaled 0-100."""
    confs = [
        t.layout.confidence
        for p in doc.pages
        for t in p.tokens
        if t.layout.confidence > 0
    ]
    return round((sum(confs) / len(confs)) * 100, 2) if confs else 99.0


# ── public API ────────────────────────────────────────────────────────────────

def run_docai_page(jpeg_bytes: bytes, page_number: int) -> dict:
    """
    Send a single JPEG page to DocAI.
    Returns:
        {"page_number": int, "text": str, "confidence": float, "character_count": int}
    """
    try:
        client, name = _build_client_and_name()
        raw = documentai.RawDocument(content=jpeg_bytes, mime_type="image/jpeg")
        result = client.process_document(
            request=documentai.ProcessRequest(name=name, raw_document=raw),
            timeout=_DOCAI_CALL_TIMEOUT,
        )
        doc = result.document
        text = doc.text or ""
        conf = _extract_confidence(doc)
        return {
            "page_number": page_number,
            "text": text,
            "confidence": conf,
            "character_count": len(text),
        }
    except Exception as e:
        logger.error(f"DocAI page {page_number} FAILED: {e}")
        raise


def run_docai(file_bytes: bytes) -> tuple[str, float]:
    """
    Send any image bytes (JPEG/PNG) to DocAI.
    Returns (text, confidence_percent).
    """
    # Detect mime
    if file_bytes[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    else:
        mime = "image/png"
    try:
        client, name = _build_client_and_name()
        raw = documentai.RawDocument(content=file_bytes, mime_type=mime)
        result = client.process_document(
            request=documentai.ProcessRequest(name=name, raw_document=raw),
            timeout=_DOCAI_CALL_TIMEOUT,
        )
        doc = result.document
        conf = _extract_confidence(doc)
        if len(doc.text) < 10:
            logger.warning(f"DocAI extracted very little text: {len(doc.text)} chars")
        return doc.text or "", conf
    except Exception as e:
        logger.error(f"DocAI FAILED: {e}")
        raise


def run_docai_image(image: Image.Image) -> tuple[str, float]:
    """Convenience: PIL Image → DocAI → (text, confidence%)."""
    text_conf = run_docai_page(_pil_to_jpeg(image), page_number=1)
    return text_conf["text"], text_conf["confidence"]
