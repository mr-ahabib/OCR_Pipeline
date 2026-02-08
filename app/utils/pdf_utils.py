from pdf2image import convert_from_bytes
from typing import List, Optional
from PIL import Image


def pdf_to_images(
    file_bytes: bytes,
    langs: Optional[list] = None,
    dpi: int = 600,
    thread_count: int = 4,
) -> List[Image.Image]:

    images = convert_from_bytes(
        file_bytes,
        dpi=dpi,              # 🔥 600 DPI = excellent for both Bangla & English
        fmt="png",            # Lossless format
        grayscale=False,      # Keep color info for better preprocessing
        thread_count=thread_count,  # Parallel processing
        use_pdftocairo=True,  # Better rendering engine
        strict=False          # Don't fail on minor PDF errors
    )

    return images
