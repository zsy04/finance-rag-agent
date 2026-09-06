from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from services.tax_engine import (
    ANNUAL_DEDUCTION,
    INCOME_RATIO,
    calculate_bonus_tax_separate,
    calculate_comprehensive_tax,
    compare_bonus_methods,
    validate_special_deductions,
)

router = APIRouter(prefix="/api/tax", tags=["个税计算"])


class TaxRequest(BaseModel):
    annual_income: float = Field(...,description="年收入总额（元）",gt=0)
    income_type: Literal["salary", "labor_service", "manuscript", "royalty"] = Field(
        default="salary", description="salary|labor_service|manuscript|royalty"
    )
    social_insurance: float = Field(default=0, ge=0, description="年三险一金（元）")
    housing_rent: float = Field(default=0, ge=0, description="租房月扣除额")
    children_edu: float = Field(default=0, ge=0, description="子女教育月扣除额")
    elderly_support: float = Field(default=0, ge=0, description="赡养老人月扣除额")
    bonus: float = Field(default=0, ge=0, description="年终奖（元）")


@router.post("/calculate")
async def calculate(request: TaxRequest):
    # 专项附加扣除法律上限校验（2026-08-13）：防输入异常导致税额系统性偏低
    err = validate_special_deductions(
        housing_rent=request.housing_rent,
        children_edu=request.children_edu,
        elderly_support=request.elderly_support,
    )
    if err:
        raise HTTPException(status_code=422, detail=err)

    # 收入类型换算
    ratio = INCOME_RATIO[request.income_type]
    taxable_basis = request.annual_income * ratio
    # 年终奖同样按收入类型比例换算（与综合所得计税口径保持一致）
    bonus_taxable = request.bonus * ratio

    special_deductions = (request.housing_rent + request.children_edu + request.elderly_support) * 12

    result = calculate_comprehensive_tax(taxable_basis, request.social_insurance, special_deductions)

    response = {
        "annual_income": request.annual_income,
        "income_type": request.income_type,
        "taxable_basis": round(taxable_basis, 2),
        "taxable_income": result["taxable_income"],
        "tax_amount": result["tax_amount"],
        "marginal_rate": result["rate"],
        "bracket_level": result["level"],
        "formula": result["formula"],
        "breakdown": {
            "annual_deduction": ANNUAL_DEDUCTION,
            "social_insurance": request.social_insurance,
            "special_deductions": special_deductions,
        },
        "legal_basis": "《个人所得税法》附表一；国发〔2023〕13号",
        "disclaimer": "⚠️ 本结果由 AI 辅助计算，仅供参考。以税务机关最终核定为准。12366",
    }

    if request.bonus > 0:
        # 单独计税：年终奖按全额（不打折）查月度税率表
        bonus_result = calculate_bonus_tax_separate(request.bonus)
        # 对比计税：salary 部分用 taxable_basis，bonus 部分用同口径换算后的金额
        comparison = compare_bonus_methods(
            taxable_basis, bonus_taxable, request.social_insurance, special_deductions
        )
        response["bonus"] = {
            "amount": request.bonus,
            "separate_tax": bonus_result["tax_amount"],
            "separate_formula": bonus_result["formula"],
            "recommendation": comparison["recommendation"],
            "saving": comparison["saving"],
        }

    return response
