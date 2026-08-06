"""对话上下文记忆工具（方案 C + 持久化）

get_user_context  — 读取当前会话已收集的用户信息
update_user_context — 更新当前会话的用户信息

存储：MemoryStore 抽象层 + SQLiteStore 实现（grill 定案 2026-08-05）
  - 画像表 user_contexts 主键 user_id，当前 user_id = thread_id 占位（登录体系后零返工）
  - thread_id 通过 contextvars.ContextVar 传递（PoC 已验证传播正常）
  - 后期换 MongoDB：仅换 storage 实现类，本文件业务零改动
"""

import json
import logging
from contextvars import ContextVar
from langchain_core.tools import tool

from storage.sqlite_store import get_store

logger = logging.getLogger(__name__)

# thread_id 通过 contextvar 传递给 @tool（PoC 已验证传播正常）
_current_thread_id: ContextVar[str] = ContextVar("current_thread_id")

CONTEXT_KEYS = {
    "city", "salary", "income_type",
    "housing_rent", "children_edu", "elderly_support",
    "deduction_medical", "deduction_mortgage", "deduction_baby",
    "previous_loss",  # 个体工商户以前年度亏损（元）
    "business_name",  # 个体工商户名称
    "business_credit_code",  # 统一社会信用代码
}


def set_current_thread_id(thread_id: str) -> None:
    """设置当前请求的 thread_id（供路由层调用）。

    提供公开 API 避免路由层直接访问私有 _current_thread_id。
    """
    _current_thread_id.set(thread_id)


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
    ctx = get_store().get_context(thread_id)  # 当前 user_id = thread_id 占位
    if not ctx:
        return json.dumps(
            {"message": "还没有收集到任何用户信息"}, ensure_ascii=False
        )
    return json.dumps(ctx, ensure_ascii=False)


@tool
def update_user_context(key: str, value: str) -> str:
    """更新当前会话的用户信息。用于 Agent 在对话中自动保存用户提供的个人数据。

    参数:
        key: 信息类型。可选值: city（城市）, salary（月薪/元）, income_type（收入类型）, housing_rent（租房月扣除额/元）, children_edu（子女教育月扣除额/元）, elderly_support（赡养老人月扣除额/元）, deduction_medical（大病医疗扣除额/元）, deduction_mortgage（住房贷款利息扣除额/元）, deduction_baby（婴幼儿照护扣除额/元）, previous_loss（个体工商户以前年度亏损/元）, business_name（个体工商户名称）, business_credit_code（统一社会信用代码）
        value: 对应的值。如 key="city", value="郑州"；key="previous_loss", value="5000"
    """
    try:
        thread_id = _current_thread_id.get()
    except LookupError:
        # contextvar 未初始化（传播失效）—— 返回错误而非降级为 "default"，
        # 避免所有用户数据写入同一槽位造成串号
        logger.error("update_user_context: contextvar 未初始化，thread_id 缺失")
        return json.dumps(
            {"error": "会话上下文未初始化，无法保存用户信息"}, ensure_ascii=False
        )
    if key not in CONTEXT_KEYS:
        return json.dumps(
            {"error": f"不支持的 key: {key}，可选: {list(CONTEXT_KEYS)}"},
            ensure_ascii=False,
        )
    get_store().update_context(thread_id, key, value)
    return json.dumps(
        {"updated": key, "value": value}, ensure_ascii=False
    )
