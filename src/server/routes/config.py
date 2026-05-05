"""Admin API: Config management and metrics."""
import re as _re

from fastapi import APIRouter
from pydantic import BaseModel

from src.core.config import config

router = APIRouter()

_SENSITIVE_KEY_PATTERN = _re.compile(r"KEY|SECRET|TOKEN|PASSWORD", _re.IGNORECASE)


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def _mask_value(key: str, value: str) -> str:
    if _is_sensitive_key(key):
        return "****"
    return str(value)


def _flatten_config(d: dict, prefix: str, out: list):
    """递归展平 YAML 配置树为 key=value 列表。"""
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            _flatten_config(v, full_key, out)
        else:
            out.append((full_key, v))


class ConfigUpdate(BaseModel):
    vars: dict[str, str]
    old_key: str | None = None  # 改名时传入旧 key，后端先删再写
    remove: bool = False        # 删除而非设置


@router.get("/api/config")
def get_config():
    cfg = config.as_dict()
    lines = []
    _flatten_config(cfg, "", lines)
    masked = {}
    for key, value in lines:
        masked[key] = _mask_value(key, value)
    return {"vars": masked}


@router.post("/api/config")
def update_config(req: ConfigUpdate):
    if req.remove:
        for key in req.vars:
            config.remove(key)
    else:
        if req.old_key and req.old_key not in req.vars:
            config.remove(req.old_key)
        for key, value in req.vars.items():
            config.set(key, value)
    config.reload()
    return {"ok": True}


@router.delete("/api/config/{key:path}")
def delete_config(key: str):
    config.remove(key)
    config.reload()
    return {"ok": True}


@router.get("/api/metrics")
def get_metrics():
    from src.core.observability import metrics
    return metrics.snapshot()
