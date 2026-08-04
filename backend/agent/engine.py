"""Agent 大脑 — LangChain v1 create_agent

create_agent(model, tools, system_prompt, checkpointer, middleware)
返回 CompiledStateGraph，支持 invoke / stream / astream_events
"""

import json
import logging
import threading

from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware, ModelCallLimitMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from agent.prompts import SYSTEM_PROMPT
from tools import ALL_TOOLS

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


def build_agent():
    """构建财税助手 Agent

    Returns:
        CompiledStateGraph — 支持 invoke / stream / astream_events
    """
    llm = ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com/v1",
        temperature=0,
    )

    agent = create_agent(
        model=llm,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
        middleware=[
            ToolErrorMiddleware(on_error=_on_tool_error),    # 工具异常不崩溃
            ModelCallLimitMiddleware(run_limit=AGENT_MODEL_CALL_LIMIT),    # 控制成本
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
