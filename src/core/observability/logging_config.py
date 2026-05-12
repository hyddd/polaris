import logging
import json
from datetime import datetime


# ANSI color codes
_COLORS = {
    logging.DEBUG: "\033[90m",     # gray
    logging.INFO: "\033[32m",      # green
    logging.WARNING: "\033[33m",   # yellow
    logging.ERROR: "\033[31m",     # red
    logging.CRITICAL: "\033[1;31m",  # bold red
}
_RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    """Text formatter with color and file:function:line location."""

    def format(self, record):
        color = _COLORS.get(record.levelno, "")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        loc = f"({record.filename}:{record.lineno}){record.funcName}()"
        return f"{color}[{record.levelname}]{_RESET} {ts} {loc} {record.getMessage()}"


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "loc": f"({record.filename}:{record.lineno}){record.funcName}",
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        try:
            from src.core.infra import get_channel, get_session_id
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
    formatter = JSONFormatter() if json_mode else ColorFormatter()

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root.addHandler(handler)
