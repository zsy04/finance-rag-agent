"""税率计算引擎单元测试

测试覆盖：
- 综合所得个税（工资薪金，含社保/专项附加扣除）
- 年终奖单独计税 + 单独/并入对比
- 经营所得个税（个体户，五级超额累进）
- 边界值：免征额、税率级距临界点、负收入
- 专项附加扣除上限校验
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from services.tax_engine import (
    calculate_bonus_tax_separate,
    calculate_business_tax,
    calculate_comprehensive_tax,
    compare_bonus_methods,
    validate_special_deductions,
)


class TestComprehensiveIncomeTax:
    """综合所得个税计算测试"""

    def test_below_threshold(self):
        """年收入低于 6 万基本减除费用，应免税"""
        result = calculate_comprehensive_tax(annual_income=50000)
        assert result["tax_amount"] == 0
        assert result["taxable_income"] == 0
        assert result["level"] == 0

    def test_first_bracket(self):
        """年收入 9.6 万：应纳税所得 36000，税额 1080（3%）"""
        result = calculate_comprehensive_tax(annual_income=96000)
        assert result["taxable_income"] == 36000
        assert result["tax_amount"] == 1080
        assert result["rate"] == "3%"
        assert result["level"] == 1

    def test_with_deductions(self):
        """社保 + 专项附加扣除参与公式：10万-6万-1万-1.2万=1.8万，税 540"""
        result = calculate_comprehensive_tax(
            annual_income=100000, social_insurance=10000, special_deductions=12000
        )
        assert result["taxable_income"] == 18000
        assert result["tax_amount"] == 540

    def test_second_bracket_upper_bound(self):
        """10% 档上界：应纳税所得 14.4 万 → 144000*10%-2520 = 11880"""
        result = calculate_comprehensive_tax(annual_income=204000)
        assert result["taxable_income"] == 144000
        assert result["tax_amount"] == 11880
        assert result["level"] == 2

    def test_boundary_36000(self):
        """级距临界点：36000 适用 3%，36001 跳 10%，速算扣除保证税额连续"""
        low = calculate_comprehensive_tax(annual_income=96000)    # taxable 36000
        high = calculate_comprehensive_tax(annual_income=96001)   # taxable 36001
        assert low["level"] == 1
        assert high["level"] == 2
        # 税额差应约为 36001*0.1-2520 - 1080 = 0.1 元
        assert high["tax_amount"] - low["tax_amount"] == pytest.approx(0.1, abs=0.01)

    def test_top_bracket(self):
        """最高档 45%：taxable 104 万 → 1040000*45%-181920 = 286080"""
        result = calculate_comprehensive_tax(annual_income=1100000)
        assert result["taxable_income"] == 1040000
        assert result["tax_amount"] == 286080
        assert result["level"] == 7

    def test_negative_income(self):
        """负收入不产生负税额"""
        result = calculate_comprehensive_tax(annual_income=-10000)
        assert result["tax_amount"] == 0
        assert result["taxable_income"] == 0

    def test_deductions_exceed_income(self):
        """扣除额超过收入：应纳税所得额归零，不为负"""
        result = calculate_comprehensive_tax(
            annual_income=100000, social_insurance=50000, special_deductions=60000
        )
        assert result["tax_amount"] == 0
        assert result["taxable_income"] == 0


class TestBonusTaxSeparate:
    """年终奖单独计税测试"""

    def test_level1(self):
        """年终奖 36000：月均 3000 → 3% 档，税 1080"""
        result = calculate_bonus_tax_separate(36000)
        assert result["monthly_equivalent"] == 3000
        assert result["tax_amount"] == 1080
        assert result["rate"] == "3%"

    def test_boundary_trap(self):
        """年终奖临界陷阱：36001 比 36000 多 1 元，税额跳增约 2310 元"""
        low = calculate_bonus_tax_separate(36000)
        high = calculate_bonus_tax_separate(36001)
        # 36001*10%-210 = 3390.1，比 1080 多 2310.1
        assert high["tax_amount"] - low["tax_amount"] == pytest.approx(2310.1, abs=0.01)

    def test_zero_bonus(self):
        """零年终奖税额为 0"""
        assert calculate_bonus_tax_separate(0)["tax_amount"] == 0


class TestBonusMethodComparison:
    """年终奖计税方式对比测试"""

    def test_separate_better(self):
        """常规情形：单独计税更优（9.6 万工资 + 3.6 万年终奖，省 2520 元）"""
        result = compare_bonus_methods(annual_income=96000, bonus=36000)
        # 单独：工资 1080 + 年终奖 1080 = 2160；并入：72000*10%-2520 = 4680
        assert result["separate"]["total"] == 2160
        assert result["merged"]["total"] == 4680
        assert result["recommendation"] == "单独计税"
        assert result["saving"] == 2520

    def test_merged_better(self):
        """低工资高年终奖：并入综合所得更优"""
        result = compare_bonus_methods(annual_income=30000, bonus=100000)
        # 单独：工资 0 + 年终奖 9790；并入：70000*10%-2520 = 4480
        assert result["merged"]["total"] == 4480
        assert result["recommendation"] == "并入综合所得"
        assert result["saving"] == 5310

    def test_zero_bonus_equal(self):
        """零年终奖：两种方式税额一致"""
        result = compare_bonus_methods(annual_income=120000, bonus=0)
        assert result["separate"]["total"] == result["merged"]["total"]


class TestBusinessIncomeTax:
    """经营所得个税计算测试（个体户，五级超额累进）

    注意：引擎约定入参为年净所得（收入-成本-费用-损失之后），不再重复扣除 6 万。
    """

    def test_first_bracket(self):
        """净所得 30000：5% 档，税 1500"""
        result = calculate_business_tax(30000)
        assert result["tax_amount"] == 1500
        assert result["level"] == 1

    def test_second_bracket(self):
        """净所得 90000：90000*10%-1500 = 7500"""
        result = calculate_business_tax(90000)
        assert result["tax_amount"] == 7500
        assert result["level"] == 2

    def test_boundary_30000(self):
        """级距临界点：30000 适用 5%，30001 跳 10%，税额连续"""
        low = calculate_business_tax(30000)
        high = calculate_business_tax(30001)
        assert low["level"] == 1
        assert high["level"] == 2
        assert high["tax_amount"] - low["tax_amount"] == pytest.approx(0.1, abs=0.01)

    def test_top_bracket(self):
        """最高档 35%：840000*35%-65500 = 228500"""
        result = calculate_business_tax(840000)
        assert result["tax_amount"] == 228500
        assert result["level"] == 5

    def test_zero_and_negative(self):
        """零/负净所得不产生负税额"""
        assert calculate_business_tax(0)["tax_amount"] == 0
        assert calculate_business_tax(-20000)["tax_amount"] == 0


class TestSpecialDeductionValidation:
    """专项附加扣除上限校验测试"""

    def test_over_limit_rejected(self):
        """住房租金月额 1 万超过 1500 上限，应拦截"""
        msg = validate_special_deductions(housing_rent=10000)
        assert msg is not None
        assert "1500" in msg

    def test_at_limit_passes(self):
        """恰好等于上限应放行"""
        assert validate_special_deductions(housing_rent=1500) is None

    def test_multiple_fields(self):
        """子女教育超限拦截 / 赡养老人临界放行"""
        assert validate_special_deductions(children_edu=2500) is not None
        assert validate_special_deductions(elderly_support=3000) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
