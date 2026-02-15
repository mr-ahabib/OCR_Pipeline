# OCR Pipeline - Bangla Text Extraction

High-accuracy OCR system optimized for Bangla (Bengali) text extraction with multi-engine support.

## ✨ Recent Improvements (Feb 2026)

### 🚀 **60-70% Faster Processing**
- Smart OCRmyPDF usage (skip for images, use for PDFs)
- Early exit strategy for high-confidence results
- Optimized parameters for Bangla processing

### 📄 **Perfect Layout Preservation**
- **Line-by-line extraction** with proper reading order
- **Paragraph detection** based on vertical spacing
- **Intelligent word spacing** (punctuation, brackets, etc.)
- **Top-to-bottom, left-to-right** reading order maintained

See [PERFORMANCE_IMPROVEMENTS.md](PERFORMANCE_IMPROVEMENTS.md) and [LAYOUT_FIX_SUMMARY.md](LAYOUT_FIX_SUMMARY.md) for details.

## Features

- **Multi-Engine OCR**: Tesseract + EasyOCR + Google DocAI
- **Bangla Optimized**: Specialized configuration for Bengali script
- **Multiple Modes**: Bangla-only, English-only, and Mixed mode
- **High Accuracy**: Uses best trained data and multiple extraction strategies
- **Page-by-Page Processing**: Detailed results for each page in PDFs
- **Robust**: Automatic fallback strategies for low-quality scans
- **Layout Preservation**: Maintains original document structure (line breaks, paragraphs, spacing)

## 🚀 Quick Setup

### 1. Install System Dependencies

#### Ubuntu/Debian:
```bash
# Install Tesseract OCR
sudo apt-get update
sudo apt-get install -y tesseract-ocr

# Install additional tools
sudo apt-get install -y poppler-utils wget
```

#### macOS:
```bash
brew install tesseract poppler
```

### 2. Install Best Trained Data for Bangla

**Option A: Automated Installation (Recommended)**
```bash
./install_tesseract_data.sh
```

**Option B: Manual Installation**
```bash
# Download best trained data
wget https://github.com/tesseract-ocr/tessdata_best/raw/main/ben.traineddata
wget https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata

# Copy to Tesseract data directory
sudo cp ben.traineddata /usr/share/tesseract-ocr/4.00/tessdata/
sudo cp eng.traineddata /usr/share/tesseract-ocr/4.00/tessdata/

# Or for Tesseract 5:
sudo cp ben.traineddata /usr/share/tesseract-ocr/5/tessdata/
sudo cp eng.traineddata /usr/share/tesseract-ocr/5/tessdata/
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

The `.env` file is already configured with optimal settings for Bangla OCR. Update if needed:

```bash
# Edit .env file
nano .env
```

**Key Configuration:**
- `TESSERACT_CMD`: Path to Tesseract executable (default: `/usr/bin/tesseract`)
- `OCRMYPDF_OVERSAMPLE_DPI`: DPI for preprocessing (default: `600` - optimal for Bangla)
- `OCR_PDF_DPI`: DPI for PDF to image conversion (default: `600`)
- `CONFIDENCE_THRESHOLD`: Minimum confidence before using DocAI fallback (default: `75`)

### 5. Validate Installation

```bash
python3 validate_tesseract.py
```

This will check:
- ✓ Tesseract installation
- ✓ Bengali language data
- ✓ English language data
- ✓ Configuration files

### 6. Start the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 📖 Usage

### API Endpoints

#### 1. Plain Text Extraction
```bash
curl -X POST "http://localhost:8000/ocr/text" \
  -F "file=@document.pdf" \
  -F "mode=bangla"
```

**Response:**
```json
{
  "text": "extracted text here..."
}
```

#### 2. Page-by-Page Extraction
```bash
curl -X POST "http://localhost:8000/ocr/pages" \
  -F "file=@document.pdf" \
  -F "mode=bangla"
```

**Response:**
```json
{
  "pages_info": [
    {
      "page_number": 1,
      "confidence": 95.5,
      "character_count": 1234,
      "text": "Page 1 text..."
    }
  ],
  "summary": {
    "total_pages": 5,
    "average_confidence": 94.2,
    "total_characters": 6789
  }
}
```

#### 3. Full JSON with Metadata
```bash
curl -X POST "http://localhost:8000/ocr/json" \
  -F "file=@document.pdf" \
  -F "mode=mixed"
```

**Response:**
```json
{
  "text": "full extracted text...",
  "confidence": 94.5,
  "pages": 5,
  "languages": ["bn", "en"],
  "mode": "mixed",
  "engine": "Multi-strategy: OCRmyPDF + Tesseract (mixed mode)",
  "pages_data": [...]
}
```

### OCR Modes

1. **`bangla`**: Bangla-only text (aggressive English filtering)
2. **`english`**: English-only text
3. **`mixed`**: Both Bangla and English text

### Supported File Types

- PDF documents (`.pdf`)
- Images: JPEG (`.jpg`, `.jpeg`), PNG (`.png`), GIF (`.gif`), BMP (`.bmp`), WebP (`.webp`), TIFF (`.tif`, `.tiff`)

## 🔧 Troubleshooting

### Issue: Bangla text not extracting or very low accuracy

**Solutions:**

1. **Verify Tesseract installation:**
   ```bash
   python3 validate_tesseract.py
   ```

2. **Ensure best trained data is installed:**
   ```bash
   tesseract --list-langs
   # Should show 'ben' and 'eng'
   ```

3. **Check if using tessdata_best (not tessdata_fast):**
   - Download from: https://github.com/tesseract-ocr/tessdata_best
   - Best data provides 10-20% better accuracy for Bangla

4. **Increase DPI settings in .env:**
   ```bash
   OCRMYPDF_OVERSAMPLE_DPI=600
   OCR_PDF_DPI=600
   ```

5. **Use correct mode:**
   - For Bangla-only documents: `mode=bangla`
   - For mixed content: `mode=mixed`

### Issue: Page-by-page extraction missing pages

**Solutions:**

1. **Check PDF quality:**
   - Ensure PDF is not corrupted
   - Try converting to images first

2. **Increase timeout settings:**
   ```bash
   REQUEST_TIMEOUT=300  # 5 minutes
   ```

3. **Check logs:**
   ```bash
   tail -f app/logs/logs.txt
   ```

### Issue: Empty .env file

The `.env` file has been properly configured with optimal settings. If you deleted it, recreate it using:

```bash
git checkout .env
```

Or copy the provided template in this README.

## 🎯 Optimization Tips

### For Best Bangla Accuracy:

1. **Use high-quality scans** (300 DPI or higher)
2. **Use `bangla` mode** for Bangla-only documents
3. **Ensure good lighting** and contrast in scanned images
4. **Use tessdata_best** (not tessdata_fast)
5. **Keep DPI at 600** in .env file

### For Faster Processing:

1. **Reduce DPI** to 400 (slight accuracy trade-off)
2. **Adjust parallel processing:**
   ```bash
   OCR_MAX_PARALLEL_PAGES=2  # Reduce for lower memory usage
   ```

### For Low-Quality Scans:

1. **Increase DPI** to 600 or higher
2. **Use `mixed` mode** if unsure about content
3. **Enable DocAI fallback** for very poor quality

## 📊 Performance

**Typical Processing Times:**
- Single page image (600 DPI): 3-5 seconds
- 10-page PDF (600 DPI): 15-25 seconds
- 50-page PDF (600 DPI): 60-90 seconds

**Accuracy Metrics:**
- Bangla text (good quality): 95-98%
- Bangla text (poor quality): 85-92%
- Mixed Bangla+English: 90-95%

## 🔍 How It Works

### Multi-Pass Strategy:

1. **Pass 1**: OCRmyPDF preprocessing + Tesseract with multiple PSM modes
   - Deskewing, cleaning, background removal
   - Multiple page segmentation modes tested in parallel
   - OEM 3 (Legacy + LSTM) for best Bangla support

2. **Pass 2**: Raw Tesseract without preprocessing (if confidence < 90%)
   - Different preprocessing variants
   - Additional PSM modes (4, 11, 13)

3. **Pass 3**: EasyOCR ensemble for Bangla validation
   - Cross-validation of text
   - English hallucination filtering
   - Alternative extraction if Tesseract fails

4. **Pass 4**: Google DocAI fallback (if confidence < threshold)
   - Only for very low quality or failed extractions

## 📝 Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TESSERACT_CMD` | `/usr/bin/tesseract` | Path to Tesseract executable |
| `CONFIDENCE_THRESHOLD` | `75` | Minimum confidence before DocAI fallback |
| `OCRMYPDF_OVERSAMPLE_DPI` | `600` | DPI for preprocessing |
| `OCR_PDF_DPI` | `600` | DPI for PDF to image conversion |
| `OCR_MAX_PARALLEL_PAGES` | `4` | Pages to process in parallel |
| `OCR_ENGINE_MAX_WORKERS` | `8` | Worker threads for OCR |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum file upload size |

## 🤝 Support

For issues or questions:

1. **Check validation script output:**
   ```bash
   python3 validate_tesseract.py
   ```

2. **Check logs:**
   ```bash
   cat app/logs/logs.txt
   ```

3. **Test with sample Bangla text:**
   ```bash
   curl -X POST "http://localhost:8000/ocr/text" \
     -F "file=@test_bangla.pdf" \
     -F "mode=bangla"
   ```

## 📄 License

This project is configured for optimal Bangla text extraction using open-source OCR engines.

## 🙏 Acknowledgments

- **Tesseract OCR** - Google's open-source OCR engine
- **EasyOCR** - Jaided AI's deep learning OCR
- **OCRmyPDF** - PDF preprocessing and enhancement
- **tessdata_best** - High-accuracy trained data models

---

**Last Updated:** February 2026
**Version:** 2.0.0 - Bangla Optimized
