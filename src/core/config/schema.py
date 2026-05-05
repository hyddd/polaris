"""Configuration schema — Pydantic models for YAML config validation.

Usage:
    from src.core.schema import AppConfig
    validated = AppConfig(**raw_dict)
"""

from pydantic import BaseModel, Field
from typing import Optional


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str
    base_url: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, gt=0)


class StorageConfig(BaseModel):
    calendar_file: str = "data/calendar.json"
    todos_file: str = "data/todos.json"
    reminders_file: str = "data/reminders.json"
    notes_dir: str = "data/notes"
    vector_db_dir: str = "data/chroma"
    scheduler_file: str = "data/scheduler.json"


class ChannelConfig(BaseModel):
    plugin: str
    enabled: bool = True


class HeartbeatConfig(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=60, gt=0)
    channel: str = ""
    prompt_file: str = "data/heartbeat.md"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "text"


class VoiceConfig(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    stt_model: str = "whisper-1"
    tts_model: str = "mimo-v2.5-tts"
    voice: str = "冰糖"
    context: str = ""  # MiMo 风格控制指令


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    public_url: str = ""  # 服务器公网地址，用于 QQ 语音消息上传
    admin_token: Optional[str] = None
    rate_limit_max_requests: int = 30
    rate_limit_window_seconds: int = 60
    max_sessions: int = 10


class AppConfig(BaseModel):
    model_config = {"extra": "allow"}

    llm: LLMConfig
    voice: VoiceConfig = VoiceConfig()
    storage: StorageConfig = StorageConfig()
    channels: dict[str, ChannelConfig] = {}
    heartbeat: HeartbeatConfig = HeartbeatConfig()
    logging: LoggingConfig = LoggingConfig()
    server: ServerConfig = ServerConfig()
    admin_token: Optional[str] = None
    demo_mode: Optional[int] = None
