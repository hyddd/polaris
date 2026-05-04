import logging
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        # 附加 contextvars 信息
        try:
            from src.core.context import get_channel, get_session_id
            channel = get_channel()
            session_id = get_session_id()
            if channel:
                log["channel"] = channel
            if session_id:
                log["session_id"] = session_id
        except Exception:
            pass
        return json.dumps(log, ensure_ascii=False)


def setup_logging(level=logging.INFO, json_mode=False):
    root = logging.getLogger("polaris")
    root.setLevel(level)
    # 清除已有 handler 避免重复
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(
        JSONFormatter() if json_mode
        else logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(handler)
