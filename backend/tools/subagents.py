"""双子 Agent（计税 + 社保）— 包装成 tool 挂回主 Agent

v1.5 设计：两个子 Agent 统一放 subagents.py，模块级懒加载单例
（与 engine.get_agent() 同模式：threading.Lock 双检，构建一次复用）。
子 Agent 无 checkpointer、无历史，每次调用独立；
画像通过 get_user_context 读取（contextvar 传 thread_id，同进程传播）。
返回遵循 tools/base.py JSON 五字段协议 → SSE 解包零改动。

v1.4 降级：子 Agent 未计算出 result_card 时，复用 AIMessage.tool_calls 参数直调原工具。
v1.5 绕过检测：answer 含税额数字但无 result_card → 强制走引擎重算，LLM 数字作废。

⚠️ 同步兼容：tax_subagent / social_subagent 包装为 sync @tool（def，非 async def）。
  内部用 asyncio.run() 跑子 Agent —— 因为 langgraph-prebuilt 1.1.0 的 ToolNode
  在 graph.invoke()（sync）路径永远走 _execute_tool_sync → tool.invoke()，
  而 async StructuredTool 的 sync invoke() 会抛 NotImplementedError。
  sync @tool + 内部 asyncio.run() 在 sync/async 两条路径上都安全：
  - sync invoke() 路径：无事件循环 → asyncio.run() 建新循环 ✅
  - async ainvoke() 路径：ToolNode 走 _arun_one → ainvoke →
    StructuredTool.ainvoke() 检测 coroutine=None → run_in_executor(self.invoke)
    → 线程池 → 该线程无事件循环 → asyncio.run() 建新循环 ✅
"""

import asyncio
import json
import logging
import re
import threading
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ToolRetryMiddleware, ModelCallLimitMiddleware
from langchain_core.tools import tool

from agent.prompts import TAX_SUBAGENT_PROMPT, SOCIAL_SUBAGENT_PROMPT
from tools import get_user_context, update_user_context
from tools.calculate_income_tax import calculate_income_tax, calculate_business_income_tax
from tools.query_social_insurance import query_social_insurance
from tools.base import AI_DISCLAIMER, tag_tool_result

logger = logging.getLogger(__name__)

# ── 计算工具名集合（供降级/绕过检测使用）──
CALC_TOOL_NAMES = {"calculate_income_tax", "calculate_business_income_tax"}


def _on_tool_error(exc: Exception, tool_call) -> str:
    """子 Agent 工具异常处理：转为错误消息返回给 LLM，而不崩溃"""
    tool_name = getattr(tool_call, "name", "unknown") if tool_call else "unknown"
    logger.warning("子 Agent 工具 %s 执行失败: %s", tool_name, exc, exc_info=True)
    return json.dumps(
        {
            "error": f"工具 {tool_name} 执行失败",
            "answer": "服务暂时不可用，请稍后重试。",
        },
        ensure_ascii=False,
    )


def _build_subagent(llm, system_prompt, tools):
    """构建子 Agent（无 checkpointer = 无状态、无历史）"""
    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[
            ToolRetryMiddleware(max_retries=0, on_failure='continue'),
            ModelCallLimitMiddleware(run_limit=8),   # 子 Agent 防死循环
        ],
        # 不传 checkpointer → 无状态，每次独立；全局单例共享安全
    )


# ── 子 Agent 缓存：按 LLM 实例缓存（模型切换器 2026-08-06）──
# LLM 本身被 engine.get_llm 按 provider 缓存（同 provider 同实例），
# 这里用 id(llm) 作 key → provider 变化时自动重建子 Agent，同 provider 复用。
_tax_subagents: dict[int, Any] = {}
_social_subagents: dict[int, Any] = {}
_lock = threading.Lock()


def get_tax_subagent(llm):
    """获取计税子 Agent（按 LLM 实例缓存，线程安全）"""
    key = id(llm)
    if key not in _tax_subagents:
        with _lock:
            if key not in _tax_subagents:
                _tax_subagents[key] = _build_subagent(
                    llm, TAX_SUBAGENT_PROMPT,
                    [get_user_context, update_user_context,
                     calculate_income_tax, calculate_business_income_tax])
    return _tax_subagents[key]


def get_social_subagent(llm):
    """获取社保子 Agent（按 LLM 实例缓存，线程安全）"""
    key = id(llm)
    if key not in _social_subagents:
        with _lock:
            if key not in _social_subagents:
                _social_subagents[key] = _build_subagent(
                    llm, SOCIAL_SUBAGENT_PROMPT,
                    [get_user_context, update_user_context, query_social_insurance])
    return _social_subagents[key]


def _extract_fields(messages) -> tuple:
    """遍历子 Agent 消息链，确定性提取最后一个非空 result_card / sources / answer（不靠 LLM 复述）

    Returns:
        (answer: str, result_card: dict|None, sources: list|None)
    """
    answer = ""
    result_card = None
    sources = None
    for msg in messages:
        content = getattr(msg, "content", "")
        if isinstance(content, str) and content.strip().startswith("{"):
            try:
                parsed = json.loads(content)
                if parsed.get("result_card"):
                    result_card = parsed["result_card"]
                if parsed.get("sources"):
                    sources = parsed["sources"]
            except json.JSONDecodeError:
                pass
        if getattr(msg, "type", "") == "ai" and content:
            answer = content  # 子 Agent 最终回答（取最后一个 AI 消息）
    return answer, result_card, sources


def _fallback_reuse_args(messages, calc_tool_names) -> tuple:
    """降级（v1.4）：从子 Agent 消息链复用 LLM 已生成的 calculate 参数直调原工具。

    触发条件：子 Agent 消息链中无 result_card，但有 AIMessage.tool_calls（LLM 已生成参数）。

    Returns:
        (answer: str, result_card: dict|None, sources: list|None, used: bool)
    """
    # ① 找最后一个 calculate 工具调用（LLM 已生成参数）
    for msg in reversed(messages):
        tool_calls = getattr(msg, "tool_calls", []) or []
        for tc in tool_calls:
            tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            if tc_name in calc_tool_names:
                args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                # ② 直调原工具（确定性引擎），参数 LLM 已生成
                fn = calculate_business_income_tax if tc_name == "calculate_business_income_tax" else calculate_income_tax
                try:
                    raw = fn.invoke(args) if hasattr(fn, "invoke") else fn(**args)
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                    logger.info("降级成功：复用 %s 参数直调原工具，取得 result_card", tc_name)
                    return parsed.get("answer", ""), parsed.get("result_card"), parsed.get("sources"), True
                except Exception as exc:
                    logger.warning("降级执行失败（%s）: %s", tc_name, exc)
                    break  # 参数不全 → 落到③
    return "", None, None, False  # ③ 未找到/失败


def _contains_tax_amount(text: str) -> bool:
    """检测文本中是否出现疑似税额数字（"税 xxx 元"或"xxx 元"模式）

    v1.5 绕过检测：用于判断 LLM 是否"心算"绕过了确定性引擎。
    """
    if not text:
        return False
    return bool(re.search(r"(税|应纳税额|个税|交税|纳税)[^\d]{0,6}(\d[\d,，.]*)\s*(元|块)", text))


def _forced_recalc(query: str, messages) -> tuple:
    """强制重算（v1.5）：优先复用 tool_calls 参数，否则返回错误让主 Agent 反问。

    绝不用 LLM 心算数字——_contains_tax_amount 已判定 answer 含税额数字但无 result_card。
    """
    answer, result_card, sources, used = _fallback_reuse_args(messages, CALC_TOOL_NAMES)
    if used:
        logger.info("强制重算：复用 tool_calls 参数成功")
        return answer, result_card, sources
    logger.warning("强制重算：无 tool_calls 可复用，返回错误让主 Agent 反问")
    return "计算所需信息不完整，请补充以下信息后重新计算。", None, None


# ── 核心异步逻辑（内部函数，不直接暴露为 @tool）────

async def _run_tax_subagent(query: str) -> str:
    """计税子 Agent 核心逻辑（async），由 tax_subagent 包装函数调用"""
    from agent.engine import get_llm, get_current_provider

    # 模型切换器：子 Agent 与主 Agent 使用同一 provider（contextvar 传播），
    # 避免主 Agent 用千问、子 Agent 却用默认 DeepSeek 的不一致。
    sub = get_tax_subagent(get_llm(get_current_provider()))
    result = await sub.ainvoke({"messages": [{"role": "user", "content": query}]})
    messages = result["messages"]
    answer, result_card, sources = _extract_fields(messages)

    if result_card is None:
        # v1.4 降级：复用 LLM 已生成的 tool_calls 参数直调原工具
        answer2, card2, src2, used = _fallback_reuse_args(messages, CALC_TOOL_NAMES)
        if used:
            answer, result_card, sources = answer2, card2, src2
        # v1.5 绕过检测：answer 含税额数字但无 result_card → 强制重算
        elif _contains_tax_amount(answer):
            logger.warning("tax_subagent: 检测到心算绕过（answer 含税额数字但无 result_card），强制重算")
            answer, result_card, sources = _forced_recalc(query, messages)

    return json.dumps({
        "answer": tag_tool_result(answer),
        "result_card": result_card,
        "sources": sources,
        "disclaimer": AI_DISCLAIMER,
    }, ensure_ascii=False)


async def _run_social_subagent(query: str) -> str:
    """社保子 Agent 核心逻辑（async），由 social_subagent 包装函数调用"""
    from agent.engine import get_llm, get_current_provider

    sub = get_social_subagent(get_llm(get_current_provider()))
    result = await sub.ainvoke({"messages": [{"role": "user", "content": query}]})
    messages = result["messages"]
    answer, result_card, sources = _extract_fields(messages)
    return json.dumps({
        "answer": tag_tool_result(answer),
        "result_card": result_card,
        "sources": sources,
        "disclaimer": AI_DISCLAIMER,
    }, ensure_ascii=False)


# ── @tool 包装（sync def，供主 Agent 的 ToolNode sync/async 两条路径调用）──


@tool
def tax_subagent(query: str) -> str:
    """计算个人所得税（工资/劳务/年终奖/个体户经营所得）。当用户需要算税时调用，
    内部由计税专家 Agent 处理：先查用户画像，再用法定税率表精确计算，最后回写画像。
    参数: query — 用户原始计税问题"""
    return asyncio.run(_run_tax_subagent(query))


@tool
def social_subagent(query: str) -> str:
    """查询社保公积金（缴费比例/缴存基数/五险一金/灵活就业）。当用户需要查社保时调用，
    内部由社保专家 Agent 处理：先查用户画像，再查询官方缴费比例，最后回写画像。
    参数: query — 用户原始社保问题"""
    return asyncio.run(_run_social_subagent(query))
