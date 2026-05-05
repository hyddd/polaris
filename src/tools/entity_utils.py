def find_by_id_or_title(
    items: list,
    id_key: str,
    id_value: str,
    title_key: str = "title",
    title_value: str = "",
) -> dict | None:
    """按 ID 精确匹配，失败后按标题模糊匹配（大小写不敏感）。返回匹配项或 None。

    Args:
        items: 要搜索的实体列表。
        id_key: ID 字段名，如 "id"。
        id_value: 要匹配的 ID 值。若为空则跳过 ID 匹配。
        title_key: 标题字段名，默认 "title"。
        title_value: 要匹配的标题值。若为空则跳过标题匹配。

    Returns:
        匹配到的实体 dict，或 None。
    """
    if not items:
        return None

    # ID 精确匹配
    if id_value:
        for item in items:
            if item.get(id_key) == id_value:
                return item
        # 后缀匹配：LLM 可能省略前缀（如 862ffcd9 匹配 todo-862ffcd9）
        for item in items:
            if item.get(id_key, "").endswith(id_value):
                return item
        # 包含匹配：最后兜底
        for item in items:
            if id_value in item.get(id_key, ""):
                return item

    # 标题模糊匹配（大小写不敏感）
    if title_value:
        for item in items:
            if title_value.lower() in item.get(title_key, "").lower():
                return item

    return None
