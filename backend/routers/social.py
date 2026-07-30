from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.social_engine import (calculate_employee_social,
                                    calculate_flexible_social,
                                    calculate_housing_fund)

router = APIRouter(prefix="/api/social", tags=["社保计算"])

# 当前 MVP 仅支持郑州。若要扩展，需在 services/social_engine.py 接入多城市数据。
SUPPORTED_CITIES: dict[str, str] = {
    "zhengzhou": "zhengzhou",
    "郑州": "zhengzhou",
}


class SocialRequest(BaseModel):
    salary: float = Field(..., description="月工资（元）", gt=0)
    city: Literal["zhengzhou", "郑州"] = Field(default="zhengzhou", description="城市（目前仅支持郑州）")
    employment_type: Literal["employee", "flexible"] = Field(
        default="employee", description="employee|flexible"
    )
    housing_fund_ratio: float = Field(default=0.12, ge=0.05, le=0.12, description="公积金比例")
    # 灵活就业缴费档次：0=下限(60%) / 1=100% / 2=200% / 3=上限(300%)
    flexible_base_level: int = Field(default=1, ge=0, le=3, description="灵活就业缴费档次")


@router.post("/calculate")
async def calculate(request: SocialRequest):
    city_key = SUPPORTED_CITIES[request.city]

    if request.employment_type == "flexible":
        flex = calculate_flexible_social(base_level=request.flexible_base_level)
        return {
            "city": city_key,
            "employment_type": "flexible",
            "salary": request.salary,
            "flexible_base_level": request.flexible_base_level,
            **flex,
        }

    social = calculate_employee_social(request.salary)
    housing = calculate_housing_fund(request.salary, request.housing_fund_ratio)

    return {
        "city": city_key,
        "employment_type": "employee",
        "salary": request.salary,
        "social_insurance": social,
        "housing_fund": housing,
        "total_personal": round(social["total_personal"] + housing["personal"], 2),
        "total_company": round(social["total_company"] + housing["company"], 2),
    }
