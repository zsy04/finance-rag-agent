"""税率计算引擎单元测试

测试覆盖：
- 综合所得个税计算（工资/劳务/稿酬）
- 年终奖单独/并入计税对比
- 经营所得个税计算（个体户）
- 边界值：免征额、税率级距边界、负数收入
"""

import pytest
from services.tax_engine import (
    calculate_comprehensive_tax,
    calculate_business_tax,
)


class TestComprehensiveIncomeTax:
    """综合所得个税计算测试"""

    def test_below_threshold(self):
        """测试低于起征点（年收入60000元）"""
        result = calculate_comprehensive_tax(
            annual_income=50000,
            social_insurance=0,
            special_deductions=0,
        )
        assert result["tax"] == 0, "年收入5万应免税"
        assert result["taxable_income"] == 0
        assert result["effective_rate"] == 0

    def test_first_bracket(self):
        """测试第一档税率（3%）"""
        # 年收入96000，扣除60000，应纳税36000，税额 36000*3% = 1080
        result = calculate_comprehensive_income_tax(
            annual_income=96000,
            special_deductions=0,
            special_additional_deductions=0,
            other_deductions=0,
        )
        assert result["tax"] == 1080, "年收入9.6万个税应为1080元"
        assert result["taxable_income"] == 36000
        assert result["bracket"] == 1
        assert abs(result["effective_rate"] - 1.125) < 0.01  # 1080/96000 ≈ 1.125%

    def test_with_special_deductions(self):
        """测试专项扣除（五险一金）"""
        result = calculate_comprehensive_income_tax(
            annual_income=120000,
            special_deductions=12000,  # 五险一金1万2
            special_additional_deductions=0,
            other_deductions=0,
        )
        # 120000 - 60000 - 12000 = 48000 应纳税所得
        # 48000 * 10% - 2520 = 2280
        assert result["tax"] == 2280
        assert result["taxable_income"] == 48000

    def test_with_additional_deductions(self):
        """测试专项附加扣除（子女教育/房贷等）"""
        result = calculate_comprehensive_income_tax(
            annual_income=150000,
            special_deductions=15000,
            special_additional_deductions=24000,  # 子女教育12000 + 房贷12000
            other_deductions=0,
        )
        # 150000 - 60000 - 15000 - 24000 = 51000
        # 51000 * 10% - 2520 = 2580
        assert result["tax"] == 2580
        assert result["taxable_income"] == 51000

    def test_high_income(self):
        """测试高收入（最高档45%）"""
        result = calculate_comprehensive_income_tax(
            annual_income=1000000,
            special_deductions=0,
            special_additional_deductions=0,
            other_deductions=0,
        )
        # 1000000 - 60000 = 940000
        # 940000 * 45% - 181920 = 241080
        assert result["tax"] == 241080
        assert result["bracket"] == 7
        assert result["marginal_rate"] == 45

    def test_boundary_36000(self):
        """测试税率级距边界：36000元（3%→10%临界点）"""
        # 刚好36000，第一档
        result1 = calculate_comprehensive_income_tax(annual_income=96000)
        assert result1["bracket"] == 1
        assert result1["marginal_rate"] == 3

        # 超过1元，第二档
        result2 = calculate_comprehensive_income_tax(annual_income=96001)
        assert result2["bracket"] == 2
        assert result2["marginal_rate"] == 10

    def test_negative_income(self):
        """测试负收入（亏损）"""
        result = calculate_comprehensive_income_tax(
            annual_income=-10000,
            special_deductions=0,
            special_additional_deductions=0,
            other_deductions=0,
        )
        assert result["tax"] == 0
        assert result["taxable_income"] == 0


class TestYearEndBonusComparison:
    """年终奖计税对比测试"""

    def test_small_bonus(self):
        """测试小额年终奖（单独计税更优）"""
        result = calculate_year_end_bonus_comparison(
            annual_salary=100000,
            year_end_bonus=30000,
            special_deductions=12000,
            special_additional_deductions=0,
        )
        assert "separate" in result
        assert "combined" in result
        assert result["recommended"] in ["separate", "combined"]
        # 小额年终奖通常单独计税更优
        assert result["separate"]["total_tax"] <= result["combined"]["total_tax"]

    def test_large_bonus(self):
        """测试大额年终奖（并入可能更优）"""
        result = calculate_year_end_bonus_comparison(
            annual_salary=80000,
            year_end_bonus=200000,  # 年终奖远超工资
            special_deductions=10000,
            special_additional_deductions=12000,
        )
        # 大额年终奖可能触发高税率，并入后平均可能更优
        assert "separate" in result
        assert "combined" in result

    def test_zero_bonus(self):
        """测试零年终奖"""
        result = calculate_year_end_bonus_comparison(
            annual_salary=120000,
            year_end_bonus=0,
            special_deductions=12000,
        )
        assert result["separate"]["bonus_tax"] == 0
        assert result["separate"]["total_tax"] == result["combined"]["total_tax"]


class TestBusinessIncomeTax:
    """经营所得个税计算测试（个体户）"""

    def test_below_threshold(self):
        """测试低于起征点"""
        result = calculate_business_income_tax(
            annual_revenue=50000,
            annual_costs=10000,
            special_additional_deductions=0,
        )
        # 50000 - 10000 - 60000 = -20000（亏损）
        assert result["tax"] == 0
        assert result["taxable_income"] <= 0

    def test_first_bracket_5(self):
        """测试第一档税率（5%）"""
        result = calculate_business_income_tax(
            annual_revenue=100000,
            annual_costs=10000,
            special_additional_deductions=0,
        )
        # 100000 - 10000 - 60000 = 30000
        # 30000 * 5% = 1500
        assert result["tax"] == 1500
        assert result["bracket"] == 1
        assert result["marginal_rate"] == 5

    def test_with_deductions(self):
        """测试专项附加扣除"""
        result = calculate_business_income_tax(
            annual_revenue=200000,
            annual_costs=50000,
            special_additional_deductions=24000,
        )
        # 200000 - 50000 - 60000 - 24000 = 66000
        # 66000 * 10% - 1500 = 5100
        assert result["tax"] == 5100
        assert result["taxable_income"] == 66000

    def test_high_income_bracket(self):
        """测试高收入档（35%）"""
        result = calculate_business_income_tax(
            annual_revenue=1000000,
            annual_costs=100000,
            special_additional_deductions=0,
        )
        # 1000000 - 100000 - 60000 = 840000
        # 840000 * 35% - 65500 = 228500
        assert result["tax"] == 228500
        assert result["bracket"] == 5
        assert result["marginal_rate"] == 35

    def test_boundary_30000(self):
        """测试税率级距边界：30000元（5%→10%临界点）"""
        # 刚好30000
        result1 = calculate_business_income_tax(
            annual_revenue=90000, annual_costs=0
        )
        assert result1["bracket"] == 1

        # 超过1元
        result2 = calculate_business_income_tax(
            annual_revenue=90001, annual_costs=0
        )
        assert result2["bracket"] == 2


class TestEdgeCases:
    """边界情况与异常输入测试"""

    def test_zero_income(self):
        """测试零收入"""
        result = calculate_comprehensive_income_tax(annual_income=0)
        assert result["tax"] == 0

    def test_exact_threshold(self):
        """测试恰好60000免征额"""
        result = calculate_comprehensive_income_tax(annual_income=60000)
        assert result["tax"] == 0
        assert result["taxable_income"] == 0

    def test_large_deductions(self):
        """测试扣除额超过收入"""
        result = calculate_comprehensive_income_tax(
            annual_income=100000,
            special_deductions=50000,
            special_additional_deductions=60000,  # 扣除总和110000 > 收入
        )
        # 扣除后应为0，不应为负
        assert result["tax"] == 0
        assert result["taxable_income"] == 0

    def test_float_precision(self):
        """测试浮点数精度"""
        result = calculate_comprehensive_income_tax(annual_income=96000.99)
        # 确保结果为整数（元）或保留2位小数（分）
        assert isinstance(result["tax"], (int, float))
        if isinstance(result["tax"], float):
            assert round(result["tax"], 2) == result["tax"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
