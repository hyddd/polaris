from .tool import TodoTool, create_default

from src.core.events import event_bus


def _on_cleanup(**kwargs):
    import json
    import logging
    from src.core.config import config

    logger = logging.getLogger("polaris.tools.todos")
    path = config.resolve_path(config.get("storage.todos_file", "data/todos.json"))
    if not path.exists():
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    todos = data if isinstance(data, list) else []
    kept = [t for t in todos if not t.get("done")]
    archived = len(todos) - len(kept)

    if archived:
        from src.storage.atomic import _atomic_write
        _atomic_write(path, kept)
        logger.info(f"清理 {archived} 条已完成待办")


event_bus.subscribe("cleanup:now", _on_cleanup)
event_bus.subscribe("cleanup:cron", _on_cleanup)
