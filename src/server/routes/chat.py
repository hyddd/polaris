"""Chat endpoints — non-streaming and SSE streaming."""
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_core.messages import AIMessage

from src.agent.graph import get_agent
from src.agent.state import AgentState
from src.session.manager import get_session_manager, SessionManager
from src.core.infra import set_context as _set_ctx, get_session_lock
from src.message import process_message
from src.message.models import Attachment
from src.message.router import _build_message

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    channel: str = ""
    retry_message_id: str | None = None  # 重试指定消息
    edit_message_id: str | None = None   # 编辑指定消息
    edit_content: str | None = None      # 编辑后的内容
    attachments: list[dict] | None = None  # 附件列表


class ChatResponse(BaseModel):
    session_id: str
    response: str
    tool_calls: list[dict] = []


def _get_active_session(session_id: str | None, session_mgr: SessionManager, channel: str = "default"):
    """Resolve session: use given ID, switch if needed, or use active."""
    if session_id:
        result = session_mgr.switch(session_id, channel)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    session, switched = session_mgr.resolve_session(channel)
    return session


def _retry_message(session_id: str, message_id: str, session_mgr: SessionManager, channel: str = "default"):
    """重试指定消息：找到原消息，重新执行"""
    session = session_mgr.get(session_id) if session_id else session_mgr.active_session(channel)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    original = session.get_message(message_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"消息不存在: {message_id}")

    # 获取原消息内容
    content = original.content if hasattr(original, 'content') else str(original)
    return content


def _edit_message(session_id: str, message_id: str, new_content: str, session_mgr: SessionManager, channel: str = "default"):
    """编辑消息并返回新内容"""
    session = session_mgr.get(session_id) if session_id else session_mgr.active_session(channel)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 更新消息内容
    if not session.update_message(message_id, new_content):
        raise HTTPException(status_code=404, detail=f"消息不存在: {message_id}")

    return new_content


def _parse_attachments(raw: list[dict] | None) -> list[Attachment] | None:
    """将请求中的 dict 附件转换为 Attachment 对象。"""
    if not raw:
        return None
    result = []
    for item in raw:
        try:
            result.append(Attachment(
                type=item.get("type", "file"),
                data=item.get("data", ""),
                mime_type=item.get("mime_type", ""),
                filename=item.get("filename", ""),
            ))
        except Exception:
            continue
    return result or None


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_mgr = get_session_manager()
    channel = req.channel or "default"
    session = _get_active_session(req.session_id, session_mgr, channel)
    attachments = _parse_attachments(req.attachments)

    # 重试逻辑
    if req.retry_message_id:
        original_content = _retry_message(session.session_id, req.retry_message_id, session_mgr, channel)
        results = await process_message(original_content, session_mgr, channel, attachments)
        response_text, tool_calls = results[-1]
        return ChatResponse(
            session_id=session.session_id,
            response=response_text,
            tool_calls=tool_calls,
        )

    # 编辑逻辑
    if req.edit_message_id and req.edit_content:
        new_content = _edit_message(session.session_id, req.edit_message_id, req.edit_content, session_mgr, channel)
        results = await process_message(new_content, session_mgr, channel, attachments)
        response_text, tool_calls = results[-1]
        return ChatResponse(
            session_id=session.session_id,
            response=response_text,
            tool_calls=tool_calls,
        )

    # 正常聊天
    results = await process_message(req.message, session_mgr, channel, attachments)
    response_text, tool_calls = results[-1]
    return ChatResponse(
        session_id=session.session_id,
        response=response_text,
        tool_calls=tool_calls,
    )


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """SSE streaming — node-level progress via LangGraph astream.

    Yields events as each graph node completes:
      event: node — which node just ran (command, agent, tools)
      event: tool_call — LLM decided to call a tool
      event: message — final response text
      event: done — stream complete
    """
    session_mgr = get_session_manager()
    channel = req.channel or "default"
    session = _get_active_session(req.session_id, session_mgr, channel)
    attachments = _parse_attachments(req.attachments)

    # Determine the message content (retry/edit/normal)
    message_content = req.message

    # 重试逻辑
    if req.retry_message_id:
        message_content = _retry_message(session.session_id, req.retry_message_id, session_mgr, channel)

    # 编辑逻辑
    elif req.edit_message_id and req.edit_content:
        message_content = _edit_message(session.session_id, req.edit_message_id, req.edit_content, session_mgr, channel)

    # System commands: wrap in SSE
    if message_content.strip().startswith("/"):
        results = await process_message(message_content, session_mgr, channel, attachments)

        async def cmd_gen() -> AsyncGenerator[str, None]:
            for response_text, _ in results:
                yield f"event: message\ndata: {json.dumps({'content': response_text}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'session_id': session.session_id}, ensure_ascii=False)}\n\n"
        return StreamingResponse(cmd_gen(), media_type="text/event-stream")

    # Normal message: streaming agent pipeline
    agent = get_agent()
    memory = session.memory
    old_messages = memory.get_messages()

    # Create HumanMessage with ID for retry/edit support
    human_msg = _build_message(message_content, attachments)
    memory.add_message(human_msg)
    human_msg_id = memory.get_message_id(human_msg)

    state = AgentState(
        messages=old_messages + [human_msg],
        intent="",
        user_profile=memory.get_profile(),
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=session.pending_action,
        streaming=True,
        channel=channel,
    )

    # Acquire per-session lock before streaming starts
    session_lock = get_session_lock(channel, session.session_id)

    async def generate() -> AsyncGenerator[str, None]:
        full_response = ""
        new_pending_action = None
        final_messages = None

        # Non-blocking try_lock: if another request is already processing
        # for this session, return an error instead of blocking the SSE stream.
        if not session_lock.acquire(blocking=False):
            yield f"event: error\ndata: {json.dumps({'error': '该会话正在处理中，请稍后再试'}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'session_id': session.session_id}, ensure_ascii=False)}\n\n"
            return
        try:
            # 在锁内设置 context，防止并发覆盖
            user_id = channel.split(":", 1)[-1] if ":" in channel else ""
            _set_ctx(channel=channel, session_id=session.session_id, user_id=user_id)
            async for event in agent.astream_events(state, version="v2"):
                kind = event.get("event", "")

                # 客户端断连时主动停止，避免锁一直不释放
                if await request.is_disconnected():
                    break

                # Token-level streaming from LLM
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk", None)
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        full_response += chunk.content
                        yield f"data: {json.dumps({'token': chunk.content}, ensure_ascii=False)}\n\n"

                # Tool call starting
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})
                    call_id = event.get("run_id", "")
                    yield f"event: tool_call\ndata: {json.dumps({'tool': tool_name, 'args': tool_input, 'call_id': call_id}, ensure_ascii=False)}\n\n"

                # Tool call finished — send result for thinking chain display
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    tool_output = event.get("data", {}).get("output", "")
                    call_id = event.get("run_id", "")
                    # ToolMessage output — extract string content
                    if hasattr(tool_output, "content"):
                        tool_output = tool_output.content
                    yield f"event: tool_result\ndata: {json.dumps({'tool': tool_name, 'result': str(tool_output), 'call_id': call_id}, ensure_ascii=False)}\n\n"

                # Track pending_action changes and capture final messages
                elif kind == "on_chain_end":
                    node_name = event.get("name", "")
                    output = event.get("data", {}).get("output", {})
                    if node_name in ("tool", "tools", "command"):
                        if isinstance(output, dict) and "pending_action" in output:
                            new_pending_action = output["pending_action"]
                    # Capture final graph state with full message history
                    if node_name in ("agent", "__end__") and isinstance(output, dict):
                        msgs = output.get("messages")
                        if msgs:
                            final_messages = msgs

            yield f"event: done\ndata: {json.dumps({'session_id': session.session_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'traceback': tb[-300:]}, ensure_ascii=False)}\n\n"

        finally:
            session_lock.release()

        if full_response:
            import logging as _log
            _log.getLogger("polaris.agent").info(
                f"[msg] old={len(old_messages)} final={len(final_messages) if final_messages else 'None'}"
            )
            if final_messages:
                # final_messages is the full graph state (old + human + agent output)
                memory.set_messages(list(final_messages))
            else:
                memory.set_messages(old_messages + [
                    human_msg,
                    AIMessage(content=full_response),
                ])
            session_mgr.record_message(message_content, full_response, channel)

        # Save pending_action to session for next invocation
        session.pending_action = new_pending_action

    return StreamingResponse(generate(), media_type="text/event-stream")
