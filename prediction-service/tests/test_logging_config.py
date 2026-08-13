"""Unit tests for text and JSON logging formatters."""

import json
import logging
import io
from logging_config import JsonFormatter, setup_logging


def test_json_formatter_valid_output():
    """Verify that JsonFormatter generates valid JSON strings with standard fields."""
    formatter = JsonFormatter()
    logger_name = "test-logger"
    record = logging.LogRecord(
        name=logger_name,
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test log message",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["logger"] == logger_name
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test log message"
    assert "timestamp" in parsed


def test_json_formatter_extra_fields():
    """Verify that extra contextual attributes are serialized into JSON."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="worker",
        level=logging.ERROR,
        pathname="worker.py",
        lineno=50,
        msg="Pod failed",
        args=(),
        exc_info=None,
    )
    record.namespace = "demo"
    record.pod = "demo-nginx-123"
    record.duration_seconds = 1.25
    record.error_type = "ValueError"

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["namespace"] == "demo"
    assert parsed["pod"] == "demo-nginx-123"
    assert parsed["duration_seconds"] == 1.25
    assert parsed["error_type"] == "ValueError"


def test_setup_logging_text_format():
    """Test setup_logging with text format configuration."""
    setup_logging(log_level="DEBUG", log_format="text")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) >= 1


def test_setup_logging_json_format():
    """Test setup_logging with JSON format configuration."""
    setup_logging(log_level="INFO", log_format="json")
    root = logging.getLogger()
    assert root.level == logging.INFO
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
