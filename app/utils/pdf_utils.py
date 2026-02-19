from pdf2image import convert_from_bytes
from typing import List, Optional
from PIL import Image
import io
import os


def count_pdf_pages(file_bytes: bytes) -> int:
    """
    Cheaply count the number of pages in a PDF without rendering.
    Returns the page count, or raises ValueError if the bytes are not a valid PDF.
    """
    import pikepdf
    with pikepdf.open(io.BytesIO(file_bytes)) as pdf:
        return len(pdf.pages)


def pdf_to_images(
    file_bytes: bytes,
    langs: Optional[list] = None,
    dpi: int = 600,
    thread_count: int = 4,
) -> List[Image.Image]:
    # Get DPI from environment or use the provided default
    configured_dpi = int(os.getenv("OCR_PDF_DPI", dpi))

    images = convert_from_bytes(
        file_bytes,
        dpi=configured_dpi,    # Use configured DPI for excellent quality (600 DPI optimal for Bangla & English)
        fmt="png",            # Lossless format
        grayscale=False,      # Keep color info for better preprocessing
        thread_count=thread_count,  # Parallel processing
        use_pdftocairo=True,  # Better rendering engine for Unicode scripts like Bangla
        strict=False          # Don't fail on minor PDF errors
    )

    return images
