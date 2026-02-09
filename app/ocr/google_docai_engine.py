from google.cloud import documentai
import logging
from app.config import settings

logger = logging.getLogger(__name__)


def _detect_mime(file_bytes: bytes) -> str:
    if file_bytes.startswith(b"%PDF"):
        return "application/pdf"
    if file_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "image/png"


def run_docai(file_bytes):
    """Run Google Document AI processing with minimal logging"""
    
    try:
        client = documentai.DocumentProcessorServiceClient()

        name = client.processor_path(
            settings.GOOGLE_PROJECT_ID,
            settings.GOOGLE_LOCATION,
            settings.GOOGLE_PROCESSOR_ID
        )

        mime_type = _detect_mime(file_bytes)
        
        raw = documentai.RawDocument(
            content=file_bytes,
            mime_type=mime_type
        )

        request = documentai.ProcessRequest(name=name, raw_document=raw)

        result = client.process_document(request=request)
        extracted_text = result.document.text
        
        # Only log if DocAI extraction seems problematic
        if len(extracted_text) < 10:
            logger.warning(f"DocAI extracted very little text: {len(extracted_text)} characters")
        
        return extracted_text
        
    except Exception as e:
        logger.error(f"DocAI FAILED: {str(e)}")
        raise
