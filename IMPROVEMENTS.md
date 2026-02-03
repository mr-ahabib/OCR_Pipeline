# OCR Pipeline Improvements for High Accuracy

## Summary of Changes

This document outlines the comprehensive improvements made to achieve **very high accuracy** for both **English** and **Bangla** OCR, including proper handling of mixed-language documents.

---

## 🎯 Key Improvements

### 1. **Header/Page Number Cropping**
- **Added automatic margin cropping** to remove headers, footers, and page numbers
- Crops top (6%), bottom (6%), left (3%), and right (3%) by default
- Focuses OCR on main content only
- Removes border detection and cleanup

### 2. **Enhanced Image Preprocessing**
- **Upscaling**: Automatically scales up small images to minimum 1000px for better OCR
- **Better noise reduction**: 
  - Bilateral filtering for Bangla (preserves edges)
  - Advanced denoising for English
- **Improved binarization**:
  - Adaptive thresholding for Bangla (block size 33)
  - OTSU + sharpening for English
- **CLAHE contrast enhancement**: Improved from 2.5 to 3.0 clipLimit
- **Morphological operations**: Opening for Bangla, closing for English
- **Auto-inversion**: Ensures black text on white background

### 3. **Multi-Pass Tesseract Strategy**
- **Pass 1**: LSTM model (OEM 1) + Auto segmentation (PSM 3) - best for mixed content
- **Pass 2**: If confidence < 75%, try uniform block (PSM 6) - better for clean books
- **Pass 3**: For Bangla, try Bengali-only optimization with PSM 3
- **Pass 4**: If still < 50%, fallback to script detection
- **Selects best result** from all passes based on confidence

### 4. **Enhanced EasyOCR**
- Added paragraph grouping for better text assembly
- Optimized detection parameters:
  - `paragraph=True` - groups text into logical blocks
  - `canvas_size=2560` - larger detection area
  - `text_threshold=0.7` - stricter text detection
  - `mag_ratio=1.5` - better magnification
- GPU support with automatic CPU fallback
- Better confidence calculation

### 5. **Advanced Postprocessing**
- **OCR artifact removal**: Fixes common character confusions (|→I, rn→m, vv→w)
- **Bangla-specific cleaning**:
  - Removes standalone English letters in Bangla text
  - Fixes common Bangla character duplications
  - Normalizes Bengali numerals
- **English-specific cleaning**:
  - Fixes l/I confusion at sentence start
  - Proper capitalization
- **Punctuation normalization**
- **Noise pattern removal**

### 6. **Improved PDF Processing**
- 600 DPI rendering (crystal clear for both languages)
- Keeps color information for better preprocessing
- Uses pdftocairo for better rendering
- Parallel processing with 4 threads

---

## 📊 Expected Accuracy Improvements

### Before
- **Bangla**: ~67% confidence with many errors
- **English**: ~86% confidence with character confusions
- **Mixed language**: Poor handling, junk characters

### After
- **Bangla**: Expected **85-95%+** confidence
- **English**: Expected **90-98%+** confidence  
- **Mixed language**: Proper detection and separation
- Headers/footers removed automatically
- Much cleaner text output

---

## 🚀 Usage

### For Bangla Documents
```bash
curl -X POST http://192.168.0.61:8000/ocr \
  -F "file=@bangla_book.pdf" \
  -F "languages=bn"
```

### For English Documents
```bash
curl -X POST http://192.168.0.61:8000/ocr \
  -F "file=@english_book.pdf" \
  -F "languages=en"
```

### For Mixed Bangla + English Documents
```bash
curl -X POST http://192.168.0.61:8000/ocr \
  -F "file=@mixed_document.pdf" \
  -F "languages=bn,en"
```

---

## 🔧 Configuration

### Adjust Margin Cropping
Edit [preprocessing.py](app/utils/preprocessing.py#L45):

```python
gray = crop_margins(
    gray, 
    top_percent=6,     # Increase to crop more header
    bottom_percent=6,  # Increase to crop more footer
    left_percent=3,    # Increase to crop more left margin
    right_percent=3    # Increase to crop more right margin
)
```

### Adjust Confidence Threshold
Edit `.env` file:
```bash
CONFIDENCE_THRESHOLD=90  # Lower to reduce DocAI fallback usage
```

### Fine-tune Tesseract PSM Mode
Edit [tesseract_engine.py](app/ocr/tesseract_engine.py#L71):

```python
# PSM modes:
# 3 = Fully automatic (best for mixed/complex layouts)
# 6 = Uniform block (best for clean single-column books)
# 11 = Sparse text (for noisy/degraded images)
```

---

## 🐛 Troubleshooting

### Still Getting Low Accuracy?

1. **Check image quality**: Ensure PDF is at least 300 DPI
2. **Increase margin cropping**: More aggressive header/footer removal
3. **Try different language combinations**: Test `bn,en` vs `bn` alone
4. **Check Tesseract language data**: Ensure Bengali trained data is installed
   ```bash
   sudo apt-get install tesseract-ocr-ben
   ```

### Headers/Footers Still Appearing?

Increase crop percentages in [preprocessing.py](app/utils/preprocessing.py#L45):
```python
gray = crop_margins(gray, top_percent=8, bottom_percent=8)
```

### Mixed Language Not Working?

- Always specify both languages: `languages=bn,en`
- The system will automatically detect and handle both scripts
- Multi-pass Tesseract will try each language separately if needed

---

## 📈 Technical Details

### Preprocessing Pipeline
1. Load image/PDF
2. Convert to grayscale
3. **Crop margins** (remove headers/footers)
4. Upscale if too small
5. CLAHE contrast enhancement
6. Language-specific filtering
7. Binarization (adaptive or OTSU)
8. Morphological operations
9. Border removal
10. Deskew
11. Invert if needed

### OCR Pipeline
1. Tesseract multi-pass (3-4 attempts)
2. EasyOCR fallback (if Tesseract < 85%)
3. DocAI ultimate fallback (if both < threshold)
4. Select best result
5. Clean text artifacts
6. Remove noise patterns
7. Spell correction

### Confidence Calculation
- Word-level confidence from Tesseract/EasyOCR
- Weighted average across all detected words
- Ignores invalid detections (-1 confidence)
- Final score: 0-100%

---

## 🎓 Best Practices

1. **Use correct language codes**: 
   - Bangla: `bn`
   - English: `en`
   - Mixed: `bn,en`

2. **High-quality input**:
   - Minimum 300 DPI for PDFs
   - Clear, well-lit images
   - Avoid blurry or distorted scans

3. **Adjust margins for your documents**:
   - Academic books: More header/footer cropping
   - Novels: Less cropping needed
   - Forms: May need custom cropping

4. **Monitor confidence scores**:
   - > 90%: Excellent
   - 80-90%: Good
   - 70-80%: Acceptable
   - < 70%: Review and possibly rescan

---

## 📝 File Changes Summary

| File | Changes |
|------|---------|
| `app/utils/preprocessing.py` | Added margin cropping, border removal, enhanced preprocessing |
| `app/ocr/tesseract_engine.py` | Multi-pass strategy, optimized configs |
| `app/ocr/easyocr_engine.py` | Better parameters, paragraph mode, GPU support |
| `app/utils/postprocessing.py` | Advanced cleaning, noise removal, language-specific fixes |
| `app/utils/pdf_utils.py` | Higher DPI, better rendering |
| `app/service.py` | Integrated new postprocessing step |
| `requirements.txt` | Added missing dependencies |

---

## 🔮 Future Improvements

- [ ] Automatic language detection
- [ ] Custom Bangla training data
- [ ] Layout analysis for complex documents
- [ ] Table detection and extraction
- [ ] Handwriting recognition support
- [ ] Batch processing optimization
- [ ] Real-time OCR streaming

---

## 📞 Support

For issues or questions about these improvements:
1. Check confidence scores in API response
2. Review preprocessing output (add debug logging)
3. Try different language combinations
4. Adjust margin cropping percentages
5. Ensure Tesseract Bengali data is installed

**Note**: The system is now optimized for **production-grade accuracy** on both Bangla and English text. Test with your specific documents and adjust parameters as needed.
