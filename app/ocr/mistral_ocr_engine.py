import base64
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Thread-pool for offloading blocking Mistral SDK calls from async handlers.
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mistral_ocr")

# Sub-directory under settings.UPLOAD_DIR where OCR-extracted images are stored.
OCR_IMAGES_SUBDIR = "ocr_images"


# ── confidence calculation ────────────────────────────────────────────────────

def _compute_page_confidence(text: str) -> float:
    """Compute a confidence score (0–100) from the extracted markdown text.

    Uses three weighted signals so scores vary meaningfully across documents:

    Signal 1 — Bad character ratio  (weight 50%):
        Counts Unicode replacement chars (U+FFFD) and non-printable control
        characters (except \\n, \\r, \\t).  Clean text scores 1.0 here.

    Signal 2 — Alphanumeric density  (weight 30%):
        Fraction of the *plain* text (markdown stripped) that consists of
        letters or digits.  Garbage/symbol-heavy output scores lower.

    Signal 3 — Word plausibility  (weight 20%):
        Ratio of 2–20 character word-like tokens to all whitespace-separated
        tokens.  Very short or very long "words" (rubbish sequences) reduce
        this score.

    Empty page  → 0.0
    Typical clean page → ~85–95  (not always 99.9)
    Heavy noise → proportionally lower
    """
    if not text:
        return 0.0

    total = len(text)

    # --- Signal 1: bad characters ---
    bad = sum(
        1 for c in text
        if c == "\ufffd"
        or (ord(c) < 32 and c not in ("\n", "\r", "\t"))
    )
    bad_score = 1.0 - (bad / total)

    # Strip markdown constructs to measure actual content
    plain = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)   # image refs
    plain = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", plain)   # links
    plain = re.sub(r"```[\s\S]*?```", " ", plain)         # fenced code blocks
    plain = re.sub(r"`[^`]+`", " ", plain)                # inline code
    plain = re.sub(r"[#*_~|<>{}\\\-=+]", " ", plain)     # markup symbols
    plain = re.sub(r"\s+", " ", plain).strip()

    if not plain:
        return round(min(99.9, max(0.0, bad_score * 50.0)), 2)

    # --- Signal 2: alphanumeric density ---
    alnum_count = sum(1 for c in plain if c.isalnum())
    alnum_ratio = alnum_count / len(plain)

    # --- Signal 3: word plausibility ---
    all_tokens = plain.split()
    plausible_words = [t for t in all_tokens if 2 <= len(t) <= 20]
    word_score = len(plausible_words) / max(len(all_tokens), 1)

    confidence = (
        bad_score   * 50.0
        + alnum_ratio * 30.0
        + word_score  * 20.0
    )
    return round(min(99.9, max(0.0, confidence)), 2)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_client():
    """Return a Mistral client using the configured API key."""
    try:
        from mistralai import Mistral
    except ImportError as exc:
        raise ImportError(
            "mistralai package is not installed. Run: pip install mistralai"
        ) from exc

    api_key = settings.MISTRAL_API_KEY
    if not api_key:
        raise ValueError(
            "MISTRAL_API_KEY is not configured. "
            "Add MISTRAL_API_KEY=<your-key> to your .env file."
        )
    return Mistral(api_key=api_key)


def _detect_image_mime(file_bytes: bytes) -> str:
    """Detect the MIME type of an image from its magic bytes."""
    if file_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if file_bytes[:4] in (b"GIF8",):
        return "image/gif"
    if file_bytes[:2] == b"BM":
        return "image/bmp"
    if file_bytes[:4] == b"RIFF" and b"WEBP" in file_bytes[:12]:
        return "image/webp"
    if file_bytes[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return "image/jpeg"


def _detect_base64_mime(b64_str: str) -> str:
    """Guess image MIME from the first bytes of a base64 string."""
    try:
        header = base64.b64decode(b64_str[:16] + "==")
        return _detect_image_mime(header)
    except Exception:
        return "image/jpeg"


def _mime_to_ext(mime: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png":  "png",
        "image/gif":  "gif",
        "image/bmp":  "bmp",
        "image/webp": "webp",
        "image/tiff": "tiff",
    }.get(mime, "jpg")


def get_ocr_images_dir() -> Path:
    """Return the absolute directory where OCR-extracted images are stored (created if needed)."""
    p = Path(settings.UPLOAD_DIR).resolve() / OCR_IMAGES_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build_image_url(filename: str) -> str:
    """Build the URL for a saved OCR image.

    Uses API_BASE_URL if configured (e.g. https://api.example.com), otherwise
    falls back to a relative path that works for same-origin frontend requests.
    """
    base = (settings.API_BASE_URL or "").rstrip("/")
    if base:
        return f"{base}/api/v1/ocr/images/{filename}"
    return f"/api/v1/ocr/images/{filename}"


def save_ocr_image_b64(b64_str: str, page_num: int) -> dict:
    """Decode a base64 image string, save it to disk, and return metadata.

    Mistral returns image_base64 with a data URI prefix such as
    ``data:image/jpeg;base64,/9j/4AAQ...`` — this function strips it before
    decoding so the saved file is a valid image.
    """
    # Strip data URI prefix if present: "data:<mime>;base64,<data>"
    if b64_str.startswith("data:"):
        # everything after the first comma is the actual base64 payload
        b64_str = b64_str.split(",", 1)[-1]

    mime      = _detect_base64_mime(b64_str)
    ext       = _mime_to_ext(mime)
    filename  = f"ocr_img_{uuid.uuid4().hex}.{ext}"
    save_path = get_ocr_images_dir() / filename

    img_bytes = base64.b64decode(b64_str)
    save_path.write_bytes(img_bytes)

    return {
        "filename": filename,
        "url":      _build_image_url(filename),
        "mime":     mime,
        "page":     page_num,
        "size_kb":  round(len(img_bytes) / 1024, 1),
    }


def _replace_images_with_urls(
    markdown: str, images: list, page_num: int
) -> tuple[str, list]:
    """Save each extracted image to disk and replace Mistral's internal
    ``![id](id)`` tokens with standard ``![alt](url)`` pointing to the
    image-serving endpoint.
    """
    if not images:
        return markdown, []

    record_map: dict[str, dict] = {}
    image_records: list[dict] = []

    for img in images:
        img_id = getattr(img, "id", None)
        b64    = getattr(img, "image_base64", None) or ""
        if not img_id or not b64:
            continue
        try:
            rec = save_ocr_image_b64(b64, page_num)
            rec["image_id"] = img_id
            record_map[img_id] = rec
            image_records.append(rec)
        except Exception as exc:
            logger.warning(f"Failed to save OCR image {img_id} on page {page_num}: {exc}")

    if not record_map:
        return markdown, image_records

    def _lookup(ref: str):
        if ref in record_map:
            return record_map[ref]
        for k, v in record_map.items():
            if k.startswith(ref) or ref.startswith(k):
                return v
        return None

    def _replace(match: re.Match) -> str:
        alt = match.group(1) or "image"
        ref = match.group(2)
        rec = _lookup(ref)
        if rec is None:
            return match.group(0)
        return f"![{alt}]({rec['url']})"

    updated_md = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", _replace, markdown)
    return updated_md, image_records


def _normalize_table_markdown(content: str) -> str:
    """Normalize a markdown table so it renders correctly in any markdown parser.

    Handles all quirks that Mistral OCR produces:

    1. **Embedded newlines in cells** — Mistral puts real ``\\n`` inside cell
       text (e.g. ``| ৩\\nশাখা | ...``).  Parser treats those as new rows,
       breaking the table.  We rejoin continuation lines (lines that don't
       start with ``|``) onto the previous row with a space.

    2. **Cross-page orphan rows** — When a large table spans multiple PDF
       pages, the first page's final partial rows overflow into the next
       page's table content, appearing *before* the ``| --- |`` separator.
       Standard markdown requires exactly one header row above ``| --- |``;
       additional rows above it become garbled fake headers.  We detect these
       orphan pre-separator rows and either:
       - promote them to regular body rows (after the separator), or
       - strip them if they are entirely empty / just punctuation.

    3. **Multiple consecutive blank lines** — squeezed to a single blank.

    4. **Extra spaces inside cells** — collapsed to single spaces.

    5. **Missing separator** — if the table has data rows but no ``| --- |``
       we insert one after the first row so it renders as a valid table.
    """
    # ── Step 1: join continuation (non-pipe) lines back onto their row ──────
    lines   = content.splitlines()
    joined  = []
    pending = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if pending:
                joined.append(pending)
                pending = ""
            joined.append("")
            continue

        if stripped.startswith("|"):
            if pending:
                joined.append(pending)
            pending = stripped
        else:
            # continuation of the previous cell
            if pending:
                pending = pending.rstrip() + " " + stripped
            else:
                pending = stripped

    if pending:
        joined.append(pending)

    # ── Step 2: collapse extra spaces inside cells ───────────────────────────
    rows: list[str] = []
    for row in joined:
        if row.startswith("|"):
            row = re.sub(r" {2,}", " ", row)
        rows.append(row)

    # Remove leading/trailing blank lines
    while rows and not rows[0]:
        rows.pop(0)
    while rows and not rows[-1]:
        rows.pop()

    if not rows:
        return content  # nothing to fix

    # ── Step 3: fix cross-page orphan rows above | --- | separator ──────────
    # Find the index of the first separator row
    sep_idx: int | None = None
    for i, row in enumerate(rows):
        if re.match(r"^\|\s*[-:]+[\s|:-]*\|$", row):
            sep_idx = i
            break

    if sep_idx is not None:
        orphans  = rows[:sep_idx]       # every row above the separator
        rest     = rows[sep_idx + 1:]   # body rows after separator

        def _is_empty_row(r: str) -> bool:
            """True when the row has no meaningful textual content."""
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            return all(not c or c in ("-", "–", "—", ".") for c in cells)

        def _looks_like_header(r: str) -> bool:
            """True when most cells are non-empty — indicates a real column header row."""
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            if not cells:
                return False
            non_empty = sum(1 for c in cells if c)
            return non_empty / max(len(cells), 1) >= 0.5  # ≥50 % cells filled

        if len(orphans) == 0:
            # No header at all — insert a synthetic blank header so markdown
            # renders the table rather than rejecting it.
            col_count = max(
                (rows[sep_idx].count("|") - 1),
                *[r.count("|") - 1 for r in rest if r.startswith("|")],
                1,
            )
            blank_header = "| " + " | ".join([""] * col_count) + " |"
            rows = [blank_header, rows[sep_idx]] + rest

        elif len(orphans) == 1 and _looks_like_header(orphans[0]):
            # Exactly one row before --- and it has enough content → real header.
            # Leave untouched.
            pass

        else:
            # Multiple rows above ---, or the single row looks like an orphan.
            # Keep the last row before --- as the header if it looks like one;
            # otherwise use a blank synthetic header.
            real_header_candidate = orphans[-1]
            above_header          = orphans[:-1]

            if _looks_like_header(real_header_candidate):
                header_row = real_header_candidate
            else:
                # Demote this row too — all orphans go to body
                above_header  = orphans
                col_count     = rows[sep_idx].count("|") - 1
                header_row    = "| " + " | ".join([""] * max(col_count, 1)) + " |"

            # Non-empty orphans become the first body rows (they carry real data)
            kept_orphans = [o for o in above_header if not _is_empty_row(o)]
            rows = [header_row, rows[sep_idx]] + kept_orphans + rest

    else:
        # No separator found — insert one after the first table row so the
        # table renders in markdown (first row becomes the header).
        table_rows = [r for r in rows if r.startswith("|")]
        if len(table_rows) > 1:
            first_pipe_idx = next(i for i, r in enumerate(rows) if r.startswith("|"))
            col_count = rows[first_pipe_idx].count("|") - 1
            sep = "| " + " | ".join(["---"] * max(col_count, 1)) + " |"
            rows.insert(first_pipe_idx + 1, sep)

    # ── Step 4: squeeze consecutive blank lines ──────────────────────────────
    final: list[str] = []
    prev_blank = False
    for row in rows:
        is_blank = not row.strip()
        if is_blank and prev_blank:
            continue
        final.append(row)
        prev_blank = is_blank

    return "\n".join(final)


def _replace_tables_with_content(markdown: str, tables) -> str:
    """Replace Mistral table placeholder links with their actual content.

    When ``table_format="markdown"`` (or ``"html"``), Mistral embeds tables
    in the page markdown as link references::

        [tbl-0.md](tbl-0.md)

    Each table's real content lives in ``page.tables[i].content``.
    This function builds a lookup map from table ``id`` → ``content`` and
    substitutes every placeholder so the final markdown contains the actual
    table rows instead of dead links.

    Handles both id styles Mistral uses in the wild:
      * ``id = "tbl-0"``   → link is ``[tbl-0.md](tbl-0.md)``
      * ``id = "tbl-0.md"`` → link is ``[tbl-0.md](tbl-0.md)``
    """
    if not tables:
        return markdown

    # Build a normalised id → content map.
    # Store every table under BOTH the raw id and the id without ".md"
    # so lookups succeed regardless of which variant Mistral uses.
    table_map: dict[str, str] = {}
    for tbl in tables:
        tbl_id      = getattr(tbl, "id",      None)
        tbl_content = getattr(tbl, "content", None)
        if not tbl_id or not tbl_content:
            continue
        cleaned = _normalize_table_markdown(tbl_content)
        table_map[tbl_id] = cleaned
        # Also index without the ".md" suffix (and with it) for fuzzy matching
        if tbl_id.endswith(".md"):
            table_map[tbl_id[:-3]] = cleaned
        else:
            table_map[tbl_id + ".md"] = cleaned

    if not table_map:
        return markdown

    def _replace_table(match: re.Match) -> str:
        link_text = match.group(1)          # e.g. "tbl-0.md"
        href      = match.group(2)          # e.g. "tbl-0.md"

        # Try exact matches first (both link text and href as keys)
        for key in (link_text, href,
                    link_text[:-3] if link_text.endswith(".md") else link_text + ".md",
                    href[:-3]      if href.endswith(".md")      else href      + ".md"):
            if key in table_map:
                return table_map[key]

        # Last resort: prefix / substring match
        for k, v in table_map.items():
            if k.startswith(link_text) or link_text.startswith(k):
                return v

        return match.group(0)   # leave untouched if nothing matched

    # Match plain (non-image) markdown links whose text/href end with ".md"
    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)", _replace_table, markdown)


# ── main sync worker (runs in thread pool) ───────────────────────────────────

def _run_mistral_ocr_sync(
    file_bytes: bytes,
    file_type: str,
    *,
    table_format: str = "markdown",
    extract_header: bool = True,
    extract_footer: bool = True,
) -> dict:
    """Blocking Mistral OCR call.  Called via ``run_mistral_ocr`` (async wrapper).

    Accepts both ``"pdf"`` and ``"image"`` (JPEG, PNG, BMP, WebP, TIFF, GIF).

    Args:
        file_bytes:      Raw document bytes.
        file_type:       ``"pdf"`` or ``"image"``.
        table_format:    ``"markdown"`` (default, inline pipe tables) or
                         ``"html"`` (<table> elements).  ``"markdown"`` matches
                         the *Inline markdown* option in Mistral Studio and
                         renders correctly in all markdown viewers.
        extract_header:  Extract page header text (default True).
        extract_footer:  Extract page footer text (default True).

    Returns a dict with:
        pages_data       – list of per-page dicts; confidence is computed
                           dynamically, not hardcoded
        text             – full document markdown (pages separated by ``---``)
        confidence       – float average across pages (0–100)
        pages            – int
        images_count     – int (extracted figures saved to disk)
        extracted_images – list[dict] — url / filename / mime / page / size_kb
        usage            – dict with Mistral usage info
        engine           – str
        features         – list[str]
    """
    client = _get_client()
    b64_doc = base64.b64encode(file_bytes).decode("utf-8")

    if file_type == "pdf":
        document = {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{b64_doc}",
        }
    elif file_type == "image":
        mime = _detect_image_mime(file_bytes)
        document = {
            "type": "image_url",
            "image_url": f"data:{mime};base64,{b64_doc}",
        }
    else:
        raise ValueError(f"Unsupported file type for Mistral OCR: {file_type!r}")

    logger.info(
        f"Mistral OCR → sending {file_type.upper()} "
        f"({len(file_bytes) // 1024}KB) to mistral-ocr-latest"
    )
    t0 = time.time()

    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document=document,
        table_format=table_format,       # "markdown" → inline pipe tables (default)
        include_image_base64=True,       # Return extracted images as base64
        extract_header=extract_header,   # Capture page headers
        extract_footer=extract_footer,   # Capture page footers
    )

    elapsed = time.time() - t0
    logger.info(f"Mistral OCR ← response received in {elapsed:.2f}s")

    pages_data:        list[dict]  = []
    all_image_records: list[dict]  = []
    page_texts:        list[str]   = []
    page_confidences:  list[float] = []

    for page in ocr_response.pages:
        page_num = page.index + 1   # Mistral pages are 0-indexed
        raw_md   = page.markdown or ""
        images   = page.images or []
        tables   = page.tables  or []

        # 1. Replace table placeholder links with real table content
        md_with_tables = _replace_tables_with_content(raw_md, tables)

        # 2. Save images to disk → replace markdown refs with public URLs
        md_with_urls, page_image_records = _replace_images_with_urls(
            md_with_tables, images, page_num
        )
        all_image_records.extend(page_image_records)

        # 3. Prepend header / append footer if Mistral extracted them
        header_text = getattr(page, "header", None) or ""
        footer_text = getattr(page, "footer", None) or ""
        if header_text:
            md_with_urls = header_text.strip() + "\n\n" + md_with_urls
        if footer_text:
            md_with_urls = md_with_urls + "\n\n" + footer_text.strip()

        # Compute confidence dynamically from actual text quality
        conf = _compute_page_confidence(md_with_urls)
        page_confidences.append(conf)

        pages_data.append({
            "page_number":     page_num,
            "text":            md_with_urls,
            "confidence":      conf,
            "character_count": len(md_with_urls),
        })
        page_texts.append(md_with_urls)

    full_text = "\n\n---\n\n".join(page_texts)
    avg_conf  = round(
        sum(page_confidences) / len(page_confidences)
        if page_confidences else 0.0,
        2,
    )

    usage: dict = {}
    if hasattr(ocr_response, "usage_info") and ocr_response.usage_info:
        u = ocr_response.usage_info
        usage = {
            "pages_processed": getattr(u, "pages_processed", None),
            "doc_size_bytes":  getattr(u, "doc_size_bytes",  None),
        }

    logger.info(
        f"Mistral OCR complete: {len(pages_data)} pages, "
        f"{len(all_image_records)} images saved, "
        f"avg confidence {avg_conf:.1f}%, {elapsed:.2f}s"
    )

    return {
        "pages_data":       pages_data,
        "text":             full_text,
        "confidence":       avg_conf,
        "pages":            len(pages_data),
        "images_count":     len(all_image_records),
        "extracted_images": all_image_records,
        "usage":            usage,
        "engine":           "Mistral OCR",
        "features": [
            "Structure-preserving markdown output",
            "Inline markdown table extraction (pipe tables)",
            "LaTeX / math equation extraction",
            "Extracted images served via URL",
            "Dynamic per-page confidence scoring",
            "Auto language detection",
            "Header and footer extraction",
            "Multi-page PDF and standalone image support",
        ],
    }


# ── public async API ──────────────────────────────────────────────────────────

async def run_mistral_ocr(
    file_bytes: bytes,
    file_type: str,
    *,
    table_format: str = "markdown",
    extract_header: bool = True,
    extract_footer: bool = True,
) -> dict:
    """Async wrapper: run Mistral OCR in a thread pool.

    Args:
        file_bytes:      Raw document bytes (PDF or any image format).
        file_type:       ``"pdf"`` or ``"image"``.
        table_format:    ``"markdown"`` (default) for inline pipe tables that
                         render in all markdown viewers, or ``"html"`` for
                         ``<table>`` elements.  Matches the *Inline markdown*
                         option shown in Mistral Studio.
        extract_header:  Include page header text in the output (default True).
        extract_footer:  Include page footer text in the output (default True).

    Returns the structured dict from ``_run_mistral_ocr_sync``.
    """
    import asyncio
    from functools import partial
    loop = asyncio.get_running_loop()
    fn = partial(
        _run_mistral_ocr_sync,
        file_bytes,
        file_type,
        table_format=table_format,
        extract_header=extract_header,
        extract_footer=extract_footer,
    )
    return await loop.run_in_executor(_EXECUTOR, fn)
