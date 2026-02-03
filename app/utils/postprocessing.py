import re

# =====================================================
# Common OCR error patterns
# =====================================================

# English character confusion pairs
ENGLISH_CONFUSIONS = {
    # I/l/1 confusion
    ' l ': ' I ',
    ' 1 ': ' I ',
    'l\'m': 'I\'m',
    'l\'ve': 'I\'ve',
    'l\'ll': 'I\'ll',
    'lt\'s': 'It\'s',
    'lf ': 'If ',
    'ln ': 'In ',
    'lt ': 'It ',
    'ls ': 'Is ',
    
    # rn/m confusion
    ' rn': ' m',
    'rnore': 'more',
    'rnost': 'most',
    'rnay': 'may',
    'rnake': 'make',
    'rnan': 'man',
    'rnuch': 'much',
    
    # vv/w confusion
    'vv': 'w',
    
    # Other common
    '0utput': 'Output',
    'O\'clock': 'o\'clock',
    'c1ock': 'clock',
    'b00k': 'book',
    'l00k': 'look',
    'tirne': 'time',
    'narne': 'name',
    'sarne': 'same',
    'carne': 'came',
    'garne': 'game',
    'horne': 'home',
    'sorne': 'some',
    'becarne': 'became',
    
    # he/le confusion
    'le ': 'he ',
    ' le\'s': ' he\'s',
    'rnust': 'must',
    
    # His/He confusion
    'His ': 'He ',
    'his ': 'he ',
}

# Bangla OCR common errors
BANGLA_CONFUSIONS = {
    'ওৱ': 'ও',
    'াা': 'া',
    'েে': 'ে',
    'িি': 'ি',
    'ীী': 'ী',
    'ুু': 'ু',
    'ূূ': 'ূ',
    '০০': '০',
    '।।': '।',
}


def clean_text(text: str):
    """
    Enhanced text cleaning for OCR output - MAXIMUM ACCURACY
    
    Removes:
    - Multiple spaces
    - Common OCR artifacts  
    - Weird characters
    - Orphaned punctuation
    - Known OCR confusion patterns
    """
    
    if not text:
        return ""
    
    # Remove common OCR artifacts
    text = text.replace('|', 'I')
    text = text.replace('~', '-')
    text = text.replace('_', ' ')
    text = text.replace('`', '\'')
    text = text.replace('´', '\'')
    
    # Remove multiple consecutive special characters
    text = re.sub(r'[^\w\s\u0980-\u09FF.,!?;:()\[\]{}"\'।-]+', ' ', text)
    
    # Remove standalone symbols (1-2 non-alphanumeric)
    text = re.sub(r'\b[^a-zA-Z\u0980-\u09FF0-9]{1,2}\b', ' ', text)
    
    # Fix spacing around punctuation
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    text = re.sub(r'([.,!?;:])\s*', r'\1 ', text)
    
    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def fix_english_ocr_errors(text: str):
    """
    Fix common English OCR character confusion errors
    """
    if not text:
        return text
    
    # Apply all known English confusion fixes
    for old, new in ENGLISH_CONFUSIONS.items():
        text = text.replace(old, new)
    
    # Fix I/l/1 at start of sentences
    text = re.sub(r'(?<=[.!?]\s)[l1](?=\s)', 'I', text)
    text = re.sub(r'^[l1](?=\s)', 'I', text)
    
    # Fix "T" instead of "I" at sentence start (common OCR error)
    text = re.sub(r'(?<=[.!?]\s)T(?=\s[a-z])', 'I', text)
    text = re.sub(r'^T(?=\s[a-z])', 'I', text)
    
    # Fix "J" instead of "I" (common OCR error)
    text = re.sub(r'\bJ\s+(had|have|was|am|will|would|could|should|can|may|might|must)\b', r'I \1', text)
    
    # Fix numbers in words
    text = re.sub(r'\b([a-zA-Z]+)1([a-zA-Z]+)\b', r'\1l\2', text)  # 1 in middle of word -> l
    text = re.sub(r'\b([a-zA-Z]+)0([a-zA-Z]+)\b', r'\1o\2', text)  # 0 in middle of word -> o
    
    return text


def fix_bangla_ocr_errors(text: str):
    """
    Fix common Bangla OCR errors
    """
    if not text:
        return text
    
    # Apply all known Bangla confusion fixes
    for old, new in BANGLA_CONFUSIONS.items():
        text = text.replace(old, new)
    
    return text


def remove_noise_patterns(text: str, langs=None):
    """
    Remove known noise patterns specific to languages - MAXIMUM ACCURACY
    """
    
    if not text or not langs:
        return text
    
    # =====================================================
    # BANGLA NOISE REMOVAL (AGGRESSIVE)
    # =====================================================
    if 'bn' in langs:
        
        # Fix common Bangla OCR errors first
        text = fix_bangla_ocr_errors(text)
        
        # Remove ALL English words from pure Bangla text
        # Remove 1-2 letter English
        text = re.sub(r'(?<![\u0980-\u09FF])[a-zA-Z]{1,2}(?![\u0980-\u09FF])', ' ', text)
        
        # Remove 3-10 letter English words (OCR junk)
        text = re.sub(r'(?<![\u0980-\u09FF])[a-zA-Z]{3,10}(?![\u0980-\u09FF])', ' ', text)
        
        # Remove any remaining English
        text = re.sub(r'\b[a-zA-Z]+\b', ' ', text)
        
        # Remove standalone numbers that are likely noise
        text = re.sub(r'(?<![\u0980-\u09FF\d])\d{1,2}(?![\u0980-\u09FF\d])', ' ', text)
        
        # Remove repeated punctuation
        text = re.sub(r'[.]{2,}', '.', text)
        text = re.sub(r'[,]{2,}', ',', text)
        text = re.sub(r'[\']{2,}', '\'', text)
        text = re.sub(r'["]{2,}', '"', text)
        
        # Clean up spaces
        text = re.sub(r'\s{2,}', ' ', text)
    
    # =====================================================
    # ENGLISH NOISE REMOVAL AND FIXES
    # =====================================================
    if 'en' in langs and 'bn' not in langs:
        
        # Fix common English OCR errors
        text = fix_english_ocr_errors(text)
        
        # Fix l/I/1 confusion at word boundaries
        text = re.sub(r'\bl\s', 'I ', text)
        text = re.sub(r'^\s*l\s', 'I ', text, flags=re.MULTILINE)
        
        # Fix "le" at start of sentence (should be "He")
        text = re.sub(r'(?<=[.!?]\s)le\s', 'He ', text)
        text = re.sub(r'^le\s', 'He ', text)
        
        # Fix "his" that should be "he" (often OCR error)
        text = re.sub(r'\bhis\s+(was|is|went|came|had|has|said|could|would|should|must|might|may|will|can)\b', 
                     r'he \1', text)
        
        # Remove repeated punctuation
        text = re.sub(r'[.]{2,}', '.', text)
        text = re.sub(r'[,]{2,}', ',', text)
        
        # Fix hyphenated words at line breaks
        text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
        
        # Clean up spaces
        text = re.sub(r'\s{2,}', ' ', text)
    
    return text.strip()
