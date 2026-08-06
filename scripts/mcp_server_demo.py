"""MCP Server Demo — 财税计算工具封装

对应《财务RAG-工程收尾待办清单》§1：把 `calculate_income_tax` 等工具封装成
标准 MCP Server，验证"任何 MCP 兼容宿主可调用"。

协议：MCP（Model Context Protocol），FastMCP 实现（stdio 传输）
工具：
  - calculate_income_tax       综合所得个税（工资/劳务/稿酬/特许权使用费 + 年终奖对比）
  - calculate_business_tax     经营所得个税（个体工商户 B 表，5%-35% 超额累进）
  - query_social_insurance     社保公积金（郑州 2025 标准）

复用：backend/services/tax_engine.py + social_engine.py（纯 Python 计算，不走 LLM）
依赖：仅 mcp（开发环境），不引入 langchain —— 演示环境约束

用法：
  python scripts/mcp_server_demo.py                      # stdio 模式，MCP 宿主默认
  npx mcporter call tax-calc calculate_income_tax ...    # mcporter 命令行验证
"""

import json
import sys
from pathlib import Path
from typing import Optional

# 让 backend 可被 import（services/tax_engine.py / social_engine.py）
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from services.tax_engine import (  # noqa: E402
    ANNUAL_DEDUCTION,
    INCOME_RATIO,
    calculate_comprehensive_tax,
    calculate_bonus_tax_separate,
    compare_bonus_methods,
    calculate_business_tax,
)
from services.social_engine import (  # noqa: E402
    calculate_employee_social,
    calculate_flexible_social,
    calculate_housing_fund,
)

# 与 backend/tools/base.py 保持一致（MCP 侧不引入 langchain 依赖）
AI_DISCLAIMER = "本结果基于法定税率表计算，仅供参考，不构成税务意见；具体以税务机关核定为准。"

mcp = FastMCP(
    "tax-calc",
    instructions=(
        "你是一个财税计算助手。当用户询问个税、社保、公积金金额时，调用对应工具精确计算，"
        "不要自己心算。工具返回 JSON 字符串，包含 answer 文本与结构化 result_card。"
    ),
)


# ═══════════════════════════════════════════
# 工具 1 — 综合所得个税（A 表 + 年终奖对比）
# ═══════════════════════════════════════════

class IncomeTaxInput(BaseModel):
    """综合所得个税计算输入参数。"""
    annual_income: float = Field(description="年收入总额（元），如 96000 表示年收入 9.6 万元")
    income_type: str = Field(
        default="salary",
        description="收入类型: salary(工资薪金)/labor_service(劳务报酬)/manuscript(稿酬)/royalty(特许权使用费)",
    )
    social_insurance: float = Field(default=0, description="年三险一金个人缴纳部分（元）")
    deductions: dict = Field(
        default_factory=dict,
        description='专项附加扣除（月扣除额/元），如 {"housing_rent": 1500, "children_edu": 2000, "elderly_support": 3000}',
    )
    bonus: float = Field(default=0, description="年终奖（元），0 或省略则不计算年终奖")


@mcp.tool(description=(
    "计算个人所得税（综合所得）。当用户问\"交多少税\"\"算个税\"\"税率多少\""
    "\"年终奖交多少\"\"劳务报酬税\"\"稿酬税\"时调用。基于法定税率表精确计算。"
))
def calculate_income_tax(
    annual_income: float,
    income_type: str = "salary",
    social_insurance: float = 0,
    deductions: Optional[dict] = None,
    bonus: float = 0,
) -> str:
    """综合所得个税：年收入 × 计入比例 − 6 万 − 社保 − 专项附加扣除 → 查超额累进表。

    Args:
        annual_income: 年收入总额（元）
        income_type: 收入类型，salary/labor_service/manuscript/royalty
        social_insurance: 年三险一金个人缴纳部分（元）
        deductions: 专项附加扣除（月扣除额/元），如 {"housing_rent": 1500}
        bonus: 年终奖（元），>0 时追加单独计税与并入综合所得对比
    """
    if deductions is None:
        deductions = {}

    if income_type not in INCOME_RATIO:
        return json.dumps(
            {"answer": f"收入类型错误: {income_type}，可选: salary/labor_service/manuscript/royalty"},
            ensure_ascii=False,
        )

    ratio = INCOME_RATIO[income_type]
    taxable_basis = annual_income * ratio
    bonus_taxable = bonus * ratio

    special_deductions = (
        deductions.get("housing_rent", 0)
        + deductions.get("children_edu", 0)
        + deductions.get("elderly_support", 0)
    ) * 12

    result = calculate_comprehensive_tax(taxable_basis, social_insurance, special_deductions)

    answer_parts = [
        f"年收入: {annual_income:.0f} 元（{income_type}，计入比例 {ratio*100:.0f}%）",
        f"计税基数: {taxable_basis:.0f} 元",
        f"起征点: {ANNUAL_DEDUCTION} 元",
        f"社保扣除: {social_insurance:.0f} 元",
        f"专项附加扣除: {special_deductions:.0f} 元/年",
        f"应纳税所得额: {result['taxable_income']:.2f} 元",
        f"适用税率: {result['rate']}（第{result['level']}级）",
        f"应纳税额: {result['tax_amount']:.2f} 元",
        f"计算公式: {result['formula']}",
    ]

    result_card = {
        "type": "tax_result",
        "data": {
            "annual_income": annual_income,
            "income_type": income_type,
            "taxable_basis": round(taxable_basis, 2),
            "taxable_income": result["taxable_income"],
            "tax_amount": result["tax_amount"],
            "marginal_rate": result["rate"],
            "bracket_level": result["level"],
            "formula": result["formula"],
            "breakdown": {
                "annual_deduction": ANNUAL_DEDUCTION,
                "social_insurance": social_insurance,
                "special_deductions": special_deductions,
            },
            "legal_basis": "《个人所得税法》附表一；国发〔2023〕13号",
        },
    }

    if bonus > 0:
        bonus_result = calculate_bonus_tax_separate(bonus)
        comparison = compare_bonus_methods(taxable_basis, bonus_taxable, social_insurance, special_deductions)
        result_card["data"]["bonus"] = {
            "amount": bonus,
            "separate_tax": bonus_result["tax_amount"],
            "separate_formula": bonus_result["formula"],
            "recommendation": comparison["recommendation"],
            "saving": comparison["saving"],
        }
        answer_parts.append(
            f"年终奖 {bonus:.0f} 元: 单独计税 {bonus_result['tax_amount']:.2f} 元，"
            f"推荐{comparison['recommendation']}（省 {comparison['saving']:.2f} 元）"
        )

    return json.dumps(
        {"answer": "\n".join(answer_parts), "result_card": result_card, "disclaimer": AI_DISCLAIMER},
        ensure_ascii=False,
    )


# ═══════════════════════════════════════════
# 工具 2 — 经营所得个税（个体工商户 B 表）
# ═══════════════════════════════════════════

class BusinessTaxInput(BaseModel):
    """经营所得个税计算输入参数。"""
    period: str = Field(default="quarter", description="申报周期: quarter(季度) 或 annual(年度)")
    income: float = Field(description="经营收入（元），季度模式填季度收入，年度模式填年度收入")
    cost: float = Field(default=0, description="成本费用（元），含房租/进货/人工/水电")
    social_insurance: float = Field(default=0, description="自己交的社保（元/年），灵活就业身份")
    previous_loss: float = Field(default=0, description="弥补以前年度亏损（元）")
    deductions: dict = Field(
        default_factory=dict,
        description='专项附加扣除（月扣除额/元），如 {"children_edu": 2000, "elderly_support": 3000}，不含 housing_rent（房租算成本）',
    )


@mcp.tool(description=(
    "计算个体工商户经营所得个税。当用户提到\"个体户\"\"经营所得\"\"B表\""
    "\"个体工商户申报\"\"开店交税\"\"经营所得税\"时调用。5%-35% 五级超额累进。"
))
def calculate_business_tax_mcp(
    period: str = "quarter",
    income: float = 0,
    cost: float = 0,
    social_insurance: float = 0,
    previous_loss: float = 0,
    deductions: Optional[dict] = None,
) -> str:
    """经营所得个税：年化收入 − 成本 − 社保 − 6 万 − 专项附加扣除 − 亏损弥补 → 查 5%-35% 累进表。

    Args:
        period: 申报周期，quarter(季度) 或 annual(年度)
        income: 经营收入（元），季度模式填季度收入
        cost: 成本费用（元）
        social_insurance: 自己交的社保（元/年）
        previous_loss: 弥补以前年度亏损（元）
        deductions: 专项附加扣除（月扣除额/元）
    """
    if deductions is None:
        deductions = {}

    is_quarter = period == "quarter"
    annual_income = income * 4 if is_quarter else income
    annual_cost = cost * 4 if is_quarter else cost

    special_annual = sum(deductions.values()) * 12
    taxable = annual_income - annual_cost - social_insurance - ANNUAL_DEDUCTION - special_annual - previous_loss

    result = calculate_business_tax(taxable)
    tax_amount = result["tax_amount"]

    if is_quarter and taxable > 0:
        quarterly_taxable = taxable / 4
        quarterly_tax = tax_amount / 4
    else:
        quarterly_taxable = taxable
        quarterly_tax = tax_amount

    period_label = "季度" if is_quarter else "年度"
    answer_parts = [
        "【经营所得个税计算】",
        f"申报周期: {period_label}",
        f"年化经营收入: {annual_income:.0f} 元",
        f"年化成本费用: {annual_cost:.0f} 元",
        f"社保扣除: {social_insurance:.0f} 元/年",
        f"基本扣除: {ANNUAL_DEDUCTION} 元/年",
        f"专项附加扣除: {special_annual:.0f} 元/年",
        f"应纳税所得额: {taxable:.2f} 元",
        f"适用税率: {result['rate']}（第{result['level']}级）",
        f"应纳税额: {quarterly_tax:.2f} 元" + (f"/{period_label}" if is_quarter else "元/年"),
        f"计算公式: {result['formula']}",
    ]
    if previous_loss > 0:
        answer_parts.insert(6, f"弥补以前年度亏损: {previous_loss:.0f} 元")

    result_card = {
        "type": "tax_result",
        "data": {
            "tax_type": "business_income",
            "period": period,
            "annual_income": round(annual_income, 2),
            "annual_cost": round(annual_cost, 2),
            "social_insurance": social_insurance,
            "special_deductions_annual": special_annual,
            "previous_loss": previous_loss,
            "annual_deduction": ANNUAL_DEDUCTION,
            "taxable_income": round(taxable, 2),
            "tax_amount": round(quarterly_tax, 2),
            "annual_tax": round(tax_amount, 2) if is_quarter else None,
            "marginal_rate": result["rate"],
            "bracket_level": result["level"],
            "formula": result["formula"],
            "legal_basis": "《个人所得税法》附表二（经营所得 5%-35% 五级超额累进）",
        },
    }
    if is_quarter:
        result_card["data"]["note"] = "季度预缴按年化计税后还原，年底需汇算清缴多退少补"

    return json.dumps(
        {"answer": "\n".join(answer_parts), "result_card": result_card, "disclaimer": AI_DISCLAIMER},
        ensure_ascii=False,
    )


# ═══════════════════════════════════════════
# 工具 3 — 社保公积金（郑州）
# ═══════════════════════════════════════════

class SocialInsuranceInput(BaseModel):
    """社保公积金计算输入参数。"""
    salary: float = Field(default=8000, description="月工资（元），用户未提供时默认 8000")
    employment_type: str = Field(default="employee", description="就业类型: employee(单位职工) 或 flexible(灵活就业)")
    housing_fund_ratio: float = Field(default=0.12, description="公积金缴存比例（0.05~0.12），默认 0.12")
    flexible_base_level: int = Field(default=1, description="灵活就业缴费档次: 0=下限(60%), 1=100%, 2=200%, 3=上限(300%)")


@mcp.tool(description=(
    "查询社保和公积金缴费金额。当用户问\"社保扣多少\"\"五险一金\"\"缴费比例\""
    "\"公积金缴存基数\"\"灵活就业交多少\"时调用。当前仅支持郑州。"
))
def query_social_insurance(
    salary: float = 8000,
    employment_type: str = "employee",
    housing_fund_ratio: float = 0.12,
    flexible_base_level: int = 1,
) -> str:
    """社保公积金计算（郑州 2025 标准）。

    Args:
        salary: 月工资（元）
        employment_type: employee(单位职工) / flexible(灵活就业)
        housing_fund_ratio: 公积金缴存比例（0.05~0.12）
        flexible_base_level: 灵活就业档次 0~3
    """
    if employment_type not in ("employee", "flexible"):
        return json.dumps(
            {"answer": f"就业类型错误: {employment_type}，可选: employee / flexible"},
            ensure_ascii=False,
        )

    if employment_type == "flexible":
        if not isinstance(flexible_base_level, int) or not 0 <= flexible_base_level <= 3:
            return json.dumps(
                {"answer": f"缴费档次错误: {flexible_base_level}，可选 0(60%下限) / 1(100%) / 2(200%) / 3(300%上限)"},
                ensure_ascii=False,
            )
        flex = calculate_flexible_social(base_level=flexible_base_level)
        _level_labels = ["60%下限", "100%", "200%", "300%上限"]
        answer_parts = ["灵活就业社保（郑州）", f"缴费档次: {_level_labels[flexible_base_level]}"]
        for name, info in flex["breakdown"].items():
            answer_parts.append(f"{name}: 基数 {info['base']:.0f} × {info['rate']*100:.0f}% = {info['amount']:.2f} 元/月")
        answer_parts.append(f"月缴合计: {flex['total_monthly']:.2f} 元")
        result_card = {
            "type": "social_result",
            "data": {"city": "zhengzhou", "employment_type": "flexible", "salary": salary,
                     "flexible_base_level": flexible_base_level, **flex,
                     "legal_basis": "《社会保险法》；郑州市2025年度社保缴费基数标准"},
        }
    else:
        social = calculate_employee_social(salary)
        housing = calculate_housing_fund(salary, housing_fund_ratio)
        answer_parts = ["单位职工社保（郑州）", f"缴费基数: {social['base']:.0f} 元"]
        for name, info in social["breakdown"].items():
            answer_parts.append(f"{name}: 单位 {info['company']:.2f} + 个人 {info['personal']:.2f} 元/月")
        answer_parts.append(
            f"公积金: 基数 {housing['base']:.0f} × {housing_fund_ratio*100:.0f}% = "
            f"个人 {housing['personal']:.2f} + 单位 {housing['company']:.2f} 元/月"
        )
        answer_parts.append(f"个人月缴合计: {social['total_personal'] + housing['personal']:.2f} 元")
        answer_parts.append(f"单位月缴合计: {social['total_company'] + housing['company']:.2f} 元")
        result_card = {
            "type": "social_result",
            "data": {"city": "zhengzhou", "employment_type": "employee", "salary": salary,
                     "social_insurance": social, "housing_fund": housing,
                     "total_personal": round(social["total_personal"] + housing["personal"], 2),
                     "total_company": round(social["total_company"] + housing["company"], 2),
                     "legal_basis": "《社会保险法》；郑州市2025年度社保缴费基数标准"},
        }

    return json.dumps(
        {"answer": "\n".join(answer_parts), "result_card": result_card, "disclaimer": AI_DISCLAIMER},
        ensure_ascii=False,
    )


if __name__ == "__main__":
    # stdio 传输模式：MCP 兼容宿主（如 WorkBuddy / Claude Desktop / mcporter）通过 stdin/stdout 调用
    mcp.run(transport="stdio")
