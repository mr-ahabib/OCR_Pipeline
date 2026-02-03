from pydantic import BaseModel
from typing import List

class OCRResponse(BaseModel):
    text: str
    confidence: float
    pages: int
    language: List[str]
