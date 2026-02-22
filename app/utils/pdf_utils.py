import io
import pikepdf


def count_pdf_pages(file_bytes: bytes) -> int:
    """
    Cheaply count the number of pages in a PDF without rendering.
    Returns the page count, or raises ValueError if the bytes are not a valid PDF.
    """
    with pikepdf.open(io.BytesIO(file_bytes)) as pdf:
        return len(pdf.pages)
