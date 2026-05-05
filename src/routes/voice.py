"""Admin API: TTS and voice file serving."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from src.core.config import config

router = APIRouter()


@router.post("/api/tts")
async def tts_endpoint(req: Request):
    body = await req.json()
    text = body.get("text", "")
    voice = body.get("voice")
    context = body.get("context")
    if not text:
        raise HTTPException(400, "text 不能为空")
    from src.domains.voice import get_voice_domain
    domain = get_voice_domain()
    if not domain:
        raise HTTPException(503, "语音服务未就绪")
    audio = domain.synthesize(text, voice=voice, context=context)
    if not audio:
        raise HTTPException(500, "TTS 生成失败，请检查 voice 配置")
    return Response(content=audio, media_type="audio/wav")


@router.get("/api/voice/{filename}")
def serve_voice(filename: str):
    """Serve generated voice files (audio elements cannot carry Bearer token)."""
    voice_dir = Path(config.resolve_path("data/voice"))
    filepath = voice_dir / filename
    if not filepath.exists():
        raise HTTPException(404, "音频文件不存在")
    return FileResponse(filepath, media_type="audio/wav")
