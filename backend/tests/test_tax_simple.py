"""税率计算引擎单元测试（简化版）

测试覆盖：
- 综合所得个税基本计算
- 边界值验证
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from services.tax_engine import calculate_comprehensive_tax, calculate_business_tax


class TestComprehensiveIncomeTax:
    """综合所得个税计算测试"""

    def test_below_threshold(self):
        """测试低于起征点（年收入60000元）"""
        result = calculate_comprehensive_tax(
            annual_income=50000,
            social_insurance=0,
            special_deductions=0,
        )
        assert result["tax_amount"] == 0, "年收入5万应免税"
        assert result["taxable_income"] == 0

    def test_first_bracket(self):
        """测试第一档税率（3%）"""
        # 年收入96000，扣除60000，应纳税36000，税额 36000*3% = 1080
        result = calculate_comprehensive_tax(
            annual_income=96000,
            social_insurance=0,
            special_deductions=0,
        )
        assert result["tax_amount"] == 1080, "年收入9.6万个税应为1080元"
        assert result["taxable_income"] == 36000

    def test_with_deductions(self):
        """测试有扣除项"""
        result = calculate_comprehensive_tax(
            annual_income=120000,
            social_insurance=12000,
            special_deductions=12000,
        )
        # 120000 - 60000 - 12000 - 12000 = 36000
        # 36000 * 3% = 1080
        assert result["tax_amount"] == 1080
        assert result["taxable_income"] == 36000

    def test_zero_income(self):
        """测试零收入"""
        result = calculate_comprehensive_tax(
            annual_income=0,
            social_insurance=0,
            special_deductions=0,
        )
        assert result["tax_amount"] == 0


class TestBusinessIncomeTax:
    """经营所得个税计算测试"""

    def test_below_threshold(self):
        """测试低于起征点"""
        result = calculate_business_tax(
            annual_revenue=50000,
            annual_costs=10000,
            special_deductions=0,
        )
        # 50000 - 10000 - 60000 = -20000（亏损）
        assert result["tax_amount"] == 0

    def test_first_bracket(self):
        """测试第一档税率（5%）"""
        result = calculate_business_tax(
            annual_revenue=100000,
            annual_costs=10000,
            special_deductions=0,
        )
        # 100000 - 10000 - 60000 = 30000
        # 30000 * 5% = 1500
        assert result["tax_amount"] == 1500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
