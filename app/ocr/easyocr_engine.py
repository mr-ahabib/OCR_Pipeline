import easyocr
import numpy as np
import ocrmypdf
import tempfile
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


def _resize_for_ocr(img, target_max_dim=2500):
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
    # Resize large images first to prevent memory issues
    img = _resize_for_ocr(img, target_max_dim=2500)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        input_img_path = Path(tmpdir) / "input.png"
        output_pdf_path = Path(tmpdir) / "preprocessed.pdf"

        if isinstance(img, np.ndarray):
            img_pil = Image.fromarray(img)
        else:
            img_pil = img

        img_pil.save(input_img_path)

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
                oversample=400,
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
            images = convert_from_path(str(output_pdf_path), dpi=400)

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


def run_easyocr(img, langs, use_ocrmypdf=True):
    """Run EasyOCR with optional preprocessing and conservative filtering."""
    import logging
    logger = logging.getLogger(__name__)
    
    if use_ocrmypdf:
        logger.info("Preprocessing image with OCRmyPDF for EasyOCR...")
        img = preprocess_with_ocrmypdf_easyocr(img, langs)

    reader = get_reader(langs)
    
    logger.info(f"Running EasyOCR with languages: {langs}")

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

    texts = []
    confs = []

    for detection in result:
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

        if confidence < 0.5:
            continue

        if len(text_stripped) <= 2 and confidence < 0.7:
            continue

        if text_stripped in '.,;:!?-()[]{}"\'' and confidence < 0.7:
            continue

        texts.append(text_stripped)
        confs.append(confidence * 100)

    if texts:
        final_text = ""
        for i, text in enumerate(texts):
            if i == 0:
                final_text = text
            elif text in '.,;:!?)]}\'"':
                final_text += text
            elif final_text and final_text[-1] in '([{\'"':
                final_text += text
            else:
                final_text += " " + text
    else:
        final_text = ""

    if confs:
        avg_conf = sum(confs) / len(confs)
    else:
        avg_conf = 0.0

    return final_text, avg_conf
