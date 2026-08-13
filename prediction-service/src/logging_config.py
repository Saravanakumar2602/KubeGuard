"""Structured logging configuration for KubeGuard supporting text and JSON formats."""

from __future__ import annotations

import sys
import time
import json
import logging
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """Custom logging formatter that outputs log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include optional structured context if present in record.__dict__
        for attr in ["namespace", "pod", "duration_seconds", "error_type"]:
            val = getattr(record, attr, None)
            if val is not None:
                log_entry[attr] = val

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(log_level: str = "INFO", log_format: str = "text") -> None:
    """Configure the root logger with text or JSON formatting based on application configuration."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to avoid duplicate log outputs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    root_logger.addHandler(handler)
