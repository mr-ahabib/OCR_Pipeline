from fastapi import FastAPI, UploadFile, File, Form
from app.service import process_file

app = FastAPI(title="Robust OCR Engine")

@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    languages: str = Form("en")
):
    langs = languages.split(",")

    content = await file.read()

    result = await process_file(content, langs)

    return result
