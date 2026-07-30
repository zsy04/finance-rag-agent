from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.tax_engine import (
    calculate_bonus_tax_separate,
    calculate_comprehensive_tax,
    compare_bonus_methods,
)

router = APIRouter(prefix="/api/tax", tags=["个税计算"])

class TaxRequest(BaseModel):
    annual_income: float = Field(...,description="年收入总额（元）",gt=0)
    income_type:str = Field(default="salary",description="salary|labor_service|manuscript")
    social_insurance: float = Field(default=0, ge=0, description="年三险一金（元）")
    housing_rent: float = Field(default=0, ge=0, description="租房月扣除额")
    children_edu: float = Field(default=0, ge=0, description="子女教育月扣除额")
    elderly_support: float = Field(default=0, ge=0, description="赡养老人月扣除额")
    bonus: float = Field(default=0, ge=0, description="年终奖（元）")


@router.post("/calculate")
async def calculate(request: TaxRequest):
    # 收入类型换算
    ratio_map = {"salary": 1.0, "labor_service": 0.8, "manuscript": 0.56, "royalty": 0.8}
    taxable_basis = request.annual_income * ratio_map.get(request.income_type, 1.0)

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
            "annual_deduction": 60000,
            "social_insurance": request.social_insurance,
            "special_deductions": special_deductions,
        },
        "legal_basis": "《个人所得税法》附表一；国发〔2023〕13号",
        "disclaimer": "⚠️ 本结果由 AI 辅助计算，仅供参考。以税务机关最终核定为准。12366",
    }

    if request.bonus > 0:
        bonus_result = calculate_bonus_tax_separate(request.bonus)
        comparison = compare_bonus_methods(taxable_basis, request.bonus, request.social_insurance, special_deductions)
        response["bonus"] = {
            "amount": request.bonus,
            "separate_tax": bonus_result["tax_amount"],
            "separate_formula": bonus_result["formula"],
            "recommendation": comparison["recommendation"],
            "saving": comparison["saving"],
        }

    return response
