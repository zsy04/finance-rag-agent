from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.social_engine import (calculate_employee_social,
                                    calculate_flexible_social,
                                    calculate_housing_fund)

router = APIRouter(prefix="/api/social", tags=["社保计算"])

class SocialRequest(BaseModel):
    salary:float = Field(...,description="月工资（元）", gt=0)
    city:str = Field(default="zhengzhou",description="城市")
    employment_type:str = Field(default="employee",description="employee|flexible")
    housing_fund_ratio: float = Field(default=0.12, ge=0.05, le=0.12, description="公积金比例")


@router.post("/calculate")
async def calculate(request: SocialRequest):
    if request.employment_type == "flexible":
        flex = calculate_flexible_social()
        return {
            "city": request.city,
            "employment_type": "flexible",
            **flex,
        }

    social = calculate_employee_social(request.salary)
    housing = calculate_housing_fund(request.salary, request.housing_fund_ratio)

    return {
        "city": request.city,
        "employment_type": "employee",
        "salary": request.salary,
        "social_insurance": social,
        "housing_fund": housing,
        "total_personal": round(social["total_personal"] + housing["personal"], 2),
        "total_company": round(social["total_company"] + housing["company"], 2),
    }
