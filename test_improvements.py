#!/usr/bin/env python3
"""
Test script to verify OCR improvements

Usage:
    python test_improvements.py <image_or_pdf_path> <languages>
    
Examples:
    python test_improvements.py sample.jpg bn
    python test_improvements.py document.pdf bn,en
"""

import sys
import requests
from pathlib import Path

def test_ocr(file_path: str, languages: str = "en"):
    """
    Test OCR API with a file
    
    Args:
        file_path: Path to image or PDF file
        languages: Comma-separated language codes (e.g., "bn,en")
    """
    
    url = "http://192.168.0.61:8000/ocr"
    
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"❌ Error: File not found: {file_path}")
        return
    
    print(f"📄 Testing OCR on: {file_path.name}")
    print(f"🌐 Languages: {languages}")
    print(f"📡 Sending request to: {url}")
    print("-" * 60)
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'application/octet-stream')}
            data = {'languages': languages}
            
            response = requests.post(url, files=files, data=data)
            response.raise_for_status()
            
            result = response.json()
            
            print("✅ OCR Completed Successfully!\n")
            print(f"📊 Confidence: {result['confidence']:.2f}%")
            print(f"📑 Pages: {result['pages']}")
            print(f"🔤 Languages: {result['language']}")
            print("-" * 60)
            print("📝 Extracted Text:")
            print("-" * 60)
            print(result['text'][:1000])  # Print first 1000 chars
            if len(result['text']) > 1000:
                print(f"\n... ({len(result['text']) - 1000} more characters)")
            print("-" * 60)
            
            # Confidence assessment
            conf = result['confidence']
            if conf >= 90:
                status = "🟢 EXCELLENT"
            elif conf >= 80:
                status = "🟡 GOOD"
            elif conf >= 70:
                status = "🟠 ACCEPTABLE"
            else:
                status = "🔴 NEEDS REVIEW"
            
            print(f"\n{status} - Confidence: {conf:.2f}%")
            
            # Save result to file
            output_file = file_path.stem + "_ocr_result.txt"
            with open(output_file, 'w', encoding='utf-8') as out:
                out.write(result['text'])
            print(f"\n💾 Full result saved to: {output_file}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to OCR server")
        print("   Make sure the server is running: uvicorn app.main:app --host 192.168.0.61 --port 8000")
    except requests.exceptions.RequestException as e:
        print(f"❌ Request Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_improvements.py <file_path> [languages]")
        print("\nExamples:")
        print("  python test_improvements.py sample.jpg bn")
        print("  python test_improvements.py document.pdf bn,en")
        print("  python test_improvements.py book.pdf en")
        sys.exit(1)
    
    file_path = sys.argv[1]
    languages = sys.argv[2] if len(sys.argv) > 2 else "en"
    
    test_ocr(file_path, languages)
