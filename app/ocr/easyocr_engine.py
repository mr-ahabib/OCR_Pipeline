import easyocr
import numpy as np
import ocrmypdf
import tempfile
import re
import os
from pathlib import Path
from PIL import Image
import cv2

SUPPORTED = {"en", "bn", "ar"}

readers = {}

LANG_MAP = {
    "en": "eng",
    "bn": "ben",
    "ar": "ara"
}

# Bangla Unicode range: \u0980-\u09FF
BANGLA_PATTERN = re.compile(r'[\u0980-\u09FF]')
ENGLISH_PATTERN = re.compile(r'[A-Za-z]')
ARABIC_PATTERN = re.compile(r'[\u0600-\u06FF]')


def _resize_for_ocr(img, target_max_dim=3000):  # Increased from 2500 for better Bangla text capture
    try:
        if isinstance(img, Image.Image):
            w, h = img.size
            max_dim = max(w, h)
            if max_dim <= target_max_dim:
                return img
            scale = target_max_dim / max_dim
            new_size = (int(w * scale), int(h * scale))
            return img.resize(new_size, Image.LANCZOS)
        elif isinstance(img, np.ndarray):
            h, w = img.shape[:2]
            max_dim = max(w, h)
            if max_dim <= target_max_dim:
                return img
            scale = target_max_dim / max_dim
            new_w, new_h = int(w * scale), int(h * scale)
            return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        return img
    except:
        return img


def preprocess_with_ocrmypdf_easyocr(img, langs):
    """Preprocess with ocrmypdf to improve EasyOCR quality."""
    # Get oversample DPI from environment or use default
    oversample_dpi = int(os.getenv("OCRMYPDF_OVERSAMPLE_DPI", 600))
    
    # Resize large images first to prevent memory issues
    img = _resize_for_ocr(img, target_max_dim=3000)  # Increased from 2500
    
    with tempfile.TemporaryDirectory() as tmpdir:
        input_img_path = Path(tmpdir) / "input.png"
        output_pdf_path = Path(tmpdir) / "preprocessed.pdf"

        if isinstance(img, np.ndarray):
            img_pil = Image.fromarray(img)
        elif isinstance(img, Image.Image):
            img_pil = img
        elif isinstance(img, (str, Path)):
            # Load image from file path
            img_pil = Image.open(img)
        else:
            # Assume it's already a PIL Image or compatible
            img_pil = img

        # Save with maximum quality
        img_pil.save(input_img_path, compress_level=0)

        try:
            lang_codes = [LANG_MAP.get(l, l) for l in langs if l in SUPPORTED]
            if not lang_codes:
                lang_codes = ["eng"]
            lang_string = "+".join(lang_codes)

            ocrmypdf.ocr(
                input_img_path,
                output_pdf_path,
                language=lang_string,
                deskew=True,
                clean=True,
                clean_final=True,
                remove_background=True,
                optimize=3,
                jpeg_quality=95,
                png_quality=95,
                jbig2_lossy=False,
                oversample=oversample_dpi,  # Use configured DPI
                remove_vectors=False,
                output_type='pdf',
                redo_ocr=True,
                force_ocr=True,
                skip_text=True,
                use_threads=True,
                invalidate_digital_signatures=True,
                tesseract_timeout=300,
                pdfa_image_compression='lossless',
                quiet=True,
                progress_bar=False
            )

            from pdf2image import convert_from_path
            images = convert_from_path(str(output_pdf_path), dpi=oversample_dpi)  # Use same DPI

            if images:
                return np.array(images[0])
            return np.array(img_pil)
        except Exception:
            return np.array(img_pil)


def get_reader(langs):
    """Create or reuse EasyOCR reader with GPU if available."""
    langs = [l for l in langs if l in SUPPORTED]
    if not langs:
        langs = ["en"]

    # For Bangla-only mode, force only Bangla to reduce English hallucinations
    if langs == ['bn']:
        key = "bn_only"
        if key not in readers:
            try:
                import torch
                if torch.cuda.is_available():
                    readers[key] = easyocr.Reader(['bn'], gpu=True, verbose=False)
                else:
                    readers[key] = easyocr.Reader(['bn'], gpu=False, verbose=False)
            except Exception:
                readers[key] = easyocr.Reader(['bn'], gpu=False, verbose=False)
        return readers[key]

    key = "_".join(sorted(langs))

    if key not in readers:
        try:
            import torch
            if torch.cuda.is_available():
                readers[key] = easyocr.Reader(langs, gpu=True, verbose=False)
            else:
                readers[key] = easyocr.Reader(langs, gpu=False, verbose=False)
        except Exception:
            readers[key] = easyocr.Reader(langs, gpu=False, verbose=False)

    return readers[key]


def _filter_hallucinated_english_token(token: str, langs: list, mode: str = "english") -> str:
    """
    AGGRESSIVE filtering of hallucinated English characters from a single token.
    In Bangla-only mode, removes virtually all English except absolutely essential cases.
    """
    if not token:
        return token

    # If English is explicitly requested, keep everything
    if 'en' in langs:
        return token

    has_bangla = bool(BANGLA_PATTERN.search(token))
    has_arabic = bool(ARABIC_PATTERN.search(token))
    has_english = bool(ENGLISH_PATTERN.search(token))

    # Bangla-only mode - VERY AGGRESSIVE filtering
    if 'bn' in langs and 'en' not in langs:
        if has_english and not has_bangla:
            # Pure English token in Bangla-only mode
            # Only allow very specific cases:
            # 1. Pure numbers (no letters)
            if re.match(r'^\d+$', token):
                return token
            # 2. Common scientific/mathematical symbols
            if token in {'kg', 'cm', 'mm', 'km', 'mg', 'ml', 'pH', 'DNA', 'RNA', 'CO2', 'H2O'}:
                return token
            # 3. Very short single letters (e.g., variables)
            if len(token) == 1 and token in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
                return ""  # Remove even single letters
            return ""  # Remove all other English
            
        elif has_english and has_bangla:
            # Mixed token - be very aggressive about removing English
            bangla_chars = len(re.findall(r'[\u0980-\u09FF]', token))
            english_chars = len(re.findall(r'[A-Za-z]', token))
            
            # If more than 30% English in a mixed token, likely hallucination
            if english_chars / (bangla_chars + english_chars) > 0.3:
                # Strip all English characters
                cleaned = re.sub(r'[A-Za-z]', '', token)
                return cleaned.strip() if cleaned.strip() else ""
            else:
                # Keep mixed token but warn that some English remains
                return token

    # Arabic-only mode - similar aggressive filtering
    if 'ar' in langs and 'en' not in langs:
        if has_english and not has_arabic:
            if re.match(r'^\d+$', token):
                return token
            return ""
        elif has_english and has_arabic:
            cleaned = re.sub(r'[A-Za-z]', '', token)
            return cleaned.strip() if cleaned.strip() else ""

    return token


def _filter_hallucinated_english(text: str, langs: list, mode: str = "english") -> str:
    """
    AGGRESSIVE filtering of hallucinated English words/characters from OCR output.
    For Bangla-only mode, removes virtually all English text.
    """
    if not text:
        return text

    # If English is requested, no filtering needed
    if 'en' in langs:
        return text

    # Apply token-level filtering
    tokens = text.split()
    filtered_tokens = []

    for token in tokens:
        cleaned = _filter_hallucinated_english_token(token, langs)
        if cleaned:
            filtered_tokens.append(cleaned)

    result = ' '.join(filtered_tokens)
    
    # Additional sentence-level filtering for Bangla
    if 'bn' in langs and 'en' not in langs:
        # Remove any remaining isolated English words that slipped through
        words = result.split()
        final_words = []
        
        for word in words:
            # Check if word is purely English (no Bangla chars)
            if ENGLISH_PATTERN.search(word) and not BANGLA_PATTERN.search(word):
                # Skip unless it's a number or very specific exception
                if re.match(r'^\d+[.,:]?$', word):  # Numbers with punctuation
                    final_words.append(word)
                # Otherwise skip this English word
            else:
                final_words.append(word)
        
        result = ' '.join(final_words)
    
    # Clean up any double spaces
    result = re.sub(r' {2,}', ' ', result).strip()
    
    return result
    
    return result


def run_easyocr(img, langs, use_ocrmypdf=True, mode="english"):
    """Run EasyOCR with optional preprocessing and mode-based filtering."""
    import logging
    logger = logging.getLogger(__name__)
    
    if use_ocrmypdf:
        logger.info("Preprocessing image with OCRmyPDF for EasyOCR...")
        img = preprocess_with_ocrmypdf_easyocr(img, langs)

    reader = get_reader(langs)
    
    logger.info(f"Running EasyOCR with languages: {langs}")

    # Adjust thresholds for Bangla-only mode to reduce English hallucinations
    # but also ensure we capture all Bangla text
    if mode == "bangla":
        # Balanced thresholds for Bangla-only mode - optimized for speed
        result = reader.readtext(
            img,
            detail=1,
            paragraph=False,
            text_threshold=0.70,  # Slightly more lenient to catch all Bangla text
            low_text=0.40,       # More lenient to catch faint text
            link_threshold=0.40, # More lenient for text linking
            min_size=10,         # Smaller minimum size to catch small text
            canvas_size=2560,    # Reduced from 3000 for faster processing
            mag_ratio=1.5,       # Reduced from 1.8 for faster processing
            rotation_info=None,
            width_ths=0.65,      # More lenient
            height_ths=0.65,     # More lenient
            slope_ths=0.15,      # More lenient for slanted text
            allowlist=None,
            blocklist=None
        )
    else:
        result = reader.readtext(
            img,
            detail=1,
            paragraph=False,
            text_threshold=0.75,
            low_text=0.45,
            link_threshold=0.45,
            min_size=15,
            canvas_size=2560,
            mag_ratio=1.5,
            rotation_info=None,
            width_ths=0.7,
            height_ths=0.7,
            slope_ths=0.1,
            allowlist=None,
            blocklist=None
        )

    if not result:
        logger.warning("EasyOCR returned no detections")
        return "", 0.0
    
    logger.info(f"EasyOCR raw detections: {len(result)} items")

    # Collect all word boxes with their positions for layout preservation
    word_boxes = []
    all_confs = []

    for detection in result:
        if len(detection) == 3:
            bbox, text, confidence = detection
        elif len(detection) == 2:
            text, confidence = detection
            bbox = None
        else:
            continue

        text_stripped = text.strip()
        if not text_stripped:
            continue

        confidence = float(confidence)

        # Early filtering: for Bangla-only mode, reject English-only detections
        if mode == "bangla":
            has_bangla = bool(BANGLA_PATTERN.search(text_stripped))
            has_english = bool(ENGLISH_PATTERN.search(text_stripped))
            
            # If it's pure English in Bangla-only mode, skip it entirely
            if has_english and not has_bangla:
                # Exception for pure numbers only
                if not re.match(r'^\d+[.,:]?$', text_stripped):
                    logger.debug(f"Skipping pure English detection in Bangla mode: '{text_stripped}'")
                    continue

        # More lenient confidence thresholds to capture all text
        min_conf = 0.40 if mode == "bangla" else 0.45  # Lower threshold for Bangla
        if confidence < min_conf:
            continue

        if len(text_stripped) <= 2 and confidence < 0.60:  # More lenient for short text
            continue

        if text_stripped in '.,;:!?-()[]{}"\'' and confidence < 0.65:  # More lenient for punctuation
            continue

        all_confs.append(confidence * 100)
        word_boxes.append(text_stripped)

    # Build simple text output - let EasyOCR's natural ordering handle layout
    if word_boxes:
        final_text = ' '.join(word_boxes)
    else:
        final_text = ""

    # Filter hallucinated English based on mode
    if mode == "bangla":
        final_text = _filter_hallucinated_english(final_text, ["bn"])
    elif mode == "english":
        # No filtering for English-only mode
        pass
    elif mode == "mixed":
        # Light filtering for mixed mode
        final_text = _filter_hallucinated_english(final_text, langs)

    if all_confs:
        avg_conf = sum(all_confs) / len(all_confs)
    else:
        avg_conf = 0.0

    return final_text, avg_conf
