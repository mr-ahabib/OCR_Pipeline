import pytesseract
from pytesseract import Output
from app.config import settings
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
    # Bengali configurations - allow natural English mixing
    "bengali_single": "--oem 1 --psm 6 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1",
    "bengali_multi": "--oem 1 --psm 1 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1",
    "bengali_auto": "--oem 1 --psm 3 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1",
    
    # English configurations
    "english_single": "--oem 1 --psm 6 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1",
    "english_multi": "--oem 1 --psm 1 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1",
    "english_auto": "--oem 1 --psm 3 -c preserve_interword_spaces=1 -c tessedit_preserve_min_wd_len=1",
    
    # Mixed language configurations
    "mixed_single": "--oem 1 --psm 6 -c preserve_interword_spaces=1",
    "mixed_multi": "--oem 1 --psm 1 -c preserve_interword_spaces=1",
    "mixed_auto": "--oem 1 --psm 3 -c preserve_interword_spaces=1",
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
    - OEM 1: LSTM neural nets only (BEST for accuracy)
    - OEM 3: Default (both legacy + LSTM)
    """
    
    if config_override:
        config = config_override
    else:
        config = "--oem 1 --psm 6"
    
    try:
        # Use image_to_string for better punctuation preservation
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
        
        # Clean up text while preserving punctuation
        text = text.strip()
        # Remove excessive whitespace but preserve single spaces
        text = ' '.join(text.split())
        
        return text, conf
    except Exception as e:
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
    Keeps scale conservative to avoid noise amplification.
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
    if max_dim >= 1800:
        return img

    scale = min(2.0, 1800.0 / max_dim)

    try:
        if isinstance(img, Image.Image):
            new_size = (int(w * scale), int(h * scale))
            return img.resize(new_size, Image.BICUBIC)
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
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

    with tempfile.TemporaryDirectory() as tmpdir:
        # Save image as temporary PDF
        input_img_path = Path(tmpdir) / "input.png"
        output_pdf_path = Path(tmpdir) / "preprocessed.pdf"
        
        # Convert numpy array to PIL Image if needed
        if isinstance(img, np.ndarray):
            img_pil = Image.fromarray(img)
        else:
            img_pil = img
        
        # Save as PNG
        img_pil.save(input_img_path)
        
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
                
                oversample=600,                 # Oversample to 500 DPI for sharper Bangla glyphs
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
            
            # Convert preprocessed PDF back to image
            from pdf2image import convert_from_path
            images = convert_from_path(str(output_pdf_path), dpi=600)
            
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

    # Preprocess with ocrmypdf if enabled
    if use_ocrmypdf:
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
        tasks = [
            (f"Primary-{column_layout}", executor.submit(_run, img, lang_string, primary_config)),
            ("Auto", executor.submit(_run, img, lang_string, auto_config)),
        ]

        easy_future = None
        if is_bengali:
            easy_future = executor.submit(run_easyocr, img, langs, True)

        # Collect base results
        for label, fut in tasks:
            text, conf = fut.result()
            results.append((text, conf, label))

        best_conf = max((c for _, c, _ in results), default=0)

        # Kick off additional strategies if early confidence is low
        more_tasks = []
        if best_conf < 90:
            more_tasks.append(("Enhanced", executor.submit(_run_with_preprocessing_variants, img, lang_string, primary_config)))
        if best_conf < 85:
            more_tasks.append(("PSM4", executor.submit(_run, img, lang_string, "--oem 1 --psm 4 -c preserve_interword_spaces=1")))
            more_tasks.append(("Sparse", executor.submit(_run, img, lang_string, "--oem 1 --psm 11 -c preserve_interword_spaces=1")))

        for label, fut in more_tasks:
            text, conf = fut.result()
            results.append((text, conf, label))

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
