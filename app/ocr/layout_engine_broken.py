import logging
import re
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image


logger = logging.getLogger(__name__)

# Bangla Unicode range: \u0980-\u09FF
BANGLA_PATTERN = re.compile(r'[\u0980-\u09FF]')
ENGLISH_PATTERN = re.compile(r'[A-Za-z]')


def _filter_hallucinated_english(text: str, langs: List[str], mode: str = "english") -> str:
    """
    AGGRESSIVE filter for hallucinated English in layout blocks.
    For Bangla-only mode, removes virtually all English text except essential numbers.
    """
    if not text:
        return text

    # If English is requested, keep everything
    if 'en' in langs:
        return text

    # Check if this is Bangla-only mode
    if 'bn' not in langs:
        return text

    if 'en' in langs:  # Mixed mode - less aggressive
        return text

    # Bangla-only mode - VERY aggressive filtering
    tokens = text.split()
    filtered_tokens = []

    for token in tokens:
        has_bangla = bool(BANGLA_PATTERN.search(token))
        has_english = bool(ENGLISH_PATTERN.search(token))

        # Keep token if:
        # 1. It has Bangla characters (even if mixed)
        # 2. It's purely numeric
        # 3. It's punctuation only
        if has_bangla:
            if has_english:
                # Mixed token: remove English chars if they're < 30% of the token
                bangla_chars = len(re.findall(r'[\u0980-\u09FF]', token))
                english_chars = len(re.findall(r'[A-Za-z]', token))
                
                if english_chars / (bangla_chars + english_chars) > 0.3:
                    # Too much English, strip it
                    cleaned = re.sub(r'[A-Za-z]', '', token)
                    if cleaned.strip():
                        filtered_tokens.append(cleaned)
                else:
                    filtered_tokens.append(token)
            else:
                filtered_tokens.append(token)
        elif not has_english:
            # Numbers, punctuation, etc. - keep
            if re.match(r'^[\\d\\u09e6-\\u09ef.,;:!?()\\[\\]{}\"\'_\\-\\s]+$', token):
                filtered_tokens.append(token)
        # Skip pure English tokens entirely

    return ' '.join(filtered_tokens).strip()

_layout_model = None


def _get_layout_model(score_thresh: float = 0.5):
    """Lazy-load Detectron2 PubLayNet model for layout detection."""

    global _layout_model

    if _layout_model is not None:
        return _layout_model

    try:
        import layoutparser as lp
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "layoutparser is required for layout-aware OCR. Install with "
            "`pip install \"layoutparser[layoutmodels]\"` and the matching "
            "detectron2 wheel for your PyTorch/CUDA version."
        ) from exc

    try:
        # Try different ways to access Detectron2LayoutModel
        if hasattr(lp, 'Detectron2LayoutModel'):
            _layout_model = lp.Detectron2LayoutModel(
                "lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config",
                extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", score_thresh],
                label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"},
            )
        elif hasattr(lp.models, 'Detectron2LayoutModel'):
            _layout_model = lp.models.Detectron2LayoutModel(
                "lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config",
                extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", score_thresh],
                label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"},
            )
        else:
            raise AttributeError("Detectron2LayoutModel not found")
    except Exception as exc:  # pragma: no cover - model load errors
        raise RuntimeError(
            "Failed to load PubLayNet Detectron2 model. This likely means:\n"
            "1. detectron2 is not installed for your PyTorch/CUDA version\n"
            "2. layoutparser was installed without detectron2 support\n"
            "3. Install detectron2 first: see https://detectron2.readthedocs.io/en/latest/tutorials/install.html\n"
            "4. Then reinstall layoutparser: pip install 'layoutparser[layoutmodels]'"
        ) from exc

    return _layout_model


def _to_rgb_np(img) -> np.ndarray:
    """Normalize input image to RGB numpy array."""

    if isinstance(img, Image.Image):
        return np.array(img.convert("RGB"))

    if isinstance(img, np.ndarray):
        if img.ndim == 2:  # grayscale
            return np.stack([img] * 3, axis=-1)
        if img.shape[2] == 4:  # RGBA
            return img[..., :3]
        return img

    raise ValueError("Unsupported image type for layout parsing")


def _format_block_text(block_type: str, text: str) -> str:
    """
    Format text based on block type for proper document structure.
    """
    text = text.strip()
    if not text:
        return ""

    if block_type == "Title":
        # Titles get emphasis (uppercase or markdown-style)
        return f"# {text}"
    elif block_type == "List":
        # Format as bullet points if not already
        lines = text.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith(('•', '-', '*', '১', '২', '৩', '৪', '৫', '৬', '৭', '৮', '৯', '০', '1', '2', '3', '4', '5', '6', '7', '8', '9')):
                formatted_lines.append(f"• {line}")
            elif line:
                formatted_lines.append(line)
        return '\n'.join(formatted_lines)
    elif block_type == "Table":
        # Tables get clear separation
        return f"[TABLE]\n{text}\n[/TABLE]"
    else:
        # Regular text paragraphs
        return text


def extract_layout_text(img, langs, mode="english", score_thresh: float = 0.5) -> Tuple[str, float, List[Dict]]:
    """Detect layout blocks and run OCR per block to preserve reading order."""

    from app.ocr.easyocr_engine import run_easyocr

    image_np = _to_rgb_np(img)
    
    try:
        model = _get_layout_model(score_thresh)

    logger.info("Running layout detection (PubLayNet)...")
    layout = model.detect(image_np)

    allowed_types = {"Text", "Title", "List", "Table"}
    blocks = [b for b in layout if b.type in allowed_types]
    
    # Sort by vertical position first (top to bottom), then horizontal (left to right)
    # Group blocks into rows based on Y overlap for multi-column handling
    blocks = sorted(blocks, key=lambda b: (b.block.y_1, b.block.x_1))

    block_results: List[Dict] = []
    collected_texts: List[str] = []
    confs: List[float] = []

    for idx, block in enumerate(blocks, 1):
        cropped = block.crop_image(image_np)
        text, conf = run_easyocr(cropped, langs, use_ocrmypdf=False)

        if not text:
            continue

        # Apply mode-based filtering
        if mode == "bangla":
            # Aggressive filtering for Bangla-only mode
            text = _filter_hallucinated_english(text, ["bn"])
        elif mode == "english":
            # No filtering for English-only mode
            pass
        elif mode == "mixed":
            # Light filtering for mixed mode (preserve intentional English)
            text = _filter_hallucinated_english(text, ["bn", "en"])
        
        if not text:
            continue
        
        if not text:
            continue

        # Format text based on block type
        formatted_text = _format_block_text(block.type, text)

        block_dict = {
            "index": idx,
            "type": block.type,
            "bbox": [
                float(block.block.x_1),
                float(block.block.y_1),
                float(block.block.x_2),
                float(block.block.y_2),
            ],
            "score": float(block.score),
            "text": text,
            "formatted_text": formatted_text,
            "confidence": float(conf),
        }

        block_results.append(block_dict)
        collected_texts.append(formatted_text)
        confs.append(float(conf))

    # Join with appropriate spacing based on block types
    combined_text = "\n\n".join(collected_texts)
    
    # Clean up excessive whitespace while preserving paragraph breaks
    combined_text = re.sub(r'\n{3,}', '\n\n', combined_text)
    combined_text = re.sub(r' {2,}', ' ', combined_text)

    avg_conf = sum(confs) / len(confs) if confs else 0.0

    return combined_text, avg_conf, block_results
