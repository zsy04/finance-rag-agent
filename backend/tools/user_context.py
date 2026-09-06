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
import re
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

# ── P1-1 画像写入校验（2026-08-11，防画像污染）────────────
# 只接受 schema 内字段（CONTEXT_KEYS 已白名单）+ 值类型校验：
# 金额字段必须为数字、city 限短文本、income_type 限枚举，一律拒绝指令性特征词。
_AMOUNT_KEYS = {
    "salary", "housing_rent", "children_edu", "elderly_support",
    "deduction_medical", "deduction_mortgage", "deduction_baby", "previous_loss",
}

# 指令性特征词（命中即拒绝写入；与 chat.py 输出侧审计同口径，放这里共享）
INJECTION_MARKERS = ("忽略", "规则", "指令", "system", "prompt", "扮演")

_INCOME_TYPES = {
    "salary", "labor_service", "manuscript", "royalty", "business",
    "工资", "工资薪金", "劳务报酬", "稿酬", "稿酬所得", "特许权使用费",
    "经营所得", "个体工商户", "经营",
}

# ── P0-1 画像前置化（2026-08-11）────────────
# 序列化固定格式文本 → 路由层拼到消息首部（稳定前缀，prefix caching 友好），
# 主流程不再依赖 get_user_context 工具注入（工具保留作显式查询/子 Agent 兼容）。
_PROFILE_LABELS: dict[str, str] = {
    "city": "城市",
    "salary": "月薪",
    "income_type": "收入类型",
    "housing_rent": "住房租金",
    "children_edu": "子女教育",
    "elderly_support": "赡养老人",
    "deduction_medical": "大病医疗",
    "deduction_mortgage": "住房贷款利息",
    "deduction_baby": "婴幼儿照护",
    "previous_loss": "上年亏损",
    "business_name": "个体户名称",
    "business_credit_code": "统一社会信用代码",
}


def set_current_thread_id(thread_id: str) -> None:
    """设置当前请求的 thread_id（供路由层调用）。

    提供公开 API 避免路由层直接访问私有 _current_thread_id。
    """
    _current_thread_id.set(thread_id)


def serialize_user_profile(ctx: dict) -> str:
    """画像 dict → 固定格式文本（P0-1 前置化用）。

    仅取 schema 内字段、跳过空值，输出如：
        "用户画像：城市=郑州；月薪=8000；收入类型=工资"
    空画像返回 ""（路由层跳过注入）。
    """
    parts = []
    for key, label in _PROFILE_LABELS.items():
        val = ctx.get(key)
        if val not in (None, ""):
            parts.append(f"{label}={val}")
    if not parts:
        return ""
    return "用户画像：" + "；".join(parts)


def _normalize_amount(value: str) -> str | None:
    """金额文本 → 规范化数字字符串（元）；无法解析返回 None。

    容忍常见单位/分隔符（"8000元""1.5万""120,000""8000/月"），
    解析失败说明含指令/垃圾文本 → 拒绝写入。
    """
    s = value.strip().replace("，", "").replace(",", "")
    for unit in ("元", "月", "年", "/", "¥", "￥", "块"):
        s = s.replace(unit, "")
    # 万单位解析（2026-08-13 修复）：支持 "1.5万"=15000、"1万2"=12000（万后数字按千计）
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*万\s*(\d+(?:\.\d+)?)?\s*千?", s)
    if m:
        wan = float(m.group(1))
        qian = float(m.group(2)) * 1000 if m.group(2) else 0.0
        return str(wan * 10000 + qian)
    try:
        return str(float(s))
    except ValueError:
        return None


def _validate_value(key: str, value: str) -> str | None:
    """校验 update_user_context 待写入值。返回错误消息（None = 通过）。"""
    value = value.strip()
    if not value:
        return "值不能为空"
    if len(value) > 50:
        return "值过长（上限 50 字符）"
    low = value.lower()
    if any(m in low for m in INJECTION_MARKERS):
        return "值包含不允许的内容，已拒绝写入"

    if key in _AMOUNT_KEYS:
        normalized = _normalize_amount(value)
        if normalized is None:
            return "金额字段需为数字（如 8000 或 1.5万）"
        amount = float(normalized)
        if not (0 < amount <= 1_000_000_000):
            return "金额超出合理范围（0 ~ 10亿）"
        return None
    if key == "city":
        if len(value) > 10:
            return "城市名过长"
        return None
    if key == "income_type":
        if value not in _INCOME_TYPES:
            return f"收入类型不支持: {value}，可选: salary/劳务报酬/稿酬/特许权使用费/经营所得"
        return None
    # business_name / business_credit_code：仅长度 + 特征词校验
    return None


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

    # P1-1 值类型校验（防画像污染：拒绝指令文本/非法类型，金额规范化落库）
    err = _validate_value(key, value)
    if err is not None:
        logger.warning("update_user_context 拒绝写入 (key=%s, value=%r): %s", key, value, err)
        return json.dumps(
            {"error": f"拒绝保存: {err}"}, ensure_ascii=False
        )

    # 金额字段规范化（"1.5万"→"15000.0"），画像只存干净数字
    stored = _normalize_amount(value) if key in _AMOUNT_KEYS else value.strip()
    get_store().update_context(thread_id, key, stored)
    return json.dumps(
        {"updated": key, "value": stored}, ensure_ascii=False
    )
