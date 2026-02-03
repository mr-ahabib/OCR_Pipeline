import logging
import io
from PIL import Image

from app.utils.preprocessing import preprocess, preprocess_difficult
from app.utils.postprocessing import clean_text, remove_noise_patterns
from app.spell.spell_corrector import correct_spelling
from app.ocr.tesseract_engine import run_tesseract
from app.ocr.easyocr_engine import run_easyocr
from app.ocr.google_docai_engine import run_docai
from app.utils.pdf_utils import pdf_to_images
from app.config import settings


# =====================================================
# Logging
# =====================================================

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# =====================================================
# Process single page - MAXIMUM ACCURACY
# =====================================================

def process_page(image, langs, raw_bytes):
    """
    Process a single page with maximum accuracy strategy:
    1. Try standard preprocessing + Tesseract multi-pass
    2. If confidence < 80, try difficult preprocessing
    3. If still low, try EasyOCR (English only)
    4. Final fallback: DocAI
    """

    # -------------------------------------------------
    # 1️⃣ Standard preprocessing + Tesseract
    # -------------------------------------------------
    img = preprocess(image, langs)
    t_text, t_conf = run_tesseract(img, langs)
    
    logger.info(f"Tesseract confidence : {t_conf:.2f}")
    
    text, conf = t_text, t_conf

    # -------------------------------------------------
    # 2️⃣ If confidence is low, try difficult preprocessing
    # -------------------------------------------------
    if t_conf < 80:
        logger.info("Trying difficult preprocessing...")
        img_difficult = preprocess_difficult(image, langs)
        t_text2, t_conf2 = run_tesseract(img_difficult, langs)
        
        logger.info(f"Tesseract (difficult) : {t_conf2:.2f}")
        
        if t_conf2 > conf:
            text, conf = t_text2, t_conf2
            logger.info("Difficult preprocessing was better")

    # -------------------------------------------------
    # 3️⃣ EasyOCR for English only (Bengali skipped)
    # -------------------------------------------------
    if 'bn' not in langs:
        if conf < 85:
            e_text, e_conf = run_easyocr(img, langs)
            logger.info(f"EasyOCR confidence   : {e_conf:.2f}")

            if e_conf > conf:
                text, conf = e_text, e_conf
    else:
        logger.info("Skipping EasyOCR for Bengali (Tesseract is better)")

    logger.info(f"Final confidence     : {conf:.2f}")

    # -------------------------------------------------
    # 4️⃣ DocAI fallback (last resort)
    # -------------------------------------------------
    if conf < settings.CONFIDENCE_THRESHOLD:
        logger.warning("⚠️ Very low confidence → using DocAI fallback")
        logger.warning(text[:500])

        try:
            text = run_docai(raw_bytes)
            conf = 100.0
            logger.info("✅ DocAI used")
        except Exception as e:
            logger.error("DocAI failed — returning local OCR")
            logger.error(str(e))

    # -------------------------------------------------
    # 5️⃣ Postprocess - MAXIMUM ACCURACY
    # -------------------------------------------------
    text = clean_text(text)
    text = remove_noise_patterns(text, langs)
    text = correct_spelling(text, langs)

    return text, conf


# =====================================================
# Process file
# =====================================================

def process_file(file_bytes, langs):

    try:
        images = pdf_to_images(file_bytes)
        logger.info(f"PDF detected → {len(images)} pages")

    except Exception:
        images = [Image.open(io.BytesIO(file_bytes))]
        logger.info("Single image detected")

    texts = []
    confs = []

    for i, img in enumerate(images, 1):

        logger.info(f"========== Page {i} ==========")

        page_text, page_conf = process_page(img, langs, file_bytes)

        texts.append(page_text)
        confs.append(page_conf)

    avg_conf = sum(confs) / len(confs) if confs else 0

    logger.info(f"Average confidence : {avg_conf:.2f}")

    return {
        "text": "\n".join(texts),
        "confidence": avg_conf,
        "pages": len(images),
        "language": langs
    }
