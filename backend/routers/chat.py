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
from agent.engine import get_agent, set_current_provider
from services.provider_registry import PROVIDER_TEMPLATES
from storage.sqlite_store import get_store
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

class ProviderConfig(BaseModel):
    """用户自配模型供应商（模型切换器 2026-08-06）。

    前端设置页填写 → localStorage → 随请求携带；后端转发（保留 Agent 全链路）。
    model 必填；base_url/api_key 缺省回退默认 DeepSeek。
    """
    base_url: str | None = Field(default=None, description="OpenAI 兼容端点")
    api_key: str | None = Field(default=None, description="用户自带 API Key")
    model: str = Field(..., min_length=1, description="模型名（如 deepseek-v4-flash / qwen-plus）")
    context_window: int | None = Field(default=None, description="上下文窗口（触发摘要动态适配）")


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息（非空）")
    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="会话 ID，用于多轮对话记忆",
    )
    provider: ProviderConfig | None = Field(default=None, description="模型供应商配置（缺省=默认 DeepSeek）")


def _sse(event_type: str, data: dict) -> str:
    """格式化 SSE 事件"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _agent_stream(message: str, thread_id: str, provider: dict | None = None):
    """Agent astream_events → 8 种 SSE 事件映射 + 历史注入/写回（持久化 §5.1）

    模型切换器：provider 非空时用自定义模型构建 Agent（get_agent(provider)），
    否则默认 DeepSeek。子 Agent 通过 contextvar 感知同一 provider。

    持久化机制：
      - 内部 thread_id：每请求独立（{业务tid}#{uuid}），InMemorySaver checkpoint
        永不跨轮累积 → 注入的历史 + 本轮消息即"全部上下文"，摘要中间件调用内压缩
      - 流结束后写回 user + assistant（完整 Message JSON），前端刷新后回显
    """
    set_current_provider(provider)
    agent = get_agent(provider)
    store = get_store()

    # 1. 历史注入：SQLite 读完整历史，只取 role+content 正文（附件不喂 LLM）
    history = store.get_history(thread_id)
    seed_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("content")
    ]
    seed_messages.append({"role": "user", "content": message})

    # 每请求独立内部 thread_id：防 InMemorySaver 双份累积（持久化由 SQLite 承担）
    run_thread_id = f"{thread_id}#{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": run_thread_id}}

    # 2. 收集本轮 AI 回复附件（写回用，与前端 Message 结构对齐）
    ai_parts: list[str] = []
    last_result_card = None
    ai_sources: list = []
    ai_disclaimer = None
    ai_context_notice = None

    # 历史摘要提示：若上一轮发生过摘要（middleware 置标志），先发 context 事件提示用户。
    # 时序说明：本轮触发的摘要会在下一轮流开始时补发（语义可接受，设计文档 §3.6）。
    from context.history_summarizer import pop_summarized_flag

    if pop_summarized_flag(thread_id):
        ai_context_notice = "较早的对话已归档为摘要，您的城市、工资、扣除项等关键信息已保留"
        yield _sse("context", {
            "type": "history_archived",
            "message": ai_context_notice,
        })

    yield _sse("thinking", {"message": "正在为您处理……"})

    try:
        async for event in agent.astream_events(
            {"messages": seed_messages},
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
                    ai_parts.append(chunk.content)
                    yield _sse("step", {"content": chunk.content})

            # 工具结束 → 解包结构化返回 → result / source / disclaimer
            elif kind == "on_tool_end":
                output = event["data"]["output"]
                raw = output.content if hasattr(output, "content") else str(output)
                try:
                    parsed = json.loads(raw)

                    # 1. result（结果卡片）— 先发，前端先插入卡片
                    if parsed.get("result_card"):
                        last_result_card = parsed["result_card"]
                        yield _sse("result", last_result_card)

                    # 2. source ×N（来源链接）— 再发，附在卡片下方
                    if parsed.get("sources"):
                        for src in parsed["sources"]:
                            ai_sources.append(src)
                            yield _sse("source", src)

                    # 3. disclaimer（免责声明）— 最后发
                    if parsed.get("disclaimer"):
                        ai_disclaimer = parsed["disclaimer"]
                        yield _sse("disclaimer", {"text": ai_disclaimer})

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
        return  # 异常不写回（用户重试时自然落库，避免双份）
    except Exception:
        # 兜底：未预期的编程错误（AttributeError/KeyError 等）应正常抛出，
        # 但 SSE 流需先关闭，故发 error 事件后重新 raise 以便上层日志捕获
        logger.exception("Agent 流式处理未预期异常 (thread_id=%s)", thread_id)
        yield _sse("error", {"content": "服务内部错误，请稍后重试"})
        return

    yield _sse("done", {})

    # 3. 写回本轮消息（完整 Message JSON，前端回显零转换）
    store.append_message(
        thread_id, "user", message,
        {"id": str(uuid.uuid4()), "role": "user", "content": message},
    )
    ai_content = "".join(ai_parts)
    if ai_content or last_result_card or ai_sources or ai_disclaimer or ai_context_notice:
        ai_msg = {"id": str(uuid.uuid4()), "role": "assistant", "content": ai_content}
        if last_result_card:
            ai_msg["resultCard"] = last_result_card
        if ai_sources:
            ai_msg["sources"] = ai_sources
        if ai_disclaimer:
            ai_msg["disclaimer"] = ai_disclaimer
        if ai_context_notice:
            ai_msg["contextNotice"] = ai_context_notice
        store.append_message(thread_id, "assistant", ai_content, ai_msg)


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

    # 模型切换器：请求携带 provider（base_url/api_key/model）→ 后端转发调用
    provider = req.provider.model_dump(exclude_none=True) if req.provider else None

    return StreamingResponse(
        _agent_stream(req.message, req.thread_id, provider),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/api/models")
async def list_models():
    """模型供应商模板列表 — 前端设置页下拉数据源（不含任何 API Key）"""
    return {"templates": PROVIDER_TEMPLATES}


class ProviderTestRequest(BaseModel):
    """测试连接：验证用户填的 base_url + api_key + model 可用"""
    base_url: str = Field(..., description="OpenAI 兼容端点")
    api_key: str = Field(..., min_length=1, description="API Key")
    model: str = Field(..., min_length=1, description="模型名")


@router.post("/api/models/test")
async def test_provider(req: ProviderTestRequest):
    """测试模型连接 — 发一次最小 chat 请求验证 key/base_url/model 有效。

    前端设置页「测试」按钮调用；仅用于验证，不落库、不改任何状态。
    """
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=req.model,
        api_key=req.api_key,
        base_url=req.base_url,
        temperature=0,
        max_retries=0,
        timeout=15,
    )
    try:
        resp = await asyncio.to_thread(llm.invoke, "你好，请回复：连接成功")
        content = (resp.content or "").strip()[:50]
        return {"ok": True, "model": req.model, "reply": content}
    except Exception as exc:  # noqa: BLE001 — 测试接口需向前端返回可读错误
        logger.info("模型测试连接失败: %s", exc)
        return {"ok": False, "model": req.model, "error": str(exc)[:200]}


@router.get("/api/chat/threads")
async def chat_threads():
    """会话列表 — 侧边栏多会话（新建/删除/切换），按更新时间倒序"""
    return {"threads": get_store().list_threads()}


@router.get("/api/chat/history")
async def chat_history(thread_id: str):
    """历史回显 — 返回该会话完整消息列表（完整 Message JSON，时间升序）

    前端挂载时调用，setMessages 直接渲染；配合 localStorage 固定 thread_id 实现
    "刷新/重开浏览器后历史回显 + Agent 接着聊"（持久化 §5.1）。
    """
    messages = get_store().get_history(thread_id)
    return {"thread_id": thread_id, "messages": messages}


@router.delete("/api/chat/history")
async def clear_chat_history(thread_id: str):
    """清空指定会话（消息 + 画像 + 会话记录）— 前端「新会话」按钮调用

    换人演示场景：删除后前端换新 thread_id，Agent 从零开始（画像/历史全清）。
    """
    get_store().delete_thread(thread_id)
    return {"ok": True, "thread_id": thread_id}


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
