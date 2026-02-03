import cv2
import numpy as np


# =====================================================
# Crop headers/footers and page numbers
# =====================================================
def crop_margins(img, top_percent=5, bottom_percent=5, left_percent=2, right_percent=2):
    """
    Remove headers, footers, page numbers from images/PDFs
    """
    h, w = img.shape[:2]
    
    top = int(h * top_percent / 100)
    bottom = h - int(h * bottom_percent / 100)
    left = int(w * left_percent / 100)
    right = w - int(w * right_percent / 100)
    
    if top >= bottom or left >= right:
        return img
    
    return img[top:bottom, left:right]


# =====================================================
# Detect and remove borders/frames
# =====================================================
def remove_borders(img):
    """
    Detect and remove black borders or frames around scanned documents
    """
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return img
    
    largest_contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest_contour)
    
    img_h, img_w = img.shape[:2]
    if x > img_w * 0.02 or y > img_h * 0.02:
        return img[y:y+h, x:x+w]
    
    return img


# =====================================================
# Deskew (works better after binarization)
# =====================================================
def deskew(img):
    coords = np.column_stack(np.where(img > 0))

    if len(coords) == 0:
        return img

    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    
    # Only deskew if angle is significant but not too extreme
    if abs(angle) < 0.5 or abs(angle) > 10:
        return img

    (h, w) = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)

    return cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )


# =====================================================
# Super-resolution upscaling for small images
# =====================================================
def smart_upscale(img, target_height=2000):
    """
    Smart upscaling for better OCR accuracy
    Uses INTER_CUBIC for smooth upscaling
    """
    h, w = img.shape[:2]
    
    if h >= target_height:
        return img
    
    scale = target_height / h
    new_w = int(w * scale)
    new_h = int(h * scale)
    
    # Use INTER_CUBIC for quality upscaling
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)


# =====================================================
# Noise removal with edge preservation
# =====================================================
def denoise_preserve_edges(img, strength=10):
    """
    Denoise while preserving text edges
    Critical for Bangla complex glyphs
    """
    # Fast NL Means Denoising - best for OCR
    denoised = cv2.fastNlMeansDenoising(img, h=strength)
    return denoised


# =====================================================
# Multi-method binarization (try multiple, return best)
# =====================================================
def adaptive_binarize(img, block_size=31, c=10):
    """
    Adaptive Gaussian thresholding - best for varying lighting
    """
    return cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size, c
    )


def otsu_binarize(img):
    """
    OTSU automatic thresholding - best for uniform backgrounds
    """
    _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def sauvola_binarize(img, window_size=25, k=0.2):
    """
    Sauvola binarization - excellent for documents with varying contrast
    """
    # Calculate local mean and std
    mean = cv2.blur(img.astype(np.float64), (window_size, window_size))
    
    # Calculate local standard deviation
    sq_mean = cv2.blur(img.astype(np.float64)**2, (window_size, window_size))
    std = np.sqrt(np.maximum(sq_mean - mean**2, 0))
    
    # Sauvola threshold
    R = 128  # dynamic range of standard deviation
    threshold = mean * (1 + k * (std / R - 1))
    
    # Apply threshold
    binary = np.zeros_like(img)
    binary[img > threshold] = 255
    
    return binary.astype(np.uint8)


def try_multiple_binarizations(img, is_bangla=False):
    """
    Try multiple binarization methods and return the best one
    Best = highest contrast between text and background
    """
    results = []
    
    # Method 1: Adaptive Gaussian (best for Bangla)
    if is_bangla:
        adaptive = adaptive_binarize(img, block_size=35, c=8)
    else:
        adaptive = adaptive_binarize(img, block_size=31, c=10)
    results.append(("adaptive", adaptive))
    
    # Method 2: OTSU (best for clean images)
    otsu = otsu_binarize(img)
    results.append(("otsu", otsu))
    
    # Method 3: Sauvola (best for varying contrast)
    try:
        sauvola = sauvola_binarize(img)
        results.append(("sauvola", sauvola))
    except:
        pass
    
    # Score each method by contrast
    best_score = 0
    best_img = adaptive
    
    for name, binary in results:
        # Score = variance (higher variance = better separation)
        score = np.var(binary)
        
        # Also check that we have reasonable amount of text
        white_ratio = np.sum(binary == 255) / binary.size
        if 0.3 < white_ratio < 0.95:  # Reasonable text/background ratio
            score *= 1.5
        
        if score > best_score:
            best_score = score
            best_img = binary
    
    return best_img


# =====================================================
# ULTRA LANGUAGE-AWARE PREPROCESS
# =====================================================
def preprocess(pil_img, langs=None):
    """
    MAXIMUM ACCURACY preprocessing pipeline
    
    Key features:
    - Smart upscaling to optimal OCR resolution
    - Multi-method binarization selection
    - Edge-preserving denoising
    - Language-specific optimizations
    - Morphological cleanup
    """

    img = np.array(pil_img)
    
    # Convert to grayscale if needed
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    # 1️⃣ CROP margins to remove headers/footers/page numbers
    gray = crop_margins(gray, top_percent=6, bottom_percent=6, left_percent=3, right_percent=3)

    # 2️⃣ SMART UPSCALE for better OCR (target 2000px height)
    gray = smart_upscale(gray, target_height=2000)

    # 3️⃣ CLAHE contrast enhancement (CRITICAL)
    clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    is_bangla = langs and 'bn' in langs
    is_english = langs and 'en' in langs and 'bn' not in langs

    # =================================================
    # BANGLA Pipeline (MAXIMUM ACCURACY)
    # =================================================
    if is_bangla:
        
        # Step 1: Bilateral filter (preserves Bangla edges)
        gray = cv2.bilateralFilter(gray, 11, 75, 75)
        
        # Step 2: Light denoising (preserve text details)
        gray = denoise_preserve_edges(gray, strength=8)
        
        # Step 3: Multi-method binarization
        thresh = try_multiple_binarizations(gray, is_bangla=True)
        
        # Step 4: Morphological cleanup for Bangla glyphs
        # Small opening to remove specks
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_open)
        
        # Closing to connect broken character parts (Bangla has many joined parts)
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 1))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_close)

    # =================================================
    # ENGLISH Pipeline (MAXIMUM ACCURACY)
    # =================================================
    elif is_english:
        
        # Step 1: Denoise
        gray = denoise_preserve_edges(gray, strength=12)
        
        # Step 2: Sharpen text
        kernel_sharpen = np.array([[-1,-1,-1],
                                   [-1, 9,-1],
                                   [-1,-1,-1]])
        gray = cv2.filter2D(gray, -1, kernel_sharpen)
        
        # Step 3: Multi-method binarization
        thresh = try_multiple_binarizations(gray, is_bangla=False)
        
        # Step 4: Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    # =================================================
    # DEFAULT Pipeline (Mixed/Other)
    # =================================================
    else:
        gray = denoise_preserve_edges(gray, strength=10)
        thresh = try_multiple_binarizations(gray, is_bangla=False)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # 4️⃣ Remove borders
    thresh = remove_borders(thresh)
    
    # 5️⃣ Deskew
    thresh = deskew(thresh)
    
    # 6️⃣ Ensure black text on white background
    if np.mean(thresh) < 127:
        thresh = cv2.bitwise_not(thresh)

    return thresh


# =====================================================
# Alternative preprocessing for difficult images
# =====================================================
def preprocess_difficult(pil_img, langs=None):
    """
    Alternative preprocessing for low-quality or difficult images
    Uses more aggressive noise reduction and contrast enhancement
    """
    img = np.array(pil_img)
    
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    
    # Aggressive upscaling
    gray = smart_upscale(gray, target_height=2500)
    
    # Heavy CLAHE
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Heavy denoising
    gray = cv2.fastNlMeansDenoising(gray, h=20)
    
    # Aggressive binarization
    thresh = adaptive_binarize(gray, block_size=41, c=12)
    
    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    if np.mean(thresh) < 127:
        thresh = cv2.bitwise_not(thresh)
    
    return thresh
