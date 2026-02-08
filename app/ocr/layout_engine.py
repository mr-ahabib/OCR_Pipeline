"""
Layout-aware OCR engine using LayoutParser and Detectron2
"""
import os
import tempfile
import layoutparser as lp
import cv2
import numpy as np
from PIL import Image
import logging
from pathlib import Path

from .easyocr_engine import run_easyocr

logger = logging.getLogger(__name__)

class LayoutEngine:
    def __init__(self):
        pass
        
        # Initialize OCR and Layout models
        self.model = None
        try:
            # Try Detectron2 model first (most reliable)
            if lp.is_detectron2_available():
                self.model = lp.Detectron2LayoutModel(
                    "lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config",
                    extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.3]  # More lenient threshold
                )
                logger.info("Detectron2 LayoutParser model initialized successfully")
                self.layout_available = True
            else:
                # Try available TensorFlow models
                try:
                    self.model = lp.TensorflowLayoutModel(
                        "lp://efficientdet/PubLayNet",
                        model_path=None,
                        label_map={1: "Text", 2: "Title", 3: "List", 4: "Table", 5: "Figure"}
                    )
                    logger.info("TensorFlow LayoutParser model initialized successfully")
                    self.layout_available = True
                except Exception as tf_e:
                    logger.warning(f"TensorFlow model failed: {tf_e}")
                    raise Exception("No suitable layout model available")
        except Exception as e:
            logger.error(f"All layout models failed: {e}")
            logger.info("Layout detection disabled, will use comprehensive text positioning")
            self.model = None
            self.layout_available = False

    def extract_layout_text(self, image_input, mode="bangla"):
        """
        Extract text using layout-aware OCR with fallback to regular OCR
        
        Args:
            image_input (str|PIL.Image): Path to the image or PIL Image object
            mode (str): Language mode - ['bangla', 'english', 'mixed']
        
        Returns:
            dict: Extracted text with confidence
        """
        temp_file_path = None
        
        try:
            # Handle PIL Image input by saving to temp file
            if hasattr(image_input, 'save'):  # PIL Image
                temp_file_path = tempfile.mktemp(suffix=".png")
                image_input.save(temp_file_path)
                image_path = temp_file_path
            elif isinstance(image_input, (str, Path)):
                image_path = str(image_input)
            else:
                raise ValueError(f"image_input must be a string, Path, or PIL Image, got {type(image_input)}")
            
            if not self.layout_available:
                logger.warning("Layout detection not available, using comprehensive text extraction")
                # Use enhanced EasyOCR with better coverage
                lang_mapping = {"bangla": ["bn"], "english": ["en"], "mixed": ["en", "bn"]}
                langs = lang_mapping.get(mode, ["en"])
                
                # Get comprehensive results that capture all text
                result = self._extract_with_comprehensive_coverage(image_path, langs, mode)
                return result
            
            # Load and process image
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Could not load image: {image_path}")
            
            # Convert BGR to RGB
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Detect layout
            if self.model is None:
                raise ValueError("Layout model is not available")
                
            layout = self.model.detect(image)
            
            if not layout:
                logger.info("No layout detected, using comprehensive text extraction")
                # Use enhanced EasyOCR with better coverage
                lang_mapping = {"bangla": ["bn"], "english": ["en"], "mixed": ["en", "bn"]}
                langs = lang_mapping.get(mode, ["en"])
                
                # Get comprehensive results that capture all text
                result = self._extract_with_comprehensive_coverage(image_path, langs, mode)
                return result
            
            # Sort blocks by vertical position to maintain reading order
            blocks = layout.sort(key=lambda b: (b.coordinates[1], b.coordinates[0]))
            
            # Language mapping for the mode
            lang_mapping = {"bangla": ["bn"], "english": ["en"], "mixed": ["en", "bn"]}
            langs = lang_mapping.get(mode, ["en"])
            
            # Extract text from each block
            extracted_blocks = []
            for block in blocks:
                block_image = block.crop_image(image)
                
                # Convert to PIL Image and save temporarily for OCR
                pil_image = Image.fromarray(block_image)
                
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                    pil_image.save(tmp_file.name)
                    
                    # Use EasyOCR on the block
                    text, confidence = run_easyocr(tmp_file.name, langs, use_ocrmypdf=True, mode=mode)
                    
                    # Clean up temp file
                    os.unlink(tmp_file.name)
                
                if text.strip():
                    block_info = {
                        "text": text,
                        "confidence": confidence,
                        "type": block.type if hasattr(block, 'type') else 'unknown',
                        "bbox": block.coordinates
                    }
                    extracted_blocks.append(block_info)
            
            # Combine blocks with proper spacing
            combined_text = ""
            total_confidence = 0
            for i, block in enumerate(extracted_blocks):
                if i > 0:
                    combined_text += "\n\n"  # Double newline between blocks
                combined_text += block["text"]
                total_confidence += block["confidence"]
            
            avg_confidence = total_confidence / len(extracted_blocks) if extracted_blocks else 0
            
            return {
                "text": combined_text.strip(),
                "confidence": round(avg_confidence, 2),
                "blocks": len(extracted_blocks)
            }
            
        except Exception as e:
            logger.error(f"Layout OCR failed: {e}")
            # Fallback to comprehensive text extraction
            logger.info("Using comprehensive text extraction due to layout error")
            # Use enhanced EasyOCR with better coverage
            lang_mapping = {"bangla": ["bn"], "english": ["en"], "mixed": ["en", "bn"]}
            langs = lang_mapping.get(mode, ["en"])
            
            # Get comprehensive results that capture all text
            result = self._extract_with_comprehensive_coverage(image_path, langs, mode)
            return result
        finally:
            # Clean up temporary file if created
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                    
    def _extract_with_comprehensive_coverage(self, image_path, langs, mode):
        """
        Extract text with comprehensive coverage using multiple OCR passes
        """
        from .easyocr_engine import get_reader, _filter_hallucinated_english
        
        try:
            reader = get_reader(langs)
            
            # First pass: Conservative settings to get high-confidence text
            conservative_results = reader.readtext(
                image_path,
                detail=1,
                paragraph=False,
                text_threshold=0.7,
                low_text=0.4,
                link_threshold=0.4,
                canvas_size=2560,
                mag_ratio=1.5
            )
            
            # Second pass: Liberal settings to catch missed text
            liberal_results = reader.readtext(
                image_path,
                detail=1,
                paragraph=False,
                text_threshold=0.4,  # Much lower threshold
                low_text=0.2,        # Lower text confidence
                link_threshold=0.2,   # Lower link confidence
                canvas_size=3840,     # Larger canvas
                mag_ratio=2.0         # Higher magnification
            )
            
            # Combine results and deduplicate based on overlap
            all_results = self._merge_ocr_results(conservative_results, liberal_results)
            
            if not all_results:
                return {"text": "", "confidence": 0.0, "blocks": 0}
            
            # Sort results by vertical position (top to bottom), then horizontal (left to right)
            sorted_results = sorted(all_results, key=lambda x: (x[0][0][1], x[0][0][0]))
            
            # Process and filter text
            all_text = []
            total_confidence = 0
            text_count = 0
            
            for bbox, text, conf in sorted_results:
                if not text.strip():
                    continue
                    
                # Apply mode-based filtering (lighter for mixed mode)
                if mode == "bangla":
                    filtered_text = _filter_hallucinated_english(text, langs, mode="bangla")
                elif mode == "mixed":
                    # Very light filtering for mixed mode to preserve more text
                    filtered_text = _filter_hallucinated_english(text, langs, mode="mixed")
                    # If nothing left after filtering, but original confidence is high, keep it
                    if not filtered_text.strip() and conf > 0.8:
                        filtered_text = text
                else:  # english mode
                    filtered_text = text  # No filtering
                
                if filtered_text.strip():
                    all_text.append(filtered_text.strip())
                    total_confidence += conf
                    text_count += 1
            
            # Join text with spaces and add line breaks for better readability
            final_text = " ".join(all_text)
            # Add line breaks at sentence boundaries and logical breaks
            final_text = self._add_smart_line_breaks(final_text)
            
            avg_confidence = total_confidence / text_count if text_count > 0 else 0.0
            
            return {
                "text": final_text.strip(),
                "confidence": round(avg_confidence, 2),
                "blocks": len(all_text)
            }
            
        except Exception as e:
            logger.error(f"Comprehensive text extraction failed: {e}")
            # Final fallback to simple OCR
            text, confidence = run_easyocr(image_path, langs, use_ocrmypdf=True, mode=mode)
            return {
                "text": text,
                "confidence": confidence,
                "blocks": 1
            }
            
    def _merge_ocr_results(self, conservative_results, liberal_results):
        """
        Merge two sets of OCR results, avoiding duplicates based on bounding box overlap
        """
        def calculate_overlap(box1, box2):
            # Calculate IoU (Intersection over Union) for two bounding boxes
            x1_min, y1_min = min(pt[0] for pt in box1), min(pt[1] for pt in box1)
            x1_max, y1_max = max(pt[0] for pt in box1), max(pt[1] for pt in box1)
            x2_min, y2_min = min(pt[0] for pt in box2), min(pt[1] for pt in box2)
            x2_max, y2_max = max(pt[0] for pt in box2), max(pt[1] for pt in box2)
            
            # Calculate intersection
            x_overlap = max(0, min(x1_max, x2_max) - max(x1_min, x2_min))
            y_overlap = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
            intersection = x_overlap * y_overlap
            
            # Calculate areas
            area1 = (x1_max - x1_min) * (y1_max - y1_min)
            area2 = (x2_max - x2_min) * (y2_max - y2_min)
            union = area1 + area2 - intersection
            
            return intersection / union if union > 0 else 0
        
        merged_results = list(conservative_results)  # Start with conservative results
        
        for lib_bbox, lib_text, lib_conf in liberal_results:
            # Check if this liberal result overlaps significantly with any conservative result
            is_duplicate = False
            for cons_bbox, cons_text, cons_conf in conservative_results:
                overlap = calculate_overlap(lib_bbox, cons_bbox)
                if overlap > 0.5:  # 50% overlap threshold
                    is_duplicate = True
                    break
            
            # If not a duplicate, add the liberal result
            if not is_duplicate:
                merged_results.append((lib_bbox, lib_text, lib_conf))
        
        return merged_results
        
    def _add_smart_line_breaks(self, text):
        """
        Add intelligent line breaks to improve text readability
        """
        import re
        
        # Add line breaks after sentence endings
        text = re.sub(r'([.!?])\s+', r'\1\n', text)
        # Add line breaks before likely headers (all caps words)
        text = re.sub(r'\s+([A-Z]{3,}(?:\s+[A-Z]{3,})*)\s+', r'\n\n\1\n\n', text)
        # Clean up multiple consecutive line breaks
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    def is_available(self):
        """Check if layout detection is available"""
        return self.layout_available


# Global instance for function-based interface
_layout_engine_instance = None

def get_layout_engine():
    """Get or create global layout engine instance"""
    global _layout_engine_instance
    if _layout_engine_instance is None:
        _layout_engine_instance = LayoutEngine()
    return _layout_engine_instance


def extract_layout_text(image_input, langs, mode="bangla"):
    """
    Function wrapper for layout-aware text extraction
    
    Args:
        image_input (str|PIL.Image): Path to the image or PIL Image object
        langs (list): List of language codes (not used directly, mapped from mode)
        mode (str): Language mode - ['bangla', 'english', 'mixed']
    
    Returns:
        tuple: (text, confidence, blocks_count)
    """
    engine = get_layout_engine()
    result = engine.extract_layout_text(image_input, mode)
    
    return (
        result.get("text", ""),
        result.get("confidence", 0.0),
        result.get("blocks", 1)
    )