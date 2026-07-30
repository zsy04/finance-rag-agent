"""社保 + 公积金计算引擎 — 郑州 2025 年度标准"""

import json
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent.parent / "rag-data" / "processed" / "cities" / "zhengzhou" / "social_insurance.json"

with open(DATA_FILE, encoding="utf-8") as f:
    _SOCIAL = json.load(f)

BASE = _SOCIAL["base"]
EMPLOYEE = _SOCIAL["employee"]
FLEXIBLE = _SOCIAL["flexible_employment"]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _clamp_social(salary: float) -> float:
    return _clamp(salary, BASE["social_insurance_min"], BASE["social_insurance_max"])


def _clamp_housing(salary: float) -> float:
    info = EMPLOYEE["housing_fund"]
    return _clamp(salary, info["base_min"], info["base_max"])


def calculate_employee_social(salary: float) -> dict:
    """
    单位职工社保（五险）

    工资低于基数下限按下限，高于上限按上限
    """
    base = _clamp_social(salary)
    items = EMPLOYEE["social_insurance"]
    breakdown = {}
    total_personal = 0.0
    total_company = 0.0

    for key in ("pension", "medical", "unemployment", "work_injury", "maternity"):
        item = items[key]
        personal = round(base * item.get("personal_rate", 0), 2)
        company_rate = item.get("company_rate")
        # 工伤保险单位费率按行业浮动，数据中标记为 null，默认取中位数 1%
        if company_rate is None:
            company_rate = 0.01
        company = round(base * company_rate, 2)

        total_personal += personal
        total_company += company
        breakdown[item["label"]] = {"base": base, "rate_company": company_rate, "rate_personal": item.get("personal_rate", 0), "company": company, "personal": personal}

    return {
        "base": base,
        "breakdown": breakdown,
        "total_personal": round(total_personal, 2),
        "total_company": round(total_company, 2),
    }


def calculate_housing_fund(salary: float, ratio: float = 0.12) -> dict:
    """
    职工住房公积金

    ratio: 缴存比例，范围 5%–12%
    """
    base = _clamp_housing(salary)
    amount = round(base * ratio, 2)

    return {
        "base": base,
        "ratio": ratio,
        "personal": amount,
        "company": amount,
    }


def calculate_flexible_social(base_level: int = 1) -> dict:
    """
    灵活就业人员社保 + 公积金

    base_level: 0→下限(60%), 1→100%, 2→200%, 3→上限(300%)
    """
    pension_opts = FLEXIBLE["social_insurance"]["pension"]["base_options"]
    pension_base = pension_opts[base_level]["amount"]
    pension_amount = round(pension_base * 0.20, 2)

    medical_base = FLEXIBLE["social_insurance"]["medical"]["base"]
    medical_amount = round(medical_base * 0.10, 2)

    housing_info = FLEXIBLE["housing_fund"]
    housing_amount = _clamp(
        round(pension_base * housing_info["rate"], 2),
        housing_info["monthly_min"],
        housing_info["monthly_max"],
    )

    total = pension_amount + medical_amount + housing_amount

    return {
        "breakdown": {
            "养老保险": {"base": pension_base, "rate": 0.20, "amount": pension_amount},
            "医疗保险": {"base": medical_base, "rate": 0.10, "amount": medical_amount},
            "住房公积金": {"base": pension_base, "rate": housing_info["rate"], "amount": housing_amount},
        },
        "total_monthly": round(total, 2),
    }
