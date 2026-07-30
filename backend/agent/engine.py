"""Agent 大脑 — LangChain v1 create_agent

create_agent(model, tools, system_prompt, checkpointer, middleware)
返回 CompiledStateGraph，支持 invoke / stream / astream_events
"""

import json
from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware, ModelCallLimitMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from agent.prompts import SYSTEM_PROMPT
from tools import ALL_TOOLS


def _on_tool_error(exc: Exception, tool_call) -> str:
    """工具异常处理：转为错误消息返回给 LLM，而不是崩溃"""
    tool_name = getattr(tool_call, "name", "unknown") if tool_call else "unknown"
    return json.dumps(
        {"error": f"工具 {tool_name} 执行失败: {exc}", "answer": f"服务暂时不可用，请稍后重试。错误: {exc}"},
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
            ModelCallLimitMiddleware(run_limit=25),    # 控制成本，防止死循环
        ],
    )
    return agent


# 全局单例（懒加载）
_agent = None


def get_agent():
    """获取 Agent 单例"""
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent
