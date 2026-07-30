"""Agent 工具集 — 所有 @tool 函数 + ALL_TOOLS 列表

工具列表顺序影响 LLM 选择倾向（先列出的更容易被选中）：
  get_user_context 放第一位 → Agent 优先检查上下文
"""

from .user_context import get_user_context, update_user_context
from .search_knowledge import search_knowledge
from .calculate_income_tax import calculate_income_tax
from .query_social_insurance import query_social_insurance
from .fill_tax_form import fill_tax_form, get_required_fields as get_form_fields
from .filing_guide import filing_guide

ALL_TOOLS = [
    get_user_context,
    search_knowledge,
    calculate_income_tax,
    query_social_insurance,
    update_user_context,
    fill_tax_form,
    filing_guide,
    # get_form_fields,  # 可选：是否暴露给 Agent（Agent 也可通过 fill_tax_form 的 docstring 了解字段）
]
