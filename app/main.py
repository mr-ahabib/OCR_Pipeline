from fastapi import FastAPI, UploadFile, File, Form
from app.service import process_file
from typing import Literal

app = FastAPI(title="Robust OCR Engine")

# Define OCR modes
OCR_MODES = {
    "bangla": ["bn"],
    "english": ["en"],
    "mixed": ["bn", "en"]
}

@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    mode: Literal["bangla", "english", "mixed"] = Form("english"),
    preserve_layout: bool = Form(False),
):
    """OCR endpoint with simplified mode selection.
    
    Modes:
    - bangla: Bangla-only OCR (filters out English hallucinations)
    - english: English-only OCR
    - mixed: Mixed Bangla+English OCR (preserves both languages)
    """
    langs = OCR_MODES.get(mode, ["en"])

    content = await file.read()

    result = await process_file(content, langs, preserve_layout=preserve_layout, mode=mode)

    return result
