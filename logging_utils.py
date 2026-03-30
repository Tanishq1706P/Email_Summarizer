import json
import logging
import sys
from typing import Any, Dict


def setup_logging(name: str) -> logging.Logger:
    """
    Production-ready structured logging setup.
    Compatible with all current imports in codebase.
    """

    # Structured logging with JSON formatter for production
    class JSONFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            log_entry: Dict[str, Any] = {
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
                "props": getattr(record, "props", {}),
            }
            if record.exc_info:
                log_entry["exc_info"] = self.formatException(record.exc_info)
            return json.dumps(log_entry, ensure_ascii=False)

    # Root logger config
    logging.root.handlers.clear()  # Clear any existing handlers
    logging.root.setLevel(logging.INFO)

    # Console handler with JSON
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    json_formatter = JSONFormatter()
    console_handler.setFormatter(json_formatter)
    logging.root.addHandler(console_handler)

    # Named logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Prevent double logging

    return logger
