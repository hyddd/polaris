"""路由共享依赖。"""
from fastapi import HTTPException


def require_domain(getter, name: str):
    """获取 domain 实例，未就绪时抛 503。"""
    domain = getter()
    if not domain:
        raise HTTPException(503, f"{name}服务未就绪")
    return domain
