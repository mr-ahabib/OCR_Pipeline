import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    TESSERACT_CMD = os.getenv("TESSERACT_CMD")
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 90))

    GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
    GOOGLE_LOCATION = os.getenv("GOOGLE_LOCATION")
    GOOGLE_PROCESSOR_ID = os.getenv("GOOGLE_PROCESSOR_ID")

settings = Settings()
