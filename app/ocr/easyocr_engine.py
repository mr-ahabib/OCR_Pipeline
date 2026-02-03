import easyocr
import numpy as np

# EasyOCR only supports these codes
SUPPORTED = {"en", "bn", "ar"}

readers = {}


def get_reader(langs):
    """
    EasyOCR uses:
    en, bn, ar
    (NOT eng/ben/ara)
    
    Creates reader with GPU support if available
    """

    # filter unsupported
    langs = [l for l in langs if l in SUPPORTED]

    if not langs:
        langs = ["en"]  # safe fallback

    key = "_".join(sorted(langs))

    if key not in readers:
        # Try GPU first, fallback to CPU
        try:
            readers[key] = easyocr.Reader(langs, gpu=True)
        except:
            readers[key] = easyocr.Reader(langs, gpu=False)

    return readers[key]


def run_easyocr(img, langs):
    """
    Enhanced EasyOCR with better text assembly and confidence calculation
    
    Args:
        img: Preprocessed image (binary or grayscale)
        langs: List of language codes
    
    Returns:
        text: Extracted text
        conf: Average confidence score (0-100)
    """

    reader = get_reader(langs)
    
    # EasyOCR parameters for better accuracy
    result = reader.readtext(
        img,
        detail=1,
        paragraph=True,        # Group text into paragraphs (better for books)
        min_size=10,           # Minimum text size to detect
        text_threshold=0.7,    # Confidence threshold for text detection
        low_text=0.4,          # Lower bound for text region
        link_threshold=0.4,    # Link threshold for text grouping
        canvas_size=2560,      # Larger canvas for better detection
        mag_ratio=1.5          # Magnification ratio
    )

    if not result:
        return "", 0.0

    texts = []
    confs = []

    for detection in result:
        bbox, text, confidence = detection
        
        if text.strip():  # Only add non-empty text
            texts.append(text.strip())
            confs.append(confidence * 100)

    # Join with proper spacing
    final_text = " ".join(texts)
    
    # Calculate weighted average confidence
    if confs:
        avg_conf = sum(confs) / len(confs)
    else:
        avg_conf = 0.0

    return final_text, avg_conf
