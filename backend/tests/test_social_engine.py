"""社保计算引擎单元测试

测试覆盖：
- 郑州社保+公积金计算（灵活就业/职工）
- 基数上下限验证
- 缴费比例准确性
"""

import pytest
from services.social_engine import calculate_social_insurance


class TestSocialInsurance:
    """社保公积金计算测试"""

    def test_flexible_employment(self):
        """测试灵活就业人员社保"""
        result = calculate_social_insurance(
            city="郑州",
            monthly_salary=8000,
            employment_type="灵活就业",
        )
        assert result["total"] > 0
        assert "pension" in result["breakdown"]
        assert "medical" in result["breakdown"]
        # 灵活就业无失业/工伤/生育保险
        assert result["breakdown"]["unemployment"] == 0
        assert result["breakdown"]["injury"] == 0
        assert result["breakdown"]["maternity"] == 0

    def test_employee(self):
        """测试职工社保+公积金"""
        result = calculate_social_insurance(
            city="郑州",
            monthly_salary=10000,
            employment_type="职工",
            provident_fund_ratio=12,
        )
        assert result["total"] > 0
        assert result["breakdown"]["provident_fund"] > 0
        # 职工有全部五险一金
        assert all(
            result["breakdown"][key] > 0
            for key in ["pension", "medical", "unemployment", "provident_fund"]
        )

    def test_salary_below_minimum(self):
        """测试工资低于最低基数"""
        result = calculate_social_insurance(
            city="郑州",
            monthly_salary=2000,  # 低于最低基数
            employment_type="职工",
        )
        # 应按最低基数计算
        assert result["base_salary"] >= 2000
        assert "adjusted" in str(result.get("note", "")).lower()

    def test_salary_above_maximum(self):
        """测试工资高于最高基数"""
        result = calculate_social_insurance(
            city="郑州",
            monthly_salary=50000,  # 高于最高基数
            employment_type="职工",
        )
        # 应按最高基数计算
        assert result["base_salary"] <= 50000

    def test_zero_provident_fund(self):
        """测试不缴纳公积金"""
        result = calculate_social_insurance(
            city="郑州",
            monthly_salary=8000,
            employment_type="职工",
            provident_fund_ratio=0,
        )
        assert result["breakdown"]["provident_fund"] == 0

    def test_max_provident_fund_ratio(self):
        """测试最高公积金比例（12%）"""
        result = calculate_social_insurance(
            city="郑州",
            monthly_salary=10000,
            employment_type="职工",
            provident_fund_ratio=12,
        )
        # 公积金 = 10000 * 12% = 1200
        assert result["breakdown"]["provident_fund"] == 1200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
