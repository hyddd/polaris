"""Tests for src.core.logging_config — structured logging setup."""

import logging
import json

from src.core.observability.logging_config import setup_logging, ColorFormatter, JSONFormatter


def test_setup_logging_text_mode():
    setup_logging(level=logging.DEBUG, json_mode=False)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, ColorFormatter)


def test_setup_logging_json_mode():
    setup_logging(level=logging.WARNING, json_mode=True)
    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JSONFormatter)

    handler = root.handlers[0]
    record = logging.LogRecord(
        name="test", level=logging.WARNING, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None, func_name="test_func",
    )
    output = handler.format(record)
    data = json.loads(output)
    assert data["level"] == "WARNING"
    assert data["logger"] == "test"
    assert data["msg"] == "hello"
    assert "ts" in data
    assert "loc" in data
