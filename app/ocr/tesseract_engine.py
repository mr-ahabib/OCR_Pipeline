import pytesseract
from pytesseract import Output
from app.config import settings
import numpy as np
import cv2

pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


# ==================================================
# Language mapping
# ==================================================
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

# ==================================================
# Tesseract configuration presets for maximum accuracy
# ==================================================
TESSERACT_CONFIGS = {
    # Bengali configurations
    "bengali_book": "--oem 1 --psm 6 -c preserve_interword_spaces=1",
    "bengali_auto": "--oem 1 --psm 3 -c preserve_interword_spaces=1",
    "bengali_column": "--oem 1 --psm 4 -c preserve_interword_spaces=1",
    "bengali_block": "--oem 1 --psm 6 -c tessedit_pageseg_mode=6",
    
    # English configurations
    "english_book": "--oem 1 --psm 6 -c preserve_interword_spaces=1",
    "english_auto": "--oem 1 --psm 3",
    "english_column": "--oem 1 --psm 4",
    "english_sparse": "--oem 1 --psm 11",
    
    # High accuracy configs
    "high_accuracy": "--oem 1 --psm 6 -c tessedit_char_blacklist=|~`",
    "max_accuracy": "--oem 1 --psm 6 -c preserve_interword_spaces=1 -c tessedit_char_blacklist=|~`@#$%^&*",
}


# ==================================================
# Internal runner with optimized configs
# ==================================================
def _run(img, lang_string, config_override=None):
    """
    Run Tesseract with optimal configuration
    
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
        data = pytesseract.image_to_data(
            img,
            lang=lang_string,
            config=config,
            output_type=Output.DICT
        )

        words = [t.strip() for t in data["text"] if t.strip()]
        text = " ".join(words)

        confs = [
            int(c) for c in data["conf"]
            if c != "-1" and int(c) > 0
        ]

        conf = sum(confs) / len(confs) if confs else 0
        
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


# ==================================================
# Multi-pass strategy for MAXIMUM accuracy
# ==================================================
def run_tesseract(img, langs):
    """
    Ultra-enhanced multi-pass strategy for maximum accuracy:
    
    For Bengali:
      1) Bengali book mode (PSM 6) - best for uniform text
      2) Bengali auto mode (PSM 3) - for complex layouts
      3) Bengali column mode (PSM 4) - for single columns
      4) Bengali with preprocessing variants
      
    For English:
      1) English book mode (PSM 6) - best for books
      2) English auto mode (PSM 3) - for mixed content
      3) English with sharpening
      4) High accuracy mode with blacklist
      
    Returns best result from all attempts
    """

    results = []
    
    # Build language string
    lang_codes = [LANG_MAP.get(l, l) for l in langs]
    lang_string = "+".join(lang_codes)
    
    is_bengali = 'bn' in langs
    is_english = 'en' in langs
    
    # ============================================================
    # BENGALI PROCESSING (Maximum Accuracy)
    # ============================================================
    if is_bengali:
        
        # Pass 1: Bengali book mode (BEST for printed books)
        text, conf = _run(img, "ben", TESSERACT_CONFIGS["bengali_book"])
        results.append((text, conf, "Bengali-Book"))
        
        # Pass 2: Bengali auto segmentation
        if conf < 90:
            text2, conf2 = _run(img, "ben", TESSERACT_CONFIGS["bengali_auto"])
            results.append((text2, conf2, "Bengali-Auto"))
        
        # Pass 3: Bengali column mode (for single columns)
        if conf < 85:
            text3, conf3 = _run(img, "ben", TESSERACT_CONFIGS["bengali_column"])
            results.append((text3, conf3, "Bengali-Column"))
        
        # Pass 4: High accuracy mode
        if conf < 85:
            text4, conf4 = _run(img, "ben", TESSERACT_CONFIGS["max_accuracy"])
            results.append((text4, conf4, "Bengali-MaxAccuracy"))
        
        # Pass 5: Try with preprocessing variants
        if conf < 80:
            text5, conf5 = _run_with_preprocessing_variants(img, "ben", TESSERACT_CONFIGS["bengali_book"])
            results.append((text5, conf5, "Bengali-Variants"))
        
        # Pass 6: Bengali block mode
        if conf < 75:
            text6, conf6 = _run(img, "ben", TESSERACT_CONFIGS["bengali_block"])
            results.append((text6, conf6, "Bengali-Block"))
    
    # ============================================================
    # ENGLISH PROCESSING (Maximum Accuracy)
    # ============================================================
    if is_english and not is_bengali:
        
        # Pass 1: English book mode (BEST for printed books)
        text, conf = _run(img, "eng", TESSERACT_CONFIGS["english_book"])
        results.append((text, conf, "English-Book"))
        
        # Pass 2: English auto mode
        if conf < 90:
            text2, conf2 = _run(img, "eng", TESSERACT_CONFIGS["english_auto"])
            results.append((text2, conf2, "English-Auto"))
        
        # Pass 3: High accuracy mode
        if conf < 85:
            text3, conf3 = _run(img, "eng", TESSERACT_CONFIGS["high_accuracy"])
            results.append((text3, conf3, "English-HighAccuracy"))
        
        # Pass 4: English column mode
        if conf < 85:
            text4, conf4 = _run(img, "eng", TESSERACT_CONFIGS["english_column"])
            results.append((text4, conf4, "English-Column"))
        
        # Pass 5: With preprocessing variants
        if conf < 80:
            text5, conf5 = _run_with_preprocessing_variants(img, "eng", TESSERACT_CONFIGS["english_book"])
            results.append((text5, conf5, "English-Variants"))
        
        # Pass 6: Sparse text (for noisy images)
        if conf < 70:
            text6, conf6 = _run(img, "eng", TESSERACT_CONFIGS["english_sparse"])
            results.append((text6, conf6, "English-Sparse"))
    
    # ============================================================
    # MIXED LANGUAGE (Bengali + English)
    # ============================================================
    if is_bengali and is_english:
        
        # Try combined with different modes
        text_mix, conf_mix = _run(img, "ben+eng", TESSERACT_CONFIGS["bengali_book"])
        results.append((text_mix, conf_mix, "Mixed-Book"))
        
        if conf_mix < 85:
            text_mix2, conf_mix2 = _run(img, "ben+eng", TESSERACT_CONFIGS["bengali_auto"])
            results.append((text_mix2, conf_mix2, "Mixed-Auto"))
    
    # ============================================================
    # SCRIPT DETECTION FALLBACK
    # ============================================================
    if not results or max(r[1] for r in results) < 50:
        script_codes = [SCRIPT_MAP.get(l, l) for l in langs]
        script_string = "+".join(script_codes)
        
        s_text, s_conf = _run(img, script_string, "--oem 1 --psm 3")
        results.append((s_text, s_conf, "Script-Fallback"))
    
    # ============================================================
    # SELECT BEST RESULT
    # ============================================================
    if results:
        best_text, best_conf, best_method = max(results, key=lambda x: x[1])
        return best_text, best_conf
    
    return "", 0.0
