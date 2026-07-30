"""个税计算工具 — 包装 services/tax_engine.py

计算逻辑不走 LLM，纯 JSON 税率表 + Python 公式，零幻觉。
收入类型比例换算 + 年终奖对比计税逻辑从 routers/tax.py 继承。
"""

import json
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from services.tax_engine import (
    ANNUAL_DEDUCTION,
    calculate_comprehensive_tax,
    calculate_bonus_tax_separate,
    compare_bonus_methods,
)
from tools.base import AI_DISCLAIMER

# 收入类型 → 计入综合所得的比例
INCOME_RATIO: dict[str, float] = {
    "salary": 1.0,
    "labor_service": 0.8,
    "manuscript": 0.56,
    "royalty": 0.8,
}

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
            "answer": "\n".join(answer_parts),
            "result_card": result_card,
            "disclaimer": AI_DISCLAIMER,
        },
        ensure_ascii=False,
    )
