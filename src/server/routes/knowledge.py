"""Admin API: Knowledge base management."""
from fastapi import APIRouter, HTTPException, UploadFile

from ._deps import require_domain, scope_errors

router = APIRouter()


def _require_rag_domain():
    from src.domains.rag import get_rag_domain
    return require_domain(get_rag_domain, "知识库")


@router.get("/api/knowledge")
def list_knowledge():
    domain = _require_rag_domain()
    with scope_errors():
        docs = domain.list_documents()
    return {"items": docs, "public_error": domain.public_error}


@router.post("/api/knowledge/upload")
async def upload_knowledge(file: UploadFile, scope: str | None = None):
    """上传文档。?scope=public|private，不传用默认。"""
    domain = _require_rag_domain()
    data = await file.read()
    with scope_errors():
        try:
            result = domain.upload_document(file_data=data, filename=file.filename, scope=scope)
        except RuntimeError as e:          # 如没配 embedding、没连团队服务
            raise HTTPException(503, str(e))
    if not result:
        raise HTTPException(400, "文档解析失败")
    return result


@router.delete("/api/knowledge/{doc_id}")
def delete_knowledge(doc_id: str):
    domain = _require_rag_domain()
    with scope_errors():
        deleted = domain.delete_document(doc_id)
    if not deleted:
        raise HTTPException(404, "文档不存在")
    return {"ok": True}


@router.get("/api/knowledge/search")
def search_knowledge(q: str = "", top_k: int = 5):
    domain = _require_rag_domain()
    results = domain.search(q, top_k=top_k)
    return {"items": [r.to_dict() for r in results], "public_error": domain.public_error}
