"""个税计算引擎 — 纯 Python，不走 LLM，零幻觉"""

import json
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent.parent / "rag-data" / "processed" / "national" / "rates" / "tax_rate_tables.json"

with open(DATA_FILE, encoding="utf-8") as f:
    _TAX = json.load(f)["tables"]["personal_income_tax"]

ANNUAL_DEDUCTION = _TAX["annual_deduction"]  # 60000
COMPREHENSIVE_BRACKETS = _TAX["comprehensive"]["brackets"]
BUSINESS_BRACKETS = _TAX["business"]["brackets"]
BONUS_MONTHLY_BRACKETS = _TAX["annual_bonus"]["method_separate"]["monthly_brackets"]


def _find_bracket(taxable: float, brackets: list[dict]) -> dict:
    """在超额累进税率表中定位适用级距"""
    for b in brackets:
        high = b.get("income_high") or b.get("monthly_income_high")
        if high is None or taxable <= high:
            return b
    return brackets[-1]  # 兜底：最高档


def calculate_comprehensive_tax(
    annual_income: float,
    social_insurance: float = 0,
    special_deductions: float = 0,
) -> dict:
    """
    综合所得个税（工资薪金 / 劳务报酬 / 稿酬 / 特许权使用费）

    公式：应纳税所得额 = 年收入 - 60000 - 社保 - 专项附加扣除
    """
    taxable = annual_income - ANNUAL_DEDUCTION - social_insurance - special_deductions

    if taxable <= 0:
        return {
            "taxable_income": 0,
            "tax_amount": 0,
            "rate": "0%",
            "level": 0,
            "formula": "应纳税所得额 ≤ 0，无需缴纳",
        }

    bracket = _find_bracket(taxable, COMPREHENSIVE_BRACKETS)
    tax = taxable * bracket["rate"] - bracket["quick_deduction"]

    return {
        "taxable_income": round(taxable, 2),
        "tax_amount": round(max(tax, 0), 2),
        "rate": f"{bracket['rate'] * 100:.0f}%",
        "level": bracket["level"],
        "formula": f"{taxable:.2f} × {bracket['rate'] * 100:.0f}% − {bracket['quick_deduction']} = {max(tax, 0):.2f}",
    }


def calculate_bonus_tax_separate(bonus: float) -> dict:
    """
    年终奖单独计税

    步骤：年终奖 ÷ 12 → 查月度税率表 → 应纳税额 = 年终奖 × 税率 − 速算扣除数
    """
    monthly = bonus / 12
    bracket = _find_bracket(monthly, BONUS_MONTHLY_BRACKETS)
    tax = bonus * bracket["rate"] - bracket["quick_deduction"]

    return {
        "monthly_equivalent": round(monthly, 2),
        "tax_amount": round(max(tax, 0), 2),
        "rate": f"{bracket['rate'] * 100:.0f}%",
        "level": bracket["level"],
        "formula": f"{bonus:.2f} × {bracket['rate'] * 100:.0f}% − {bracket['quick_deduction']} = {max(tax, 0):.2f}",
    }


def compare_bonus_methods(
    annual_income: float,
    bonus: float,
    social_insurance: float = 0,
    special_deductions: float = 0,
) -> dict:
    """
    年终奖计税方式对比：单独计税 vs 并入综合所得，推荐税额较低者
    """
    # 单独计税
    salary_tax = calculate_comprehensive_tax(annual_income, social_insurance, special_deductions)
    bonus_tax = calculate_bonus_tax_separate(bonus)
    total_separate = salary_tax["tax_amount"] + bonus_tax["tax_amount"]

    # 并入综合所得
    merged_result = calculate_comprehensive_tax(
        annual_income + bonus, social_insurance, special_deductions
    )
    total_merged = merged_result["tax_amount"]

    best = "separate" if total_separate <= total_merged else "merged"
    return {
        "separate": {"salary_tax": salary_tax["tax_amount"], "bonus_tax": bonus_tax["tax_amount"], "total": round(total_separate, 2)},
        "merged": {"total": round(total_merged, 2)},
        "recommendation": "单独计税" if best == "separate" else "并入综合所得",
        "saving": round(abs(total_separate - total_merged), 2),
    }


def calculate_business_tax(annual_net_income: float) -> dict:
    """
    经营所得个税（个体工商户 / 个人独资企业 / 合伙企业）

    公式：应纳税所得额 = 年收入 − 成本 − 费用 − 损失（这里传入的是净所得）
    """
    taxable = annual_net_income

    if taxable <= 0:
        return {
            "taxable_income": 0,
            "tax_amount": 0,
            "rate": "0%",
            "level": 0,
        }

    bracket = _find_bracket(taxable, BUSINESS_BRACKETS)
    tax = taxable * bracket["rate"] - bracket["quick_deduction"]

    return {
        "taxable_income": round(taxable, 2),
        "tax_amount": round(max(tax, 0), 2),
        "rate": f"{bracket['rate'] * 100:.0f}%",
        "level": bracket["level"],
        "formula": f"{taxable:.2f} × {bracket['rate'] * 100:.0f}% − {bracket['quick_deduction']} = {max(tax, 0):.2f}",
    }
