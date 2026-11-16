"""多路检索结果合并。"""


def rrf_merge(result_lists: list[list], key, top_k: int, k: int = 60) -> list:
    """倒数排名融合：多路检索结果按名次合并，不需要把不同来源的分数换算成同一尺度。

    私人结果来自本机 Chroma、公共结果来自 team 服务，两边分数不保证可比，所以按名次合并。
    返回 [(item, rrf_score)]，按分数从高到低。
    """
    scores: dict = {}
    items: dict = {}
    for results in result_lists:
        for rank, item in enumerate(results):
            kk = key(item)
            scores[kk] = scores.get(kk, 0.0) + 1.0 / (k + rank + 1)
            items.setdefault(kk, item)
    ordered = sorted(scores, key=lambda kk: scores[kk], reverse=True)[:top_k]
    return [(items[kk], scores[kk]) for kk in ordered]
