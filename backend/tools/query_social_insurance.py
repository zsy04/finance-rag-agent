"""社保公积金计算工具 — 包装 services/social_engine.py

当前仅支持郑州。职工社保(五险) + 公积金，或灵活就业社保 + 公积金。
"""

import json
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from services.social_engine import (
    calculate_employee_social,
    calculate_flexible_social,
    calculate_housing_fund,
)
from tools.base import AI_DISCLAIMER

LEGAL_BASIS = "《社会保险法》；郑州市2025年度社保缴费基数标准"


class SocialInsuranceInput(BaseModel):
    """社保计算输入参数。"""
    salary: float = Field(default=8000, description="月工资（元），如 8000。用户未提供时默认 8000")
    employment_type: str = Field(
        default="employee",
        description="就业类型: employee(单位职工) 或 flexible(灵活就业)"
    )
    housing_fund_ratio: float = Field(
        default=0.12,
        description="公积金缴存比例（0.05~0.12），默认0.12（12%）"
    )
    flexible_base_level: int = Field(
        default=1,
        description="灵活就业缴费档次: 0=下限(60%), 1=100%, 2=200%, 3=上限(300%)，默认1"
    )


@tool(args_schema=SocialInsuranceInput)
def query_social_insurance(
    salary: float,
    employment_type: str = "employee",
    housing_fund_ratio: float = 0.12,
    flexible_base_level: int = 1,
) -> str:
    """查询社保和公积金缴费金额。当用户提到"社保扣多少""五险一金""缴费比例""公积金缴存基数""灵活就业交多少""社保基数""公积金比例"等问题时使用此工具。当前仅支持郑州。用户可能只问比例不提供工资，工具会用默认工资 8000 计算。

    参数:
        salary: 月工资（元）
        employment_type: 就业类型: employee(单位职工) / flexible(灵活就业)
        housing_fund_ratio: 公积金缴存比例（0.05~0.12），默认0.12
        flexible_base_level: 灵活就业缴费档次: 0(60%)/1(100%)/2(200%)/3(300%)，默认1
    """

    # 枚举兜底校验
    if employment_type not in ("employee", "flexible"):
        return json.dumps(
            {"answer": f"就业类型错误: {employment_type}，可选: employee / flexible"},
            ensure_ascii=False,
        )

    if employment_type == "flexible":
        flex = calculate_flexible_social(base_level=flexible_base_level)
        answer_parts = [
            f"灵活就业社保（郑州）",
            f"缴费档次: {['60%下限', '100%', '200%', '300%上限'][flexible_base_level]}",
        ]
        for name, info in flex["breakdown"].items():
            answer_parts.append(
                f"{name}: 基数 {info['base']:.0f} × {info['rate']*100:.0f}% = {info['amount']:.2f} 元/月"
            )
        answer_parts.append(f"月缴合计: {flex['total_monthly']:.2f} 元")

        result_card = {
            "type": "social_result",
            "data": {
                "city": "zhengzhou",
                "employment_type": "flexible",
                "salary": salary,
                "flexible_base_level": flexible_base_level,
                **flex,
                "legal_basis": LEGAL_BASIS,
            },
        }
    else:
        social = calculate_employee_social(salary)
        housing = calculate_housing_fund(salary, housing_fund_ratio)

        answer_parts = [
            f"单位职工社保（郑州）",
            f"缴费基数: {social['base']:.0f} 元",
        ]
        for name, info in social["breakdown"].items():
            answer_parts.append(
                f"{name}: 单位 {info['company']:.2f} + 个人 {info['personal']:.2f} 元/月"
            )
        answer_parts.append(
            f"公积金: 基数 {housing['base']:.0f} × {housing_fund_ratio*100:.0f}% = "
            f"个人 {housing['personal']:.2f} + 单位 {housing['company']:.2f} 元/月"
        )
        answer_parts.append(
            f"个人月缴合计: {social['total_personal'] + housing['personal']:.2f} 元"
        )
        answer_parts.append(
            f"单位月缴合计: {social['total_company'] + housing['company']:.2f} 元"
        )

        result_card = {
            "type": "social_result",
            "data": {
                "city": "zhengzhou",
                "employment_type": "employee",
                "salary": salary,
                "social_insurance": social,
                "housing_fund": housing,
                "total_personal": round(social["total_personal"] + housing["personal"], 2),
                "total_company": round(social["total_company"] + housing["company"], 2),
                "legal_basis": LEGAL_BASIS,
            },
        }

    return json.dumps(
        {
            "answer": "\n".join(answer_parts),
            "result_card": result_card,
            "disclaimer": AI_DISCLAIMER,
        },
        ensure_ascii=False,
    )
