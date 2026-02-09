from pydantic import BaseModel
from typing import List, Optional, Union

class PageData(BaseModel):
    """Individual page OCR results for multi-page documents"""
    page_number: int
    text: str
    confidence: float
    character_count: int

class PlainTextResponse(BaseModel):
    """Simple plain text response"""
    text: str
    
class PageByPageResponse(BaseModel):
    """Page-by-page formatted text response"""
    formatted_text: str
    summary: str

class OCRResponse(BaseModel):
    """Full JSON OCR response with metadata"""
    text: str  # Combined text for all pages
    confidence: float  # Overall average confidence
    pages: int  # Total number of pages processed
    languages: List[str]  # Languages used for OCR
    mode: str  # OCR mode (bangla/english/mixed)
    engine: str  # OCR engine description
    features: List[str]  # List of features used
    
    # Page-by-page results (only present for multi-page documents)
    pages_data: Optional[List[PageData]] = None
    
    class Config:
        schema_extra = {
            "plain_text_example": {
                "text": "Sample extracted text from the document"
            },
            "page_by_page_example": {
                "formatted_text": "=== PAGE 1 === (Confidence: 94.5%) ===\nText from page 1\n\n=== PAGE 2 === (Confidence: 91.8%) ===\nText from page 2",
                "summary": "2 pages processed with 93.1% average confidence"
            },
            "json_example": {
                "text": "Combined text from all pages...",
                "confidence": 91.5,
                "pages": 3,
                "languages": ["en"],
                "mode": "english",
                "engine": "Multi-strategy: OCRmyPDF + Tesseract (english mode)", 
                "features": ["Multi-column detection", "Page-by-page OCR results"],
                "pages_data": [
                    {
                        "page_number": 1,
                        "text": "Text from page 1",
                        "confidence": 94.5,
                        "character_count": 156
                    }
                ]
            }
        }
