"""Agent 工具集 — 所有 @tool 函数

ALL_TOOLS 组装已移至 agent/engine.py（按 AGENT_MODE 多形态组装，避免循环导入）。
本模块只做工具导出声明。
"""

from .user_context import get_user_context, update_user_context
from .search_knowledge import search_knowledge
from .calculate_income_tax import calculate_income_tax, calculate_business_income_tax
from .query_social_insurance import query_social_insurance
from .fill_tax_form import fill_tax_form, get_required_fields as get_form_fields
from .filing_guide import filing_guide
from .subagents import tax_subagent, social_subagent
