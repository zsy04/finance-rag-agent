"""
聊天 SSE 路由
============
新版 POST /api/chat — Agent 通路（create_agent + astream_events + 8 种 SSE 事件）
旧版 POST /chat      — Legacy 直连通路（纯 RAG + LLM，快速路径）
旧版 POST /chat/with-search — Legacy 带来源的直连通路
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rag.retriever import get_retriever
from services.generator import stream_answer
from agent.engine import get_agent
from tools.user_context import set_current_thread_id

logger = logging.getLogger(__name__)

# ── 路由 ──────────────────────────────────────────────

router = APIRouter(tags=["chat"])

# SSE 流式响应通用头：禁止代理缓冲，保证 token 实时下发
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


# ── 新版 Agent 通路 ───────────────────────────────────

class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息（非空）")
    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="会话 ID，用于多轮对话记忆",
    )


def _sse(event_type: str, data: dict) -> str:
    """格式化 SSE 事件"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _agent_stream(message: str, thread_id: str):
    """Agent astream_events → 8 种 SSE 事件映射"""
    agent = get_agent()
    config = {"configurable": {"thread_id": thread_id}}

    # 历史摘要提示：若上一轮发生过摘要（middleware 置标志），先发 context 事件提示用户。
    # 时序说明：本轮触发的摘要会在下一轮流开始时补发（语义可接受，设计文档 §3.6）。
    from context.history_summarizer import pop_summarized_flag

    if pop_summarized_flag(thread_id):
        yield _sse("context", {
            "type": "history_archived",
            "message": "较早的对话已归档为摘要，您的城市、工资、扣除项等关键信息已保留",
        })

    yield _sse("thinking", {"message": "正在为您处理……"})

    try:
        async for event in agent.astream_events(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            version="v2",
        ):
            kind = event["event"]

            # 工具开始 → thinking
            if kind == "on_tool_start":
                yield _sse("thinking", {"tool": event.get("name", "")})

            # LLM 逐 token → step
            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield _sse("step", {"content": chunk.content})

            # 工具结束 → 解包结构化返回 → result / source / disclaimer
            elif kind == "on_tool_end":
                output = event["data"]["output"]
                raw = output.content if hasattr(output, "content") else str(output)
                try:
                    parsed = json.loads(raw)

                    # 1. result（结果卡片）— 先发，前端先插入卡片
                    if parsed.get("result_card"):
                        yield _sse("result", parsed["result_card"])

                    # 2. source ×N（来源链接）— 再发，附在卡片下方
                    if parsed.get("sources"):
                        for src in parsed["sources"]:
                            yield _sse("source", src)

                    # 3. disclaimer（免责声明）— 最后发
                    if parsed.get("disclaimer"):
                        yield _sse("disclaimer", {"text": parsed["disclaimer"]})

                except (json.JSONDecodeError, TypeError):
                    # 非 JSON 返回（如纯文本错误消息），记录日志便于排查
                    logger.debug("工具返回非 JSON，跳过解包: %s", raw[:200])

            # 工具错误 → thinking（非致命，Agent 会自行处理并继续）
            elif kind == "on_tool_error":
                err_msg = str(event.get("data", {}).get("error", "工具调用失败"))
                yield _sse("thinking", {"tool_error": err_msg})

    except (ConnectionError, asyncio.TimeoutError, RuntimeError) as e:
        # 网络/超时/运行时错误 → 对用户友好提示，内部记完整 traceback
        logger.exception("Agent 流式处理异常 (thread_id=%s)", thread_id)
        yield _sse("error", {"content": "服务内部错误，请稍后重试"})
    except Exception:
        # 兜底：未预期的编程错误（AttributeError/KeyError 等）应正常抛出，
        # 但 SSE 流需先关闭，故发 error 事件后重新 raise 以便上层日志捕获
        logger.exception("Agent 流式处理未预期异常 (thread_id=%s)", thread_id)
        yield _sse("error", {"content": "服务内部错误，请稍后重试"})

    yield _sse("done", {})


@router.post("/api/chat")
async def agent_chat(req: AgentChatRequest):
    """
    Agent 通路 — 工具自动调度 + 多轮记忆 + SSE 流式输出

    SSE 事件类型:
      event: thinking    → Agent 开始处理 / 工具调用中
      event: step        → LLM 逐 token 输出
      event: result      → 计算结果卡片（tax_result / social_result）
      event: source      → 法规来源链接
      event: disclaimer  → AI 免责声明
      event: error       → 处理失败
      event: done        → 回复完成
    """
    # 设置 contextvar → @tool 内部可通过 _current_thread_id.get() 读取
    set_current_thread_id(req.thread_id)

    return StreamingResponse(
        _agent_stream(req.message, req.thread_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ── Legacy 直连通路（保留，Phase 6 决定是否移除）──────

class LegacyChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="用户问题（非空）")


@router.post("/chat")
async def legacy_chat(req: LegacyChatRequest):
    """
    Legacy 直连通路 — 纯 RAG + LLM，无 Agent 调度
    快速路径，适合延迟敏感的纯问答场景
    """
    retriever = get_retriever()
    results = await run_in_threadpool(retriever.retrieve, req.query, top_k=5)

    return StreamingResponse(
        stream_answer(req.query, results),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/chat/with-search")
async def legacy_chat_with_search(req: LegacyChatRequest):
    """Legacy 带来源的直连通路"""
    retriever = get_retriever()
    results = await run_in_threadpool(retriever.retrieve, req.query, top_k=5)

    async def stream_with_sources():
        sources = [
            {"doc_title": r["doc_title"], "source_file": r["source_file"],
             "relevance_tier": r["relevance_tier"], "final_score": r["final_score"]}
            for r in results
        ]
        yield f"data: {json.dumps({'type': 'sources', 'data': sources}, ensure_ascii=False)}\n\n"
        async for chunk in stream_answer(req.query, results):
            yield chunk

    return StreamingResponse(
        stream_with_sources(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
