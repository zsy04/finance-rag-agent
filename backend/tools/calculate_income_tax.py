"""个税计算工具 — 包装 services/tax_engine.py

计算逻辑不走 LLM，纯 JSON 税率表 + Python 公式，零幻觉。
收入类型比例换算 + 年终奖对比计税逻辑从 routers/tax.py 继承。
"""

import json
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from services.tax_engine import (
    ANNUAL_DEDUCTION,
    INCOME_RATIO,
    calculate_comprehensive_tax,
    calculate_bonus_tax_separate,
    compare_bonus_methods,
    calculate_business_tax,
    validate_special_deductions,
)
from tools.base import AI_DISCLAIMER, tag_tool_result

LEGAL_BASIS = "《个人所得税法》附表一；国发〔2023〕13号"


class IncomeTaxInput(BaseModel):
    """个税计算输入参数。"""
    annual_income: float = Field(
        description="年收入总额（元），如 96000 表示年收入 9.6 万元"
    )
    income_type: str = Field(
        default="salary",
        description="收入类型，可选值: salary(工资薪金), labor_service(劳务报酬), manuscript(稿酬), royalty(特许权使用费)。默认 salary"
    )
    social_insurance: float = Field(
        default=0, description="年三险一金个人缴纳部分（元）"
    )
    deductions: dict = Field(
        default_factory=dict,
        description='专项附加扣除（月扣除额，元），如 {"housing_rent": 1500, "children_edu": 2000, "elderly_support": 3000}'
    )
    bonus: float = Field(
        default=0, description="年终奖（元），不传或为0则不计算年终奖"
    )


@tool(args_schema=IncomeTaxInput)
def calculate_income_tax(
    annual_income: float,
    income_type: str,
    social_insurance: float = 0,
    deductions: dict = None,
    bonus: float = 0,
) -> str:
    """计算个人所得税。当用户提到"交多少税""算个税""税率多少""年终奖交多少""劳务报酬税""稿酬税""个税怎么算"等问题时使用此工具。计算基于法定税率表，结果精确可靠。用户提供的金额可能不完整，工具内部会用默认值补全（income_type 默认 salary，social_insurance 默认 0，deductions 默认空）。

    参数:
        annual_income: 年收入总额（元）
        income_type: 收入类型: salary(工资) / labor_service(劳务报酬) / manuscript(稿酬) / royalty(特许权使用费)
        social_insurance: 年三险一金个人缴纳部分（元），默认0
        deductions: 专项附加扣除（月扣除额/元），如 {"housing_rent": 1500}，默认空
        bonus: 年终奖（元），默认0
    """
    if deductions is None:
        deductions = {}

    # 枚举兜底校验
    if income_type not in INCOME_RATIO:
        return json.dumps(
            {"answer": f"收入类型错误: {income_type}，可选: salary/labor_service/manuscript/royalty"},
            ensure_ascii=False,
        )

    # 收入类型换算
    ratio = INCOME_RATIO[income_type]
    taxable_basis = annual_income * ratio
    bonus_taxable = bonus * ratio

    # 专项附加扣除：月额 × 12
    housing_rent = deductions.get("housing_rent", 0)
    children_edu = deductions.get("children_edu", 0)
    elderly_support = deductions.get("elderly_support", 0)
    # 法律上限校验（2026-08-13）：防超限输入系统性压低税额
    err = validate_special_deductions(
        housing_rent=housing_rent,
        children_edu=children_edu,
        elderly_support=elderly_support,
    )
    if err:
        return json.dumps({"answer": err}, ensure_ascii=False)
    special_deductions = (housing_rent + children_edu + elderly_support) * 12

    # 计算个税
    result = calculate_comprehensive_tax(taxable_basis, social_insurance, special_deductions)

    # 构建回答文本
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
            "legal_basis": LEGAL_BASIS,
        },
    }

    # 年终奖对比
    if bonus > 0:
        bonus_result = calculate_bonus_tax_separate(bonus)
        comparison = compare_bonus_methods(
            taxable_basis, bonus_taxable, social_insurance, special_deductions
        )
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
        {
            "answer": tag_tool_result("\n".join(answer_parts)),
            "result_card": result_card,
            "disclaimer": AI_DISCLAIMER,
        },
        ensure_ascii=False,
    )


# ═══════════════════════════════════════════
# B 表 — 个体工商户经营所得计税
# ═══════════════════════════════════════════

BUSINESS_LEGAL_BASIS = "《个人所得税法》附表二（经营所得 5%-35% 五级超额累进）"


class BusinessTaxInput(BaseModel):
    """个体工商户经营所得计税输入参数。"""
    period: str = Field(
        default="quarter", description="申报周期: quarter(季度) 或 annual(年度)"
    )
    income: float = Field(description="经营收入（元），季度模式填季度收入，年度模式填年度收入")
    cost: float = Field(
        default=0, description="成本费用（元），含房租/进货/人工/水电等"
    )
    social_insurance: float = Field(
        default=0, description="自己交的社保（元/年），灵活就业身份缴纳"
    )
    previous_loss: float = Field(
        default=0, description="弥补以前年度亏损（元），上一年度亏损可在本年盈利时抵扣"
    )
    deductions: dict = Field(
        default_factory=dict,
        description='专项附加扣除（月扣除额，元），如 {"children_edu": 2000, "elderly_support": 3000}。注意个体户房租算成本，不含 housing_rent'
    )


@tool(args_schema=BusinessTaxInput)
def calculate_business_income_tax(
    period: str,
    income: float,
    cost: float = 0,
    social_insurance: float = 0,
    previous_loss: float = 0,
    deductions: dict = None,
) -> str:
    """计算个体工商户经营所得个税。当用户提到"个体户""经营所得""B表""个体工商户申报""开店交税""经营所得税"等问题时使用此工具。计算基于法定 5%-35% 五级超额累进税率表（个人所得税法附表二）。

    参数:
        period: 申报周期 — quarter(季度) 或 annual(年度)
        income: 经营收入（元）。quarter 模式填季度收入，annual 模式填年度收入
        cost: 成本费用（元），含房租/进货/人工/水电
        social_insurance: 自己交的社保（元/年）
        previous_loss: 弥补以前年度亏损（元）
        deductions: 专项附加扣除（月扣除额/元），不含 housing_rent（个体户房租算成本）
    """
    if deductions is None:
        deductions = {}

    # ── 1. 季度 → 年度折算 ──
    is_quarter = period == "quarter"
    annual_income = income * 4 if is_quarter else income
    annual_cost = cost * 4 if is_quarter else cost
    # 社保和亏损已经是年度的，不乘

    # ── 2. 专项附加扣除（6 项，不含住房租金） ──
    special_monthly = sum(deductions.values())
    special_annual = special_monthly * 12

    # ── 3. 应纳税所得额 ──
    taxable = annual_income - annual_cost - social_insurance - ANNUAL_DEDUCTION - special_annual - previous_loss

    # ── 4. 查税率表 ──
    result = calculate_business_tax(taxable)
    tax_amount = result["tax_amount"]

    # ── 5. 季度 → 还原 ──
    if is_quarter and taxable > 0:
        quarterly_taxable = taxable / 4
        quarterly_tax = tax_amount / 4
    else:
        quarterly_taxable = taxable
        quarterly_tax = tax_amount

    # ── 6. 构建回答 ──
    period_label = "季度" if is_quarter else "年度"
    period_unit = "季度" if is_quarter else "年度"
    income_label = f"{period_unit}经营收入"
    display_income = annual_income
    display_cost = annual_cost

    answer_parts = [
        f"【经营所得个税计算】",
        f"申报周期: {period_label}",
        f"年化经营收入: {display_income:.0f} 元",
        f"年化成本费用: {display_cost:.0f} 元（含房租/进货/人工/水电）",
        f"社保扣除: {social_insurance:.0f} 元/年",
        f"基本扣除: {ANNUAL_DEDUCTION} 元/年",
        f"专项附加扣除: {special_annual:.0f} 元/年" + (f"（{', '.join(f'{k}={v}元/月' for k,v in deductions.items())}）" if deductions else ""),
    ]
    if previous_loss > 0:
        answer_parts.append(f"弥补以前年度亏损: {previous_loss:.0f} 元")

    answer_parts += [
        f"应纳税所得额: {taxable:.2f} 元" + (f"（{period_unit}: {quarterly_taxable:.2f} 元）" if is_quarter else ""),
        f"适用税率: {result['rate']}（第{result['level']}级）",
        f"应纳税额: {quarterly_tax:.2f} 元" + (f"/{period_unit}" if is_quarter else "元/年") + (f"（年化: {tax_amount:.2f} 元）" if is_quarter else ""),
        f"计算公式: {result['formula']}",
    ]

    result_card = {
        "type": "tax_result",
        "data": {
            "tax_type": "business_income",
            "period": period,
            "annual_income": round(display_income, 2),
            "annual_cost": round(display_cost, 2),
            "social_insurance": social_insurance,
            "special_deductions_annual": special_annual,
            "previous_loss": previous_loss,
            "annual_deduction": ANNUAL_DEDUCTION,
            "taxable_income": round(taxable, 2),
            "quarterly_taxable": round(quarterly_taxable, 2) if is_quarter else None,
            "tax_amount": round(quarterly_tax, 2),
            "annual_tax": round(tax_amount, 2) if is_quarter else None,
            "marginal_rate": result["rate"],
            "bracket_level": result["level"],
            "formula": result["formula"],
            "legal_basis": BUSINESS_LEGAL_BASIS,
        },
    }

    if is_quarter:
        result_card["data"]["note"] = "季度预缴按年化计税后还原，年底需汇算清缴多退少补"

    return json.dumps(
        {
            "answer": tag_tool_result("\n".join(answer_parts)),
            "result_card": result_card,
            "disclaimer": AI_DISCLAIMER,
        },
        ensure_ascii=False,
    )
