import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── column widths ─────────────────────────────────────────────────────────────
_W_SERIAL  = 6
_W_DATE    = 12
_W_TIME    = 10
_W_LEVEL   = 8
_W_UID     = 8
_W_EMAIL   = 28
_W_MODULE  = 25
_W_EVENT   = 40
_SEP       = " | "
# Total ≈ 6+12+10+8+8+28+25+40 + 7*(3) = 158 chars


class StructuredFileHandler(logging.FileHandler):
    """Custom file handler that writes logs with structured, human-readable
    columns to logs.txt.

    Column layout:
        Serial | Date | Time | Level | User ID | User Email | Module/Function | Event
    """

    def __init__(self, log_file_path: str):
        super().__init__(log_file_path, mode="a", encoding="utf-8")
        self.log_counter = self._get_next_serial_number()
        self._ensure_header_exists()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _get_next_serial_number(self) -> int:
        try:
            if os.path.exists(self.baseFilename) and os.path.getsize(self.baseFilename) > 0:
                with open(self.baseFilename, "r", encoding="utf-8") as f:
                    for line in reversed(f.readlines()):
                        parts = line.split(_SEP)
                        if parts and parts[0].strip().isdigit():
                            return int(parts[0].strip()) + 1
            return 1
        except Exception:
            return 1

    def _ensure_header_exists(self):
        try:
            if not os.path.exists(self.baseFilename) or os.path.getsize(self.baseFilename) == 0:
                total_width = (
                    _W_SERIAL + _W_DATE + _W_TIME + _W_LEVEL
                    + _W_UID + _W_EMAIL + _W_MODULE + _W_EVENT
                    + len(_SEP) * 7
                )
                with open(self.baseFilename, "w", encoding="utf-8") as f:
                    f.write("=" * total_width + "\n")
                    f.write(f"{'OCR PIPELINE — OPERATION LOG':^{total_width}}\n")
                    f.write("=" * total_width + "\n")
                    header = (
                        f"{'#':<{_W_SERIAL}}"
                        f"{_SEP}{'Date':<{_W_DATE}}"
                        f"{_SEP}{'Time':<{_W_TIME}}"
                        f"{_SEP}{'Level':<{_W_LEVEL}}"
                        f"{_SEP}{'User ID':<{_W_UID}}"
                        f"{_SEP}{'User Email':<{_W_EMAIL}}"
                        f"{_SEP}{'Module/Function':<{_W_MODULE}}"
                        f"{_SEP}{'Event':<{_W_EVENT}}"
                    )
                    f.write(header + "\n")
                    f.write("-" * total_width + "\n")
        except Exception:
            pass

    # ── emit ──────────────────────────────────────────────────────────────────

    def emit(self, record: logging.LogRecord):
        try:
            dt = datetime.fromtimestamp(record.created)
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")

            module_func = (
                f"{record.module}.{record.funcName}"
                if hasattr(record, "funcName") else record.module
            )

            # User context (set via extra={} on the logger call, or "-" if absent)
            uid   = str(getattr(record, "user_id",    "-") or "-")
            email = str(getattr(record, "user_email", "-") or "-")

            message_preview = record.getMessage()
            if len(message_preview) > _W_EVENT:
                message_preview = message_preview[:_W_EVENT - 3] + "..."

            line = (
                f"{self.log_counter:<{_W_SERIAL}}"
                f"{_SEP}{date_str:<{_W_DATE}}"
                f"{_SEP}{time_str:<{_W_TIME}}"
                f"{_SEP}{record.levelname:<{_W_LEVEL}}"
                f"{_SEP}{uid:<{_W_UID}}"
                f"{_SEP}{email:<{_W_EMAIL}}"
                f"{_SEP}{module_func:<{_W_MODULE}}"
                f"{_SEP}{message_preview:<{_W_EVENT}}"
            )

            with open(self.baseFilename, "a", encoding="utf-8") as f:
                f.write(line + "\n")

                # Full message on the next line for errors/warnings
                if record.levelname in ("ERROR", "WARNING", "CRITICAL"):
                    full_msg = record.getMessage()
                    if len(full_msg) > _W_EVENT:
                        indent = " " * (_W_SERIAL + len(_SEP))
                        f.write(f"{indent}Details: {full_msg}\n")

                    if record.exc_info:
                        import traceback
                        indent = " " * (_W_SERIAL + len(_SEP))
                        tb = "".join(traceback.format_exception(*record.exc_info))
                        f.write(f"{indent}Exception: {tb}\n")

                if record.levelname in ("ERROR", "CRITICAL"):
                    total_width = (
                        _W_SERIAL + _W_DATE + _W_TIME + _W_LEVEL
                        + _W_UID + _W_EMAIL + _W_MODULE + _W_EVENT
                        + len(_SEP) * 7
                    )
                    f.write("-" * total_width + "\n")

            self.log_counter += 1
        except Exception:
            super().emit(record)


# ── setup ─────────────────────────────────────────────────────────────────────

def setup_file_logging(log_level: int = logging.WARNING) -> logging.Logger:
    """Configure structured file + console logging.

    File handler records WARNING and above (to reduce noise).
    Console handler uses *log_level* (INFO by default when called from service).
    """
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file_path = log_dir / "logs.txt"

    file_handler = StructuredFileHandler(str(log_file_path))
    file_handler.setLevel(logging.WARNING)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    file_handler.setFormatter(logging.Formatter("%(message)s"))
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )

    logging.basicConfig(level=log_level, handlers=[file_handler, console_handler], force=True)

    logger = logging.getLogger(__name__)
    logger.warning("OCR Pipeline SESSION STARTED at %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    return logger


# ── helpers for callers ───────────────────────────────────────────────────────

def log_ocr_operation(
    operation_type: str,
    file_info: str,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
):
    """Log an OCR operation with user context (id + email).

    Only failures and low-confidence results trigger a file write
    (WARNING/ERROR level) to keep the log readable.
    """
    _log = logging.getLogger("ocr_operations")
    extra = {"user_id": user_id or "-", "user_email": user_email or "-"}

    if error:
        _log.error(
            "OCR %s FAILED — File: %s — Error: %s",
            operation_type, file_info, error,
            extra=extra,
        )
        return

    if result:
        confidence = result.get("confidence", 0)
        pages      = result.get("pages", 1)
        engine     = result.get("engine", "unknown")
        if confidence < 80:
            _log.warning(
                "OCR %s LOW CONFIDENCE — Engine: %s — File: %s — Pages: %s — Conf: %.2f%%",
                operation_type, engine, file_info, pages, confidence,
                extra=extra,
            )
        else:
            # Always log successful OCR to track activity per user
            _log.warning(
                "OCR %s OK — Engine: %s — File: %s — Pages: %s — Conf: %.2f%%",
                operation_type, engine, file_info, pages, confidence,
                extra=extra,
            )


def log_performance_metrics(
    operation: str,
    duration: float,
    pages: int = 1,
    file_size: Optional[int] = None,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
):
    """Log slow operations to the structured log file."""
    _log = logging.getLogger("performance")
    extra = {"user_id": user_id or "-", "user_email": user_email or "-"}

    threshold = 10.0 if pages > 3 else 5.0
    if duration > threshold:
        size_info = f"Size: {file_size // 1024}KB" if file_size else ""
        _log.warning(
            "SLOW — %s — Duration: %.2fs — Pages: %s %s",
            operation, duration, pages, size_info,
            extra=extra,
        )
