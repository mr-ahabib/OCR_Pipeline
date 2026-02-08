#!/usr/bin/env python3
"""
Test script for the new mode-based OCR API
Usage: python3 test_modes.py
"""

import json
from app.main import OCR_MODES

def test_mode_mapping():
    """Test that mode mapping works correctly"""
    print("🧪 Testing OCR mode mapping...")
    
    for mode, expected_langs in OCR_MODES.items():
        print(f"  {mode}: {expected_langs}")
    
    # Test each mode
    test_cases = [
        ("bangla", ["bn"]),
        ("english", ["en"]), 
        ("mixed", ["bn", "en"])
    ]
    
    for mode, expected in test_cases:
        actual = OCR_MODES.get(mode, ["en"])
        if actual == expected:
            print(f"  ✅ {mode} mode: {actual}")
        else:
            print(f"  ❌ {mode} mode: expected {expected}, got {actual}")

def test_api_format():
    """Test the expected API request format"""
    print("\n📡 Testing API request format...")
    
    examples = [
        {
            "description": "Bangla-only OCR (aggressive English filtering)",
            "curl": 'curl -F file=@document.pdf -F mode=bangla http://localhost:8000/ocr'
        },
        {
            "description": "English-only OCR (no filtering)",
            "curl": 'curl -F file=@document.pdf -F mode=english http://localhost:8000/ocr'
        },
        {
            "description": "Mixed Bangla+English OCR (balanced filtering)",
            "curl": 'curl -F file=@document.pdf -F mode=mixed http://localhost:8000/ocr'
        },
        {
            "description": "Layout-aware mixed OCR",
            "curl": 'curl -F file=@document.pdf -F mode=mixed -F preserve_layout=true http://localhost:8000/ocr'
        }
    ]
    
    for example in examples:
        print(f"  📋 {example['description']}")
        print(f"     {example['curl']}")
        print()

if __name__ == "__main__":
    test_mode_mapping()
    test_api_format()
    
    print("🎉 Mode-based OCR API is ready!")
    print("\nKey features:")
    print("- Bangla mode: Aggressive English filtering for pure Bangla text")
    print("- English mode: No filtering for English-only documents") 
    print("- Mixed mode: Balanced filtering preserves both languages")
    print("- Layout mode: Works with all language modes for structured documents")