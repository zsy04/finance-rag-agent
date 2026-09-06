"""社保 + 公积金计算引擎单元测试（郑州 2025 年度标准）

测试覆盖：
- 职工五险（基数 clamp + 个人/单位费率）
- 住房公积金（比例 5%-12%，基数上下限）
- 灵活就业（养老 4 档基数 + 医疗 + 公积金月缴上下限）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from services.social_engine import (
    calculate_employee_social,
    calculate_flexible_social,
    calculate_housing_fund,
)


class TestEmployeeSocial:
    """职工五险测试"""

    def test_personal_part_at_average_base(self):
        """按社平基数 6385：个人 10.3%（养老8% + 医疗2% + 失业0.3%）"""
        result = calculate_employee_social(6385)
        assert result["base"] == 6385
        assert result["total_personal"] == pytest.approx(6385 * 0.103, abs=0.05)
        # 工伤/生育个人不缴
        assert result["breakdown"]["工伤保险"]["personal"] == 0
        assert result["breakdown"]["生育保险"]["personal"] == 0

    def test_company_part(self):
        """单位部分：养老16% + 医疗8% + 生育1%；工伤数据为 null，引擎默认取 1%"""
        result = calculate_employee_social(6385)
        b = result["breakdown"]
        assert b["养老保险"]["company"] == pytest.approx(6385 * 0.16, abs=0.01)
        assert b["医疗保险"]["company"] == pytest.approx(6385 * 0.08, abs=0.01)
        assert b["工伤保险"]["rate_company"] == 0.01
        assert result["total_company"] > result["total_personal"]

    def test_base_clamp_low(self):
        """工资低于基数下限 3831，按下限缴纳"""
        result = calculate_employee_social(2000)
        assert result["base"] == 3831

    def test_base_clamp_high(self):
        """工资高于基数上限 19155，按上限缴纳"""
        result = calculate_employee_social(50000)
        assert result["base"] == 19155

    def test_breakdown_completeness(self):
        """五险分项齐全，各项基数一致"""
        result = calculate_employee_social(8000)
        assert set(result["breakdown"].keys()) == {
            "养老保险", "医疗保险", "失业保险", "工伤保险", "生育保险"
        }
        assert all(item["base"] == 8000 for item in result["breakdown"].values())


class TestHousingFund:
    """住房公积金测试"""

    def test_default_ratio_12(self):
        """默认 12% 比例：6385*0.12 = 766.2，单位个人等额"""
        result = calculate_housing_fund(6385)
        assert result["base"] == 6385
        assert result["ratio"] == 0.12
        assert result["personal"] == pytest.approx(766.2, abs=0.01)
        assert result["company"] == result["personal"]

    def test_ratio_5(self):
        """最低比例 5%：6385*0.05 = 319.25"""
        result = calculate_housing_fund(6385, ratio=0.05)
        assert result["personal"] == pytest.approx(319.25, abs=0.01)

    def test_base_clamp(self):
        """公积金基数上下限：下限 2100 / 上限 27520"""
        assert calculate_housing_fund(1000)["base"] == 2100
        assert calculate_housing_fund(30000)["base"] == 27520


class TestFlexibleSocial:
    """灵活就业社保测试"""

    def test_level_100(self):
        """100% 档：养老 6385*20% = 1277，医疗 5108*10% = 510.8"""
        result = calculate_flexible_social(base_level=1)
        b = result["breakdown"]
        assert b["养老保险"]["amount"] == 1277.0
        assert b["医疗保险"]["amount"] == 510.8
        # 公积金 6385*20% = 1277，介于月缴上下限 580-2894 之间
        assert 580 <= b["住房公积金"]["amount"] <= 2894
        # 合计 = 三项之和
        total = sum(v["amount"] for v in b.values())
        assert result["total_monthly"] == pytest.approx(total, abs=0.01)

    def test_level_60(self):
        """60% 下限档：养老 3831*20% = 766.2"""
        result = calculate_flexible_social(base_level=0)
        assert result["breakdown"]["养老保险"]["amount"] == 766.2

    def test_level_300_housing_clamp(self):
        """300% 上限档：公积金 19155*20% = 3831 超月缴上限，应 clamp 到 2894"""
        result = calculate_flexible_social(base_level=3)
        assert result["breakdown"]["住房公积金"]["amount"] == 2894


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
