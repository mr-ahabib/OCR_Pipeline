from pdf2image import convert_from_bytes
from typing import List
from PIL import Image


def pdf_to_images(file_bytes: bytes) -> List[Image.Image]:
    """
    Convert PDF → ultra high quality images for OCR

    Optimized for:
    - Bangla thin glyphs and complex characters
    - English books and documents
    - Mixed language content
    - Maximum accuracy
    
    Key improvements:
    - 600 DPI for crystal clear text
    - PNG format for lossless quality
    - Proper color space handling
    """

    images = convert_from_bytes(
        file_bytes,
        dpi=600,              # 🔥 600 DPI = excellent for both Bangla & English
        fmt="png",            # Lossless format
        grayscale=False,      # Keep color info for better preprocessing
        thread_count=4,       # Parallel processing
        use_pdftocairo=True,  # Better rendering engine
        strict=False          # Don't fail on minor PDF errors
    )

    return images
