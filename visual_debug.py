"""
Visual Preprocessing Demo

This script shows before/after of the preprocessing pipeline
Useful for debugging and understanding the improvements
"""

import cv2
import numpy as np
from PIL import Image
import sys
from pathlib import Path

# Import the old and new preprocessing
from app.utils.preprocessing import preprocess, crop_margins


def show_preprocessing_steps(image_path: str, langs=['bn']):
    """
    Visualize all preprocessing steps
    
    Args:
        image_path: Path to test image
        langs: List of language codes
    """
    
    print(f"Loading image: {image_path}")
    
    # Load image
    pil_img = Image.open(image_path)
    img = np.array(pil_img)
    
    # Convert to grayscale
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    
    print(f"Original size: {gray.shape}")
    
    # Step 1: Show original
    cv2.imwrite("debug_1_original.png", gray)
    print("✓ Saved: debug_1_original.png")
    
    # Step 2: After cropping margins
    cropped = crop_margins(gray, top_percent=6, bottom_percent=6, left_percent=3, right_percent=3)
    cv2.imwrite("debug_2_cropped.png", cropped)
    print("✓ Saved: debug_2_cropped.png (headers/footers removed)")
    print(f"  After crop size: {cropped.shape}")
    
    # Step 3: After upscaling (if needed)
    h, w = cropped.shape
    if h < 1000 or w < 1000:
        scale_factor = max(1000/h, 1000/w)
        new_h, new_w = int(h * scale_factor), int(w * scale_factor)
        upscaled = cv2.resize(cropped, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        cv2.imwrite("debug_3_upscaled.png", upscaled)
        print("✓ Saved: debug_3_upscaled.png")
        print(f"  Upscaled to: {upscaled.shape}")
    else:
        upscaled = cropped
        print("  (No upscaling needed)")
    
    # Step 4: After CLAHE
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(upscaled)
    cv2.imwrite("debug_4_clahe.png", enhanced)
    print("✓ Saved: debug_4_clahe.png (contrast enhanced)")
    
    # Step 5: Full preprocessing pipeline
    final = preprocess(pil_img, langs)
    cv2.imwrite("debug_5_final.png", final)
    print("✓ Saved: debug_5_final.png (ready for OCR)")
    
    print("\n" + "="*60)
    print("Preprocessing Pipeline Complete!")
    print("="*60)
    print("\nFiles created:")
    print("  1. debug_1_original.png  - Original image")
    print("  2. debug_2_cropped.png   - After margin cropping")
    print("  3. debug_3_upscaled.png  - After upscaling (if needed)")
    print("  4. debug_4_clahe.png     - After contrast enhancement")
    print("  5. debug_5_final.png     - Final preprocessed (for OCR)")
    print("\n👁️  Open these files to see each step of the process")
    
    # Calculate improvements
    orig_mean = np.mean(gray)
    final_mean = np.mean(final)
    
    print(f"\n📊 Statistics:")
    print(f"  Original brightness: {orig_mean:.2f}")
    print(f"  Final brightness: {final_mean:.2f}")
    print(f"  Size reduction: {gray.shape} → {cropped.shape}")
    
    area_orig = gray.shape[0] * gray.shape[1]
    area_crop = cropped.shape[0] * cropped.shape[1]
    reduction = (1 - area_crop/area_orig) * 100
    print(f"  Area reduced by: {reduction:.1f}% (removed margins)")


def compare_old_vs_new(image_path: str, langs=['bn']):
    """
    Compare the results with old vs new preprocessing
    (This would need the old function saved separately)
    """
    print("\nTo compare old vs new:")
    print("1. Run preprocessing on your sample images")
    print("2. Use the debug files to visually inspect")
    print("3. Check OCR confidence scores")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python visual_debug.py <image_path> [languages]")
        print("\nExamples:")
        print("  python visual_debug.py sample.jpg bn")
        print("  python visual_debug.py page.png bn,en")
        sys.exit(1)
    
    image_path = sys.argv[1]
    langs = sys.argv[2].split(',') if len(sys.argv) > 2 else ['bn']
    
    if not Path(image_path).exists():
        print(f"Error: File not found: {image_path}")
        sys.exit(1)
    
    show_preprocessing_steps(image_path, langs)
