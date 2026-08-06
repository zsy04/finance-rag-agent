"""Agent 大脑 — LangChain v1 create_agent

create_agent(model, tools, system_prompt, checkpointer, middleware)
返回 CompiledStateGraph，支持 invoke / stream / astream_events

v1.5 multi-agent: ALL_TOOLS 按 AGENT_MODE 两形态组装
  - multi 形态：计税/社保 → tax_subagent / social_subagent
  - tools 形态：原 8 工具（回退/演示）
"""

import json
import logging
import threading
from contextvars import ContextVar
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware, ModelCallLimitMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL, AGENT_MODE
from agent.prompts import SYSTEM_PROMPT_MULTI, SYSTEM_PROMPT_TOOLS
from context.history_summarizer import build_history_summarizer
from services.provider_registry import provider_key, resolve_context_window
from tools import (
    get_user_context, search_knowledge,
    calculate_income_tax, calculate_business_income_tax,
    query_social_insurance,
    update_user_context, fill_tax_form, filing_guide,
    tax_subagent, social_subagent,
)

logger = logging.getLogger(__name__)

# 单轮对话中 LLM 最多调用次数（含工具调用 + 最终回答）。
# 25 次：典型个税计算需 3-5 次（get_user_context → calculate → update → 回答），
# 预留余量给多工具组合场景；超过则强制终止，防止死循环浪费 token。
AGENT_MODEL_CALL_LIMIT = 25


def _on_tool_error(exc: Exception, tool_call) -> str:
    """工具异常处理：转为错误消息返回给 LLM，而不是崩溃"""
    tool_name = getattr(tool_call, "name", "unknown") if tool_call else "unknown"
    # 异常详情只记日志，不泄露给 LLM（可能含文件路径等敏感信息）
    logger.warning("工具 %s 执行失败: %s", tool_name, exc, exc_info=True)
    return json.dumps(
        {
            "error": f"工具 {tool_name} 执行失败",
            "answer": "服务暂时不可用，请稍后重试。",
        },
        ensure_ascii=False,
    )


# ── LLM/Agent 缓存（主/子 Agent 共用 LLM 实例；按 provider 多实例，默认 DeepSeek 单例）──
# 模型切换器（2026-08-06）：provider = {base_url, api_key, model, context_window}，
# 由前端设置页配置 → localStorage → 请求携带 → 路由层 set_current_provider →
# get_llm/get_agent 按 provider 签名缓存（同配置复用，切换即时生效）。
_llm_cache: dict[str, ChatOpenAI] = {}
_llm_lock = threading.Lock()

# 当前请求的 provider（contextvar 传播给子 Agent / 摘要器等深层调用）
_current_provider: ContextVar[dict[str, Any] | None] = ContextVar(
    "current_provider", default=None
)


def set_current_provider(provider: dict[str, Any] | None) -> None:
    """设置当前请求的 provider（路由层调用）。None = 默认 DeepSeek"""
    _current_provider.set(provider)


def get_current_provider() -> dict[str, Any] | None:
    """读取当前请求的 provider（子 Agent 等深层调用使用）"""
    return _current_provider.get()


def get_llm(provider: dict[str, Any] | None = None) -> ChatOpenAI:
    """获取 LLM（按 provider 缓存，线程安全）。

    provider=None → 默认 DeepSeek（config.DEEPSEEK_MODEL + DEEPSEEK_API_KEY）。
    provider 含 base_url/api_key/model → 按签名缓存（OpenAI 兼容协议统一接入）。
    temperature 恒为 0：财税场景确定性优先（模型切换器需求 §4 定案）。
    """
    key = provider_key(provider)
    if key not in _llm_cache:
        with _llm_lock:
            if key not in _llm_cache:
                if not provider:
                    llm = ChatOpenAI(
                        model=DEEPSEEK_MODEL,
                        api_key=DEEPSEEK_API_KEY,
                        base_url="https://api.deepseek.com/v1",
                        temperature=0,
                    )
                else:
                    # BYOK：用户自带 key/base_url/模型名（OpenAI 兼容端点）
                    llm = ChatOpenAI(
                        model=provider["model"],
                        api_key=provider.get("api_key") or DEEPSEEK_API_KEY,
                        base_url=provider.get("base_url")
                        or "https://api.deepseek.com/v1",
                        temperature=0,
                    )
                _llm_cache[key] = llm
    return _llm_cache[key]


# ── ALL_TOOLS + SYSTEM_PROMPT 按 AGENT_MODE 组装 ──

if AGENT_MODE == "multi":
    ALL_TOOLS = [
        get_user_context,
        search_knowledge,
        tax_subagent,
        social_subagent,
        update_user_context,
        fill_tax_form,
        filing_guide,
    ]
    SYSTEM_PROMPT = SYSTEM_PROMPT_MULTI
else:  # tools 形态 = 原单 Agent（回退/演示）
    ALL_TOOLS = [
        get_user_context,
        search_knowledge,
        calculate_income_tax,
        calculate_business_income_tax,
        query_social_insurance,
        update_user_context,
        fill_tax_form,
        filing_guide,
    ]
    SYSTEM_PROMPT = SYSTEM_PROMPT_TOOLS


def build_agent(llm: ChatOpenAI | None = None, context_window: int | None = None):
    """构建财税助手 Agent

    Args:
        llm: LLM 实例（None → get_llm() 默认 DeepSeek）
        context_window: 模型上下文窗口（None → 摘要 trigger 用默认 40K）

    Returns:
        CompiledStateGraph — 支持 invoke / stream / astream_events
    """
    if llm is None:
        llm = get_llm()

    agent = create_agent(
        model=llm,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        # InMemorySaver 仅作"单轮会话缓冲"（持久化 §5.1）：
        # 路由层每请求传入独立内部 thread_id（{业务tid}#{uuid}），checkpoint 永不跨轮累积，
        # 历史上下文由 chat.py 从 SQLite 注入，流结束后写回——真正持久化在 SQLite。
        checkpointer=InMemorySaver(),
        middleware=[
            ToolErrorMiddleware(on_error=_on_tool_error),    # 工具异常不崩溃
            ModelCallLimitMiddleware(run_limit=AGENT_MODEL_CALL_LIMIT),    # 控制成本
            build_history_summarizer(llm, context_window=context_window),  # 窗口动态 trigger
        ],
    )
    return agent


# 全局 Agent 缓存：默认单例 + 自定义 provider 多实例（懒加载 + 双重检查锁）
_agent_cache: dict[str, Any] = {}
_agent_lock = threading.Lock()


def get_agent(provider: dict[str, Any] | None = None):
    """获取 Agent（按 provider 缓存，线程安全）。

    provider=None → 默认 DeepSeek Agent（与原 get_agent() 行为一致）；
    provider 提供 base_url/api_key/model → 对应 provider 的 Agent 实例。
    """
    key = provider_key(provider)
    if key not in _agent_cache:
        with _agent_lock:
            if key not in _agent_cache:
                llm = get_llm(provider)
                _agent_cache[key] = build_agent(
                    llm, context_window=resolve_context_window(provider)
                )
    return _agent_cache[key]
