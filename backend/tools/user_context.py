"""对话上下文记忆工具（方案 C）

get_user_context  — 读取当前会话已收集的用户信息
update_user_context — 更新当前会话的用户信息

存储：per-thread dict（contexts），thread_id 通过 contextvars.ContextVar 传递
锁：threading.Lock 保护并发写
"""

import json
import threading
from contextvars import ContextVar
from langchain_core.tools import tool

# thread_id 通过 contextvar 传递给 @tool（PoC 已验证传播正常）
_current_thread_id: ContextVar[str] = ContextVar("current_thread_id")
contexts: dict[str, dict] = {}  # {thread_id: {city, salary, income_type, deductions}}
_contexts_lock = threading.Lock()

CONTEXT_KEYS = {
    "city", "salary", "income_type",
    "housing_rent", "children_edu", "elderly_support",
}


@tool
def get_user_context() -> str:
    """获取当前会话中已收集的用户信息（城市、工资、收入类型、扣除项等）。
    在回答任何涉及个税或社保计算的问题之前，先调用此工具检查已有的用户信息。"""
    try:
        thread_id = _current_thread_id.get()
    except LookupError:
        return json.dumps(
            {"message": "还没有收集到任何用户信息"}, ensure_ascii=False
        )
    with _contexts_lock:
        ctx = contexts.get(thread_id, {})
    if not ctx:
        return json.dumps(
            {"message": "还没有收集到任何用户信息"}, ensure_ascii=False
        )
    return json.dumps(ctx, ensure_ascii=False)


@tool
def update_user_context(key: str, value: str) -> str:
    """更新当前会话的用户信息。用于 Agent 在对话中自动保存用户提供的个人数据。

    参数:
        key: 信息类型。可选值: city（城市）, salary（月薪/元）, income_type（收入类型：salary工资/labor_service劳务报酬/manuscript稿酬/royalty特许权）, housing_rent（租房月扣除额/元）, children_edu（子女教育月扣除额/元）, elderly_support（赡养老人月扣除额/元）
        value: 对应的值。如 key="city", value="郑州"；key="salary", value="8000"
    """
    try:
        thread_id = _current_thread_id.get()
    except LookupError:
        thread_id = "default"
    if key not in CONTEXT_KEYS:
        return json.dumps(
            {"error": f"不支持的 key: {key}，可选: {list(CONTEXT_KEYS)}"},
            ensure_ascii=False,
        )
    with _contexts_lock:
        if thread_id not in contexts:
            contexts[thread_id] = {}
        contexts[thread_id][key] = value
    return json.dumps(
        {"updated": key, "value": value}, ensure_ascii=False
    )
