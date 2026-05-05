"""Tests for src.core.logging_config — structured logging setup."""

import logging
import json

from src.core.observability.logging_config import setup_logging


def test_setup_logging_text_mode():
    setup_logging(level=logging.DEBUG, json_mode=False)
    root = logging.getLogger("polaris")
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    formatter = root.handlers[0].formatter
    assert isinstance(formatter, logging.Formatter)
    assert not hasattr(formatter, "format") or not isinstance(formatter, __import__("src.core.observability.logging_config", fromlist=["JSONFormatter"]).JSONFormatter)


def test_setup_logging_json_mode():
    from src.core.observability.logging_config import JSONFormatter
    setup_logging(level=logging.WARNING, json_mode=True)
    root = logging.getLogger("polaris")
    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JSONFormatter)

    # Verify JSON output format
    handler = root.handlers[0]
    record = logging.LogRecord(
        name="test", level=logging.WARNING, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None,
    )
    output = handler.format(record)
    data = json.loads(output)
    assert data["level"] == "WARNING"
    assert data["logger"] == "test"
    assert data["msg"] == "hello"
    assert "ts" in data
