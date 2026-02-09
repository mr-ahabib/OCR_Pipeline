import logging
import os
from datetime import datetime
from pathlib import Path


class StructuredFileHandler(logging.FileHandler):
    """Custom file handler that writes logs with structured headers to logs.txt"""
    
    def __init__(self, log_file_path):
        super().__init__(log_file_path, mode='a', encoding='utf-8')
        self.log_counter = self._get_next_serial_number()
        self._ensure_header_exists()
    
    def _get_next_serial_number(self):
        """Get the next serial number for logs"""
        try:
            if os.path.exists(self.baseFilename) and os.path.getsize(self.baseFilename) > 0:
                with open(self.baseFilename, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    # Find the last serial number
                    for line in reversed(lines):
                        if line.strip() and not line.startswith('-') and not line.startswith('|'):
                            try:
                                # Split and get the first field which should be the serial
                                parts = line.split('|')
                                if len(parts) > 0:
                                    serial_str = parts[0].strip()
                                    if serial_str.isdigit():
                                        return int(serial_str) + 1
                            except:
                                continue
                    return 1
            else:
                return 1
        except:
            return 1
    
    def _ensure_header_exists(self):
        """Ensure the log file has proper headers for important events only"""
        try:
            if not os.path.exists(self.baseFilename) or os.path.getsize(self.baseFilename) == 0:
                with open(self.baseFilename, 'w', encoding='utf-8') as f:
                    f.write("=" * 120 + "\n")
                    f.write(f"{'OCR PIPELINE - IMPORTANT EVENTS LOG':^120}\n")
                    f.write("=" * 120 + "\n")
                    f.write(f"{'Serial':<8} | {'Date':<12} | {'Time':<10} | {'Level':<8} | {'Module/Function':<25} | {'Event/Error':<40}\n")
                    f.write("-" * 120 + "\n")
        except Exception as e:
            # Fallback - create simple header
            pass
    
    def emit(self, record):
        """Custom emit method to format log records with structured headers"""
        try:
            # Format the timestamp
            dt = datetime.fromtimestamp(record.created)
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M:%S')
            
            # Get module/function info
            module_func = f"{record.module}.{record.funcName}" if hasattr(record, 'funcName') else record.module
            
            # Truncate long messages for the main log, full message goes to details
            message_preview = record.getMessage()
            if len(message_preview) > 40:
                message_preview = message_preview[:37] + "..."
            
            # Create structured log entry
            log_entry = f"{self.log_counter:<8} | {date_str:<12} | {time_str:<10} | {record.levelname:<8} | {module_func:<25} | {message_preview:<40}\n"
            
            # Write to file
            with open(self.baseFilename, 'a', encoding='utf-8') as f:
                f.write(log_entry)
                
                # If it's an error or warning, add detailed info
                if record.levelname in ['ERROR', 'WARNING', 'CRITICAL']:
                    full_message = record.getMessage()
                    if len(full_message) > 40:
                        f.write(f"{'':>8}   Details: {full_message}\n")
                    
                    # Add exception info if present
                    if record.exc_info:
                        import traceback
                        f.write(f"{'':>8}   Exception: {traceback.format_exception(*record.exc_info)}\n")
                
                # Add separator for readability
                if record.levelname in ['ERROR', 'CRITICAL']:
                    f.write("-" * 120 + "\n")
            
            self.log_counter += 1
            
        except Exception:
            # Fallback to standard file handler
            super().emit(record)


def setup_file_logging(log_level=logging.WARNING):
    """Set up structured file logging for important events only"""
    
    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    log_file_path = log_dir / "logs.txt"
    
    # Create custom handler for important logs only
    file_handler = StructuredFileHandler(str(log_file_path))
    file_handler.setLevel(logging.WARNING)  # Only WARNING and above go to file
    
    # Create console handler for immediate feedback (can be more verbose)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # Create formatters
    file_formatter = logging.Formatter('%(message)s')  # Custom handler handles formatting
    console_formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        handlers=[file_handler, console_handler],
        force=True  # Override existing configuration
    )
    
    # Log session start as important event
    logger = logging.getLogger(__name__)
    logger.warning(f"OCR Pipeline SESSION STARTED at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return logger


def log_ocr_operation(operation_type, file_info, result=None, error=None):
    """Log important OCR operations only"""
    logger = logging.getLogger('ocr_operations')
    
    if error:
        logger.error(f"OCR {operation_type} FAILED - File: {file_info} - Error: {error}")
    else:
        confidence = result.get('confidence', 0) if result else 0
        pages = result.get('pages', 1) if result else 1
        # Only log low confidence results or failures as important
        if confidence < 80:
            logger.warning(f"OCR {operation_type} LOW CONFIDENCE - File: {file_info} - Pages: {pages} - Confidence: {confidence:.2f}%")
        # Don't log successful high-confidence operations to reduce log noise


def log_performance_metrics(operation, duration, pages=1, file_size=None):
    """Log performance issues only (slow operations)"""
    logger = logging.getLogger('performance')
    
    # Only log if operation is taking too long (performance issue)
    threshold = 10.0 if pages > 3 else 5.0  # Adjust threshold based on page count
    
    if duration > threshold:
        size_info = f"Size: {file_size//1024}KB" if file_size else ""
        logger.warning(f"SLOW PERFORMANCE - {operation} - Duration: {duration:.2f}s - Pages: {pages} {size_info}")