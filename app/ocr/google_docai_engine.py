from google.cloud import documentai
from app.config import settings


def _detect_mime(file_bytes: bytes) -> str:
    if file_bytes.startswith(b"%PDF"):
        return "application/pdf"
    if file_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "image/png"


def run_docai(file_bytes):

    client = documentai.DocumentProcessorServiceClient()

    name = client.processor_path(
        settings.GOOGLE_PROJECT_ID,
        settings.GOOGLE_LOCATION,
        settings.GOOGLE_PROCESSOR_ID
    )

    raw = documentai.RawDocument(
        content=file_bytes,
        mime_type=_detect_mime(file_bytes)
    )

    request = documentai.ProcessRequest(name=name, raw_document=raw)

    result = client.process_document(request=request)

    return result.document.text
