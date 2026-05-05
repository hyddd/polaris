"""Tests for src.core.schema -- Pydantic config validation."""

import pytest
from pydantic import ValidationError

from src.core.config.schema import AppConfig


def test_valid_config():
    """Valid config passes validation."""
    data = {
        "llm": {
            "api_key": "sk-test",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
    }
    cfg = AppConfig(**data)
    assert cfg.llm.api_key == "sk-test"
    assert cfg.llm.model == "gpt-4o"


def test_missing_api_key():
    """Missing api_key raises ValidationError."""
    data = {
        "llm": {
            "model": "gpt-4o",
        },
    }
    with pytest.raises(ValidationError) as exc_info:
        AppConfig(**data)
    assert "api_key" in str(exc_info.value)


def test_invalid_temperature():
    """Temperature out of range raises ValidationError."""
    data = {
        "llm": {
            "api_key": "sk-test",
            "temperature": 3.0,  # max is 2
        },
    }
    with pytest.raises(ValidationError) as exc_info:
        AppConfig(**data)
    assert "temperature" in str(exc_info.value)


def test_default_values():
    """Unspecified fields use defaults."""
    data = {
        "llm": {
            "api_key": "sk-test",
        },
    }
    cfg = AppConfig(**data)
    assert cfg.llm.model == "gpt-4o"
    assert cfg.llm.temperature == 0.7
    assert cfg.llm.max_tokens == 4096
    assert cfg.storage.calendar_file == "data/calendar.json"
    assert cfg.heartbeat.enabled is False
    assert cfg.logging.level == "INFO"
    assert cfg.admin_token is None


def test_extra_fields_allowed():
    """Extra fields do not raise errors (model_config extra=allow)."""
    data = {
        "llm": {
            "api_key": "sk-test",
        },
        "embedding": {
            "model": "some-embedding-model",
        },
        "tools": {
            "calendar": {"use_mock": True},
        },
        "server": {
            "host": "0.0.0.0",
            "port": 8000,
        },
    }
    cfg = AppConfig(**data)
    # extra fields are stored but not typed
    assert cfg.llm.api_key == "sk-test"
