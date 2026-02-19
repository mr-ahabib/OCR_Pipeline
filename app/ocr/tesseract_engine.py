import pytesseract
from pytesseract import Output
from app.core.config import settings
import numpy as np
import cv2
import ocrmypdf
import tempfile
import os
from pathlib import Path
from PIL import Image
import io
import re
from concurrent.futures import ThreadPoolExecutor

from app.ocr.easyocr_engine import get_reader, preprocess_with_ocrmypdf_easyocr, run_easyocr, _filter_hallucinated_english

pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

def detect_column_layout(img):
    """
    Detect if image has single or multiple columns
    Returns: 'single', 'multi'
    """
    try:
        if isinstance(img, np.ndarray):
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        else:
            gray = np.array(img.convert('L'))
        
        # Use connected components analysis
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Analyze horizontal projection
        h_projection = np.sum(binary, axis=0)
        h_mean = np.mean(h_projection)
        
        # Count significant valleys (potential column separators)
        valleys = 0
        in_valley = False
        for val in h_projection:
            if val < h_mean * 0.3:
                if not in_valley:
                    valleys += 1
                    in_valley = True
            else:
                in_valley = False
        
        # If multiple significant valleys, likely multi-column
        return 'multi' if valleys >= 2 else 'single'
    except:
        return 'single'  # Default to single column

LANG_MAP = {
    "en": "eng",
    "bn": "ben",
    "ar": "ara"
}

SCRIPT_MAP = {
    "en": "Latin",
    "bn": "Bengali",
    "ar": "Arabic"
}

DEFAULT_WORKERS = max(2, min(8, (os.cpu_count() or 4)))
OCR_ENGINE_MAX_WORKERS = int(os.getenv("OCR_ENGINE_MAX_WORKERS", DEFAULT_WORKERS))

TESSERACT_CONFIGS = {
    # Bengali configurations - Use OEM 3 (legacy + LSTM) for best Bangla accuracy
    # OEM 3 combines both engines for better Unicode script support
    "bengali_single": "--oem 3 --psm 6 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1 -c textord_heavy_nr=1",
    "bengali_multi": "--oem 3 --psm 1 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1 -c textord_heavy_nr=1",
    "bengali_auto": "--oem 3 --psm 3 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1 -c textord_heavy_nr=1",
    "bengali_script": "--oem 3 --psm 6 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1 -c textord_heavy_nr=1 -c tessedit_char_whitelist= ",
    
    # English configurations - OEM 1 (LSTM) is fine for English
    "english_single": "--oem 1 --psm 6 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1",
    "english_multi": "--oem 1 --psm 1 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1",
    "english_auto": "--oem 1 --psm 3 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1",
    
    # Mixed language configurations - OEM 3 for better multi-script support
    "mixed_single": "--oem 3 --psm 6 -c preserve_interword_spaces=1",
    "mixed_multi": "--oem 3 --psm 1 -c preserve_interword_spaces=1",
    "mixed_auto": "--oem 3 --psm 3 -c preserve_interword_spaces=1",
}


EASYOCR_ENGLISH_CONF_THRESHOLD = 75.0  # EasyOCR confidence is 0-100 after scaling - even stricter threshold

EASYOCR_PARAMS = {
    "detail": 1,
    "paragraph": False,
    "text_threshold": 0.75,
    "low_text": 0.45,
    "link_threshold": 0.45,
    "min_size": 15,
    "canvas_size": 2560,
    "mag_ratio": 1.5,
    "rotation_info": None,
    "width_ths": 0.7,
    "height_ths": 0.7,
    "slope_ths": 0.1,
    "allowlist": None,
    "blocklist": None,
}

def _extract_text_with_layout(img, lang_string, config):
    """
    Extract text while preserving layout structure (line breaks, spacing, etc.)
    Uses bounding boxes to reconstruct the original layout with proper reading order.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = pytesseract.image_to_data(
            img,
            lang=lang_string,
            config=config,
            output_type=Output.DICT
        )
        
        # Collect all word boxes with their positions
        word_boxes = []
        confs = []
        
        n_boxes = len(data['text'])
        logger.info(f"Processing {n_boxes} total boxes from Tesseract")
        
        for i in range(n_boxes):
            conf = int(data['conf'][i])
            text = data['text'][i].strip()
            
            if conf > 0 and text:
                confs.append(conf)
                top = data['top'][i]
                left = data['left'][i]
                width = data['width'][i]
                height = data['height'][i]
                
                word_boxes.append({
                    'text': text,
                    'top': top,
                    'left': left,
                    'right': left + width,
                    'bottom': top + height,
                    'center_y': top + height // 2,
                    'center_x': left + width // 2
                })
        
        logger.info(f"Found {len(word_boxes)} valid words to process")
        
        if not word_boxes:
            logger.warning("No word boxes found, returning empty")
            return "", 0
        
        # Sort all words by vertical position first (top to bottom), then horizontal (left to right)
        word_boxes.sort(key=lambda x: (x['top'], x['left']))
        logger.info(f"Sorted {len(word_boxes)} words by position")
        
        # Group words into lines - simple approach: group by similar Y positions
        # This is more reliable than complex overlap detection
        lines = []
        current_line = [word_boxes[0]]
        line_reference_top = word_boxes[0]['top']  # Reference Y position for this line
        line_max_height = word_boxes[0]['bottom'] - word_boxes[0]['top']
        
        for word in word_boxes[1:]:
            word_height = word['bottom'] - word['top']
            
            # Check if this word is on the same line as current_line
            # Use the reference (first word's) top position, not min of all words
            max_height = max(line_max_height, word_height)
            tolerance = max(5, max_height * 0.25)  # 25% of max height in line
            
            if abs(word['top'] - line_reference_top) <= tolerance:
                # Same line - add word
                current_line.append(word)
                line_max_height = max(line_max_height, word_height)
            else:
                # New line - save current and start new
                lines.append(current_line)
                current_line = [word]
                line_reference_top = word['top']
                line_max_height = word_height
        
        # Don't forget the last line
        if current_line:
            lines.append(current_line)
        
        logger.info(f"Grouped words into {len(lines)} lines")
        
        # Build text with layout preservation
        result_lines = []
        prev_line_bottom = None
        
        for line_idx, line_words in enumerate(lines):
            # Sort words in line by horizontal position (left to right)
            line_words.sort(key=lambda x: x['left'])
            
            # Calculate line metrics
            line_top = min(w['top'] for w in line_words)
            line_bottom = max(w['bottom'] for w in line_words)
            line_height = line_bottom - line_top
            
            # Check for paragraph break (larger vertical gap)
            if prev_line_bottom is not None:
                gap = line_top - prev_line_bottom
                # Paragraph break if gap is more than 1.5x line height
                if gap > line_height * 1.5:
                    result_lines.append('')  # Empty line for paragraph break
                    logger.debug(f"Paragraph break detected (gap={gap:.1f}, height={line_height:.1f})")
            
            # Join words with spaces, handling punctuation
            line_text = ''
            for i, word in enumerate(line_words):
                if i == 0:
                    line_text = word['text']
                else:
                    # Check if punctuation that should attach to previous word
                    if word['text'][0] in '.,;:!?)]}\'"':
                        line_text += word['text']
                    # Check if opening punctuation that next word should attach to
                    elif line_text and line_text[-1] in '([{\'"':
                        line_text += word['text']
                    else:
                        line_text += ' ' + word['text']
            
            result_lines.append(line_text)
            logger.debug(f"Line {line_idx + 1}: {len(line_words)} words, text length={len(line_text)}")
            prev_line_bottom = line_bottom
        
        text = '\n'.join(result_lines)
        conf = sum(confs) / len(confs) if confs else 0
        
        logger.info(f"Layout extraction complete: {len(text)} chars, {len(result_lines)} lines, conf={conf:.2f}%")
        
        return text, conf
        
    except Exception as e:
        logger.error(f"Layout extraction failed: {str(e)}", exc_info=True)
        return "", 0.0


def _run(img, lang_string, config_override=None):
    """
    Tesseract with optimal configuration
    
    PSM modes:
    - PSM 3: Fully automatic page segmentation (best for mixed content)
    - PSM 4: Single column of text (newspapers, books)
    - PSM 6: Uniform block of text (best for clean books)
    - PSM 11: Sparse text (for noisy images)
    - PSM 12: Sparse text with OSD
    
    OEM modes:
    - OEM 1: LSTM neural nets only (BEST for English)
    - OEM 3: Legacy + LSTM (BEST for Bangla and other Unicode scripts)
    """
    
    if config_override:
        config = config_override
    else:
        # Default to OEM 3 for better multi-script support
        config = "--oem 3 --psm 6"
    
    try:
        # Use standard Tesseract image_to_string - reliable and simple
        text = pytesseract.image_to_string(
            img,
            lang=lang_string,
            config=config
        )
        
        # Get confidence separately
        data = pytesseract.image_to_data(
            img,
            lang=lang_string,
            config=config,
            output_type=Output.DICT
        )
        
        confs = [
            int(c) for c in data["conf"]
            if c != "-1" and int(c) > 0
        ]
        
        conf = sum(confs) / len(confs) if confs else 0
        
        # Clean up text
        text = text.strip()
        
        return text, conf
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Tesseract extraction failed: {str(e)}")
        return "", 0.0


def _run_with_preprocessing_variants(img, lang_string, config):
    """
    Try multiple preprocessing variants and return best result
    """
    results = []
    
    # Original image
    text1, conf1 = _run(img, lang_string, config)
    results.append((text1, conf1))
    
    # Try with slight blur (reduces noise)
    try:
        blurred = cv2.GaussianBlur(img, (3, 3), 0)
        text2, conf2 = _run(blurred, lang_string, config)
        results.append((text2, conf2))
    except:
        pass
    
    # Try with sharpening
    try:
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(img, -1, kernel)
        text3, conf3 = _run(sharpened, lang_string, config)
        results.append((text3, conf3))
    except:
        pass
    
    # Return best
    if results:
        return max(results, key=lambda x: x[1])
    return "", 0.0


def _maybe_upsample_for_bengali(img, langs):
    """
    Upsample low-resolution pages to boost Bangla character fidelity.
    Optimized for speed while maintaining quality.
    """
    if "bn" not in langs:
        return img

    try:
        if isinstance(img, Image.Image):
            w, h = img.size
        else:
            h, w = img.shape[:2]
    except Exception:
        return img

    max_dim = max(h, w)
    # Reduced from 2400 to 2000 for faster processing
    if max_dim >= 2000:
        return img

    scale = min(2.0, 2000.0 / max_dim)  # Reduced from 2.5 to 2.0

    try:
        if isinstance(img, Image.Image):
            new_size = (int(w * scale), int(h * scale))
            # Use LANCZOS for better quality
            return img.resize(new_size, Image.LANCZOS)
        new_w, new_h = int(w * scale), int(h * scale)
        # Use LANCZOS4 for better quality
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    except Exception:
        return img


def _detect_english_with_easyocr(img, langs, use_ocrmypdf=False):
    """
    Use EasyOCR to validate whether English text genuinely exists in Bangla-heavy pages.
    Returns detected English tokens and their confidence to drive ensemble filtering.
    """

    if "bn" not in langs:
        return None

    try:
        target_langs = []
        if "bn" in langs:
            target_langs.append("bn")
        if "en" in langs:
            target_langs.append("en")

        # Always include English so we can verify or refute its presence
        if "en" not in target_langs:
            target_langs.append("en")

        prepared_img = preprocess_with_ocrmypdf_easyocr(img, target_langs) if use_ocrmypdf else img
        reader = get_reader(target_langs)
        detections = reader.readtext(prepared_img, **EASYOCR_PARAMS)

        english_tokens = []
        english_confs = []
        aggregated_tokens = []

        for detection in detections:
            if len(detection) == 3:
                _, text, confidence = detection
            elif len(detection) == 2:
                text, confidence = detection
            else:
                continue

            text_stripped = text.strip()
            if not text_stripped:
                continue

            confidence = float(confidence)
            aggregated_tokens.append(text_stripped)

            if re.search(r"[A-Za-z]", text_stripped):
                english_tokens.append(text_stripped)
                english_confs.append(confidence * 100)

        english_conf = sum(english_confs) / len(english_confs) if english_confs else 0.0

        return {
            "has_english": bool(english_tokens),
            "english_tokens": english_tokens,
            "english_conf": english_conf,
            "raw_text": " ".join(aggregated_tokens)
        }
    except Exception:
        return None


def _strip_english_tokens(text):
    tokens = text.split()
    filtered = [t for t in tokens if not re.search(r"[A-Za-z]", t)]
    return " ".join(filtered).strip()


def _merge_english_tokens(base_text, english_candidates):
    if not english_candidates:
        return base_text

    english_iter = iter(english_candidates)
    merged = []

    for token in base_text.split():
        if re.search(r"[A-Za-z]", token):
            replacement = next(english_iter, None)
            merged.append(replacement if replacement else token)
        else:
            merged.append(token)

    # Append any remaining EasyOCR English tokens
    merged.extend(list(english_iter))
    return " ".join(merged).strip()


def _apply_easyocr_ensemble(text, langs, easyocr_info):
    """
    Blend Tesseract output with EasyOCR signals to suppress hallucinated English
    inside Bangla pages while keeping real English when confirmed.
    AGGRESSIVE filtering for Bangla-only mode.
    """

    if not text or not easyocr_info:
        return text

    if "bn" not in langs:
        return text

    # If English is not in requested languages at all, aggressively filter
    if "en" not in langs:
        return _filter_hallucinated_english(text, langs)

    if not re.search(r"[A-Za-z]", text):
        return text

    tokens = text.split()
    english_token_count = len([t for t in tokens if re.search(r"[A-Za-z]", t)])
    total_tokens = len(tokens)

    english_confirmed = (
        easyocr_info.get("has_english", False)
        and easyocr_info.get("english_conf", 0.0) >= EASYOCR_ENGLISH_CONF_THRESHOLD
    )

    # In mixed Bangla+English mode, be more conservative about English
    if not english_confirmed and total_tokens > 0:
        english_ratio = english_token_count / total_tokens
        # Stricter threshold - remove English if it's less than 30% of content
        if english_ratio <= 0.3:
            return _strip_english_tokens(text)

    # When English is confirmed, prefer EasyOCR's tokens over Tesseract's English guesses
    if english_confirmed:
        return _merge_english_tokens(text, easyocr_info.get("english_tokens", []))

    return text


def _sharpen_and_denoise(img):
    """Apply light denoising and unsharp masking to help recover faint strokes."""
    try:
        if isinstance(img, Image.Image):
            img_np = np.array(img)
        else:
            img_np = img

        if img_np is None:
            return img

        # Light denoise
        denoised = cv2.fastNlMeansDenoisingColored(img_np, None, 5, 5, 7, 21)

        # Unsharp mask
        blur = cv2.GaussianBlur(denoised, (0, 0), 1.2)
        sharpened = cv2.addWeighted(denoised, 1.5, blur, -0.5, 0)

        return sharpened
    except Exception:
        return img

def preprocess_with_ocrmypdf(img, langs):
    # Get oversample DPI from environment or use default
    oversample_dpi = int(os.getenv("OCRMYPDF_OVERSAMPLE_DPI", 600))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save image as temporary PDF
        input_img_path = Path(tmpdir) / "input.png"
        output_pdf_path = Path(tmpdir) / "preprocessed.pdf"
        
        # Convert numpy array to PIL Image if needed
        if isinstance(img, np.ndarray):
            img_pil = Image.fromarray(img)
        else:
            img_pil = img
        
        # Save as PNG with maximum quality
        img_pil.save(input_img_path, compress_level=0)
        
        try:
            # Build language string for ocrmypdf
            lang_codes = [LANG_MAP.get(l, l) for l in langs]
            lang_string = "+".join(lang_codes)
            
            # Use ocrmypdf for maximum quality preprocessing
            ocrmypdf.ocr(
                input_img_path,
                output_pdf_path,
                language=lang_string,
                
                deskew=True,                    # Auto-deskew pages
                clean=True,                     # Clean artifacts
                clean_final=True,               # Final cleanup pass
                remove_background=True,         # Remove background noise
                rotate_pages=True,              # Auto-rotate pages
                
                optimize=3,                     # Maximum optimization level
                jpeg_quality=95,                # High JPEG quality
                png_quality=95,                 # High PNG quality
                jbig2_lossy=False,             # Lossless compression
                pdfa_image_compression='lossless',  # Lossless PDF/A
                
                oversample=oversample_dpi,      # Use configured DPI for sharper Bangla glyphs
                remove_vectors=False,           # Keep vector graphics
                
                output_type='pdf',
                redo_ocr=True,                  # Force re-OCR
                force_ocr=True,                 # OCR even if text exists
                skip_text=True,                 # Skip existing text layer
                
                use_threads=True,               # Multi-threading
                tesseract_timeout=300,          # 5 min timeout
                
                invalidate_digital_signatures=True,
                quiet=True,
                progress_bar=False
            )
            
            # Convert preprocessed PDF back to image at same DPI as oversample
            from pdf2image import convert_from_path
            images = convert_from_path(str(output_pdf_path), dpi=oversample_dpi)
            
            if images:
                # Convert back to numpy array
                return np.array(images[0])
            else:
                return np.array(img_pil)
                
        except Exception as e:
            # Fallback to original image if ocrmypdf fails
            return np.array(img_pil)


def fix_common_ocr_errors(text, langs, mode="english"):
    """
    Fix common OCR errors without breaking compound words
    Also applies mode-based hallucination filtering
    """
    if not text:
        return text
    
    # Apply hallucination filtering based on mode
    if mode == "bangla":
        # Bangla-only mode: aggressive English filtering
        text = _filter_hallucinated_english(text, ["bn"])
    elif mode == "english":
        # English-only mode: no filtering needed
        pass
    elif mode == "mixed":
        # Mixed mode: minimal filtering, preserve both languages
        # Only filter if we're sure it's hallucination
        pass
    
    return text.strip()
    
    return text.strip()


def run_tesseract(img, langs, use_ocrmypdf=True, mode="english"):

    # Upsample low-res pages for Bangla to improve stroke clarity
    img = _maybe_upsample_for_bengali(img, langs)

    # Only use OCRmyPDF preprocessing if confidence is expected to be low
    # Skip for faster processing on good quality images
    # This significantly speeds up processing
    if use_ocrmypdf:
        # Skip OCRmyPDF for small adjustments, only use for complex documents
        img = preprocess_with_ocrmypdf(img, langs)

    # Additional sharpening/denoise to retain final strokes (helps last-word dropouts)
    img = _sharpen_and_denoise(img)
    
    # Detect column layout
    column_layout = detect_column_layout(img)
    
    results = []
    
    # Build language string
    lang_codes = [LANG_MAP.get(l, l) for l in langs]
    lang_string = "+".join(lang_codes)
    
    is_bengali = 'bn' in langs
    is_english = 'en' in langs
    is_mixed = is_bengali and is_english

    if is_mixed:
        primary_config = TESSERACT_CONFIGS["mixed_multi" if column_layout == 'multi' else "mixed_single"]
    elif is_bengali:
        primary_config = TESSERACT_CONFIGS["bengali_multi" if column_layout == 'multi' else "bengali_single"]
    elif is_english:
        primary_config = TESSERACT_CONFIGS["english_multi" if column_layout == 'multi' else "english_single"]
    else:
        primary_config = "--oem 1 --psm 6 -c preserve_interword_spaces=1"

    if is_mixed:
        auto_config = TESSERACT_CONFIGS["mixed_auto"]
    elif is_bengali:
        auto_config = TESSERACT_CONFIGS["bengali_auto"]
    elif is_english:
        auto_config = TESSERACT_CONFIGS["english_auto"]
    else:
        auto_config = "--oem 1 --psm 3 -c preserve_interword_spaces=1"

    best_conf = 0.0
    easy_text = None
    easy_conf = 0.0

    with ThreadPoolExecutor(max_workers=OCR_ENGINE_MAX_WORKERS) as executor:
        # Start with only primary config for faster processing
        tasks = [
            (f"Primary-{column_layout}", executor.submit(_run, img, lang_string, primary_config)),
        ]

        # Collect initial result
        for label, fut in tasks:
            text, conf = fut.result()
            results.append((text, conf, label))

        best_conf = max((c for _, c, _ in results), default=0)

        # Early exit if confidence is good enough - saves significant time
        if best_conf >= 85:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Early exit: high confidence {best_conf:.2f}% achieved with primary config")
        else:
            # Only try additional strategies if confidence is low
            more_tasks = [("Auto", executor.submit(_run, img, lang_string, auto_config))]
            
            if best_conf < 80:
                more_tasks.append(("Enhanced", executor.submit(_run_with_preprocessing_variants, img, lang_string, primary_config)))
            
            if best_conf < 70:
                more_tasks.append(("PSM4", executor.submit(_run, img, lang_string, "--oem 3 --psm 4 -c preserve_interword_spaces=1")))
            
            if best_conf < 60 and is_bengali:
                # Additional pass with PSM 13 (raw line) for very low confidence Bangla
                more_tasks.append(("RawLine", executor.submit(_run, img, lang_string, "--oem 3 --psm 13 -c preserve_interword_spaces=1")))

            for label, fut in more_tasks:
                text, conf = fut.result()
                results.append((text, conf, label))

        easy_future = None
        # Only use EasyOCR if Tesseract confidence is low or for Bangla
        if is_bengali and best_conf < 90:
            easy_future = executor.submit(run_easyocr, img, langs, False, mode)  # Skip OCRmyPDF in EasyOCR

        # Collect EasyOCR result in parallel for Bangla
        if easy_future:
            try:
                easy_text, easy_conf = easy_future.result()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"EasyOCR future failed: {str(e)}")
                easy_text, easy_conf = None, 0.0

    if results:
        import logging
        logger = logging.getLogger(__name__)
        
        # Filter results: only consider those with actual text content
        valid_results = [(t, c, m) for t, c, m in results if t and len(t.strip()) > 0]
        
        if valid_results:
            best_text, best_conf, best_method = max(valid_results, key=lambda x: x[1])
        else:
            best_text, best_conf, best_method = "", 0.0, "Empty"
        
        logger.info(f"Best Tesseract result ({best_method}): {len(best_text)} chars, conf={best_conf:.2f}%")
        logger.info(f"Text preview: {best_text[:200]}..." if len(best_text) > 200 else f"Full text: {best_text}")
        
        # Validate English presence in Bangla pages using EasyOCR to avoid hallucinated mix
        if best_text and mode in ["bangla", "mixed"]:
            easyocr_info = _detect_english_with_easyocr(img, langs, use_ocrmypdf=False)
            if mode == "bangla":
                # Bangla-only: aggressive filtering
                best_text = _apply_easyocr_ensemble(best_text, ["bn"], easyocr_info)
            elif mode == "mixed":
                # Mixed mode: balanced filtering
                best_text = _apply_easyocr_ensemble(best_text, langs, easyocr_info)

        # Bangla accuracy ensemble: compare with EasyOCR full pass and pick stronger signal
        if 'bn' in langs and mode in ["bangla", "mixed"]:
            try:
                if easy_text is None:
                    logger.info(f"Running EasyOCR ensemble for Bangla (mode: {mode})...")
                    easy_text, easy_conf = run_easyocr(img, langs, use_ocrmypdf=True, mode=mode)
                logger.info(f"EasyOCR result: {len(easy_text) if easy_text else 0} chars, conf={easy_conf:.2f}%")
                if easy_text:
                    logger.info(f"EasyOCR preview: {easy_text[:200]}..." if len(easy_text) > 200 else f"EasyOCR full: {easy_text}")

                # CRITICAL: If Tesseract is empty but EasyOCR has text, use EasyOCR
                if (not best_text or len(best_text.strip()) == 0) and easy_text and len(easy_text.strip()) > 0:
                    logger.info(f"Using EasyOCR (Tesseract returned empty, EasyOCR has {len(easy_text)} chars)")
                    best_text, best_conf = easy_text, easy_conf
                # Prefer EasyOCR if clearly stronger or Tesseract confidence is low
                elif easy_text and easy_conf > best_conf + 2:
                    logger.info(f"Using EasyOCR (conf {easy_conf:.2f}% > {best_conf:.2f}% + 2)")
                    best_text, best_conf = easy_text, easy_conf
                elif easy_text and best_conf < 85 and easy_conf >= best_conf - 2:
                    logger.info(f"Using EasyOCR (Tesseract weak: {best_conf:.2f}% < 85, EasyOCR comparable: {easy_conf:.2f}%)")
                    best_text, best_conf = easy_text, easy_conf
                elif easy_text and len(easy_text.strip()) > len(best_text.strip()) * 2 and easy_conf >= 50:
                    logger.info(f"Using EasyOCR (has {len(easy_text)} chars vs Tesseract's {len(best_text)} chars)")
                    best_text, best_conf = easy_text, easy_conf
                else:
                    logger.info(f"Keeping Tesseract result (conf={best_conf:.2f}% vs EasyOCR {easy_conf:.2f}%)")
            except Exception as e:
                logger.error(f"EasyOCR ensemble failed: {str(e)}")
                pass

        # Apply minimal targeted fixes (mode-aware filtering)
        best_text = fix_common_ocr_errors(best_text, langs, mode)
        
        logger.info(f"Final result: {len(best_text)} chars, conf={best_conf:.2f}%")
        logger.info(f"Final preview: {best_text[:200]}..." if len(best_text) > 200 else f"Final text: {best_text}")
        
        return best_text, best_conf
    
    return "", 0.0
