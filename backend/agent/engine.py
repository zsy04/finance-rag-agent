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

from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware, ModelCallLimitMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL, AGENT_MODE
from agent.prompts import SYSTEM_PROMPT_MULTI, SYSTEM_PROMPT_TOOLS
from context.history_summarizer import build_history_summarizer
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


# ── LLM 单例（主/子 Agent 共用，避免各建一个 ChatOpenAI）──
_llm = None
_llm_lock = threading.Lock()


def get_llm():
    """获取 LLM 单例（线程安全）。主 Agent 与子 Agent 共用一个实例。"""
    global _llm
    if _llm is None:
        with _llm_lock:
            if _llm is None:
                _llm = ChatOpenAI(
                    model=DEEPSEEK_MODEL,
                    api_key=DEEPSEEK_API_KEY,
                    base_url="https://api.deepseek.com/v1",
                    temperature=0,
                )
    return _llm


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


def build_agent():
    """构建财税助手 Agent

    Returns:
        CompiledStateGraph — 支持 invoke / stream / astream_events
    """
    llm = get_llm()

    agent = create_agent(
        model=llm,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
        middleware=[
            ToolErrorMiddleware(on_error=_on_tool_error),    # 工具异常不崩溃
            ModelCallLimitMiddleware(run_limit=AGENT_MODEL_CALL_LIMIT),    # 控制成本
            build_history_summarizer(llm),    # 历史摘要：trigger=40K/keep=20 + 摘要标志→context 事件
        ],
    )
    return agent


# 全局单例（懒加载 + 双重检查锁，与 get_retriever() 模式一致）
_agent = None
_agent_lock = threading.Lock()


def get_agent():
    """获取 Agent 单例（线程安全）"""
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = build_agent()
    return _agent
