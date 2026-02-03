from textblob import TextBlob
from rapidfuzz import process, fuzz
import os
import re

# ======================================================
# Load Bangla dictionary
# ======================================================

BANGLA_DICT_PATH = os.path.join(
    os.path.dirname(__file__),
    "bangla_words.txt"
)

if os.path.exists(BANGLA_DICT_PATH):
    with open(BANGLA_DICT_PATH, encoding="utf-8") as f:
        # remove duplicates + empty lines
        BANGLA_WORDS = list({w.strip() for w in f if w.strip()})
else:
    BANGLA_WORDS = []

# ======================================================
# Regex helpers
# ======================================================

# Only Bangla unicode characters
BANGLA_RE = re.compile(r'^[\u0980-\u09FF]+$')


def is_valid_bangla(word: str) -> bool:
    """
    True only if word contains Bangla letters only.
    Prevents correcting junk like: hb, 123, !!! etc
    """
    return bool(BANGLA_RE.match(word))


# ======================================================
# English correction (TextBlob)
# ======================================================

def correct_english(text: str):
    """
    Safe English spell correction
    """
    try:
        return str(TextBlob(text).correct())
    except Exception:
        # never break pipeline
        return text


# ======================================================
# Bangla correction (RapidFuzz)
# ======================================================

def correct_bangla_word(word: str):
    """
    Correct a single Bangla word safely.
    NEVER throws exceptions.
    """

    # -------------------------
    # skip fast cases
    # -------------------------

    if not word:
        return word

    if len(word) < 2:  # tiny tokens usually noise
        return word

    if not BANGLA_WORDS:  # dictionary missing
        return word

    if not is_valid_bangla(word):  # skip non-Bangla text
        return word

    # -------------------------
    # fuzzy match
    # -------------------------

    result = process.extractOne(
        word,
        BANGLA_WORDS,
        scorer=fuzz.ratio
    )

    # 🔴 critical crash fix
    if result is None:
        return word

    match, score, _ = result

    # only accept strong matches
    if score > 85:
        return match

    return word


def correct_bangla(text: str):
    """
    Correct Bangla sentence word-by-word
    """
    try:
        words = text.split()
        corrected = [correct_bangla_word(w) for w in words]
        return " ".join(corrected)
    except Exception:
        return text


# ======================================================
# Main unified function
# ======================================================

def correct_spelling(text: str, langs: list):
    """
    Unified spell corrector
    langs example: ['bn'], ['en'], ['bn','en']
    """

    if not text:
        return text

    try:
        if 'en' in langs:
            text = correct_english(text)

        if 'bn' in langs:
            text = correct_bangla(text)

        # Arabic intentionally skipped
        # (protects Qur'an / Islamic words)

        return text

    except Exception:
        # absolute safety — never crash API
        return text
