"""Chat endpoints — non-streaming and SSE streaming."""
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agent.graph import get_agent
from src.agent.state import AgentState
from src.session.manager import get_session_manager, SessionManager
from src.core.infra import set_context as _set_ctx, get_session_lock
from src.message import process_message
from src.message.models import Attachment
from src.message.router import _build_message
from src.message.turn import TurnRecorder

logger = logging.getLogger("polaris.agent")

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
    session_lock = get_session_lock(session.session_id)

    async def generate() -> AsyncGenerator[str, None]:
        # Non-blocking try_lock: if another request (any channel) is already processing
        # this session, return an error instead of blocking the SSE stream.
        # 拿不到锁时什么都不写：以前用户消息在抢锁之前就进了历史，报忙后残留下来
        if not session_lock.acquire(blocking=False):
            yield _sse("error", {"error": "该会话正在处理中，请稍后再试"})
            yield _sse("done", {"session_id": session.session_id})
            return

        turn = None
        error_payload = None
        try:
            # 在锁内设置 context，防止并发覆盖
            user_id = channel.split(":", 1)[-1] if ":" in channel else ""
            _set_ctx(channel=channel, session_id=session.session_id, user_id=user_id)

            # 读历史、写用户消息都放在锁内，避免读到别的入口正在改写的历史
            old_messages = memory.get_messages()
            human_msg = _build_message(message_content, attachments)
            memory.add_message(human_msg)
            turn_start = len(old_messages) + 1
            turn = TurnRecorder(old_messages, human_msg)

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
                session_id=session.session_id,
            )

            try:
                async for event in agent.astream_events(state, version="v2"):
                    # 客户端断连时主动停止，避免锁一直不释放
                    if await request.is_disconnected():
                        break

                    kind = event.get("event", "")
                    token = turn.feed(event)

                    # Token-level streaming from LLM
                    if token:
                        yield _sse(None, {"token": token})

                    # Tool call starting
                    elif kind == "on_tool_start":
                        tool_name = event.get("name", "unknown")
                        tool_input = event.get("data", {}).get("input", {})
                        call_id = event.get("run_id", "")
                        yield _sse("tool_call", {"tool": tool_name, "args": tool_input, "call_id": call_id})

                    # Tool call finished — send result for thinking chain display
                    elif kind == "on_tool_end":
                        tool_name = event.get("name", "unknown")
                        tool_output = event.get("data", {}).get("output", "")
                        call_id = event.get("run_id", "")
                        # ToolMessage output — extract string content
                        if hasattr(tool_output, "content"):
                            tool_output = tool_output.content
                        yield _sse("tool_result", {"tool": tool_name, "result": str(tool_output), "call_id": call_id})

            except Exception as e:
                import traceback
                turn.error = e
                error_payload = {"error": str(e), "traceback": traceback.format_exc()[-300:]}

            finally:
                # 正常结束、出错、客户端断开（CancelledError / GeneratorExit）都走这里，先落盘。
                # 断开时 Starlette 会直接取消生成器，以前写在 finally 之后的保存代码根本执行不到。
                _commit_stream_turn(session_mgr, session, turn, turn_start, message_content, channel)

        finally:
            session_lock.release()

        # 落盘之后才发终态：收到 done 即表示本轮已保存
        if error_payload:
            yield _sse("error", error_payload)
        elif turn.notice:
            # 确认/取消的结果不是模型 token，流里没有，要单独发
            yield _sse("message", {"content": turn.notice})
        yield _sse("done", {"session_id": session.session_id})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _sse(event: str | None, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n" if event else f"data: {data}\n\n"


def _commit_stream_turn(session_mgr: SessionManager, session, turn: TurnRecorder,
                        turn_start: int, message_content: str, channel: str) -> None:
    """把一轮流式对话的结果写回会话并落盘。规则见 src/message/turn.py。"""
    session.pending_action = turn.pending_action()
    session.memory.replace_keeping_appended(turn_start, turn.history())
    if turn.completed and not turn.notice:
        # record_message 内部会落盘
        session_mgr.record_message(message_content, turn.reply_text, channel,
                                   session_id=session.session_id)
    else:
        session_mgr.save_session(session.session_id)
    if not turn.completed:
        logger.warning(
            f"[chat] 会话 {session.session_id} 本轮未正常结束"
            f"（{'出错: ' + str(turn.error) if turn.error else '客户端中断'}），"
            f"已写回 {len(turn.deltas)} 条中间消息"
        )
