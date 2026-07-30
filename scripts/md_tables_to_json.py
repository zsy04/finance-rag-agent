#!/usr/bin/env python3
"""
将税率表缺失清单.md 中的四张税率表转为 JSON，供 Agent 工具调用。
"""

import json
import re
from pathlib import Path


def parse_car_range(s):
    """解析 '60至360' 或 '300至540' 格式的范围"""
    m = re.match(r'(\d+)\s*至\s*(\d+)', s)
    if m:
        return {"low": int(m.group(1)), "high": int(m.group(2))}
    # "按照货车税额的50%计算" 等特殊情况
    return {"note": s}


def parse_rate_pct(s):
    """解析 '万分之零点五' 或 '千分之一' 等"""
    s = s.strip()
    # 百分比
    m = re.match(r'百\s*分\s*之\s*([\d.]+)', s)
    if m:
        return float(m.group(1)) / 100
    # 千分比
    m = re.match(r'千\s*分\s*之\s*([\d.]+)', s)
    if m:
        return float(m.group(1)) / 1000
    # 万分比
    m = re.match(r'万\s*分\s*之\s*([\d.]+)', s)
    if m:
        return float(m.group(1)) / 10000
    # 纯数字
    m = re.match(r'([\d.]+)\s*%?', s)
    if m:
        return float(m.group(1)) / 100
    return s


def build_json():
    data = {
        "tool_usage": {
            "description": "中国财税税率表，含个人所得税、车船税、印花税的税率/税额数据。用于税率计算器的精确查询。",
            "tables": {
                "personal_income_tax": "个人所得税综合所得 + 经营所得税率表",
                "vehicle_vessel_tax": "车船税税目税额表（按排量/吨位）",
                "stamp_tax": "印花税税目税率表（合同/产权转移/账簿/证券）",
            },
            "usage_examples": [
                "用户: 我月薪2万，个税多少？→ 查综合所得税率表，累进计算",
                "用户: 刚买了辆2.0L的车，车船税多少？→ 查车船税→乘用车→1.6-2.0L档",
                "用户: 签了个100万的购销合同，印花税多少？→ 查印花税→买卖合同→万分之三",
            ],
        },
        "tables": {},
    }

    # ── 1. 个人所得税 ──
    data["tables"]["personal_income_tax"] = {
        "description": "个人所得税税率表，含综合所得（7级）和经营所得（5级）两套税率",
        "exemption": 5000,  # 月免征额
        "annual_deduction": 60000,  # 年度基本减除费用
        "comprehensive": {
            "description": "综合所得适用（工资薪金、劳务报酬、稿酬、特许权使用费）",
            "type": "超额累进",
            "brackets": [
                {"level": 1, "income_range": "不超过36000元", "income_high": 36000, "rate": 0.03, "quick_deduction": 0},
                {"level": 2, "income_range": "36000-144000元", "income_low": 36000, "income_high": 144000, "rate": 0.10, "quick_deduction": 2520},
                {"level": 3, "income_range": "144000-300000元", "income_low": 144000, "income_high": 300000, "rate": 0.20, "quick_deduction": 16920},
                {"level": 4, "income_range": "300000-420000元", "income_low": 300000, "income_high": 420000, "rate": 0.25, "quick_deduction": 31920},
                {"level": 5, "income_range": "420000-660000元", "income_low": 420000, "income_high": 660000, "rate": 0.30, "quick_deduction": 52920},
                {"level": 6, "income_range": "660000-960000元", "income_low": 660000, "income_high": 960000, "rate": 0.35, "quick_deduction": 85920},
                {"level": 7, "income_range": "超过960000元", "income_low": 960000, "rate": 0.45, "quick_deduction": 181920},
            ],
            "formula": "应纳税额 = 应纳税所得额 × 税率 - 速算扣除数",
            "taxable_income_formula": "应纳税所得额 = 月度收入 - 5000元(免征额) - 专项扣除(三险一金) - 专项附加扣除 - 其他扣除",
        },
        "business": {
            "description": "经营所得适用（个体工商户、个人独资企业、合伙企业）",
            "type": "超额累进",
            "brackets": [
                {"level": 1, "income_range": "不超过30000元", "income_high": 30000, "rate": 0.05, "quick_deduction": 0},
                {"level": 2, "income_range": "30000-90000元", "income_low": 30000, "income_high": 90000, "rate": 0.10, "quick_deduction": 1500},
                {"level": 3, "income_range": "90000-300000元", "income_low": 90000, "income_high": 300000, "rate": 0.20, "quick_deduction": 10500},
                {"level": 4, "income_range": "300000-500000元", "income_low": 300000, "income_high": 500000, "rate": 0.30, "quick_deduction": 40500},
                {"level": 5, "income_range": "超过500000元", "income_low": 500000, "rate": 0.35, "quick_deduction": 65500},
            ],
            "formula": "应纳税额 = 应纳税所得额 × 税率 - 速算扣除数",
            "taxable_income_formula": "应纳税所得额 = 年收入总额 - 成本 - 费用 - 损失",
        },
    }

    # ── 2. 车船税 ──
    data["tables"]["vehicle_vessel_tax"] = {
        "description": "车船税税目税额表，各省在幅度内自定具体税额。计算器默认取中位数。",
        "note": "税额范围为全国指导幅度，具体以各省公布为准",
        "passenger_cars": [
            {"displacement": "1.0升（含）以下", "displacement_low": 0, "displacement_high": 1.0, "tax_range": {"low": 60, "high": 360}, "tax_mid": 210},
            {"displacement": "1.0-1.6升（含）", "displacement_low": 1.0, "displacement_high": 1.6, "tax_range": {"low": 300, "high": 540}, "tax_mid": 420},
            {"displacement": "1.6-2.0升（含）", "displacement_low": 1.6, "displacement_high": 2.0, "tax_range": {"low": 360, "high": 660}, "tax_mid": 510},
            {"displacement": "2.0-2.5升（含）", "displacement_low": 2.0, "displacement_high": 2.5, "tax_range": {"low": 660, "high": 1200}, "tax_mid": 930},
            {"displacement": "2.5-3.0升（含）", "displacement_low": 2.5, "displacement_high": 3.0, "tax_range": {"low": 1200, "high": 2400}, "tax_mid": 1800},
            {"displacement": "3.0-4.0升（含）", "displacement_low": 3.0, "displacement_high": 4.0, "tax_range": {"low": 2400, "high": 3600}, "tax_mid": 3000},
            {"displacement": "4.0升以上", "displacement_low": 4.0, "tax_range": {"low": 3600, "high": 5400}, "tax_mid": 4500},
        ],
        "commercial_vehicles": {
            "bus": {"description": "客车（核定载客≥9人，含电车）", "unit": "每辆", "tax_range": {"low": 480, "high": 1440}, "tax_mid": 960},
            "truck": {"description": "货车（含半挂牵引车、三轮汽车、低速载货车）", "unit": "整备质量每吨", "tax_range": {"low": 16, "high": 120}, "tax_mid": 68},
        },
        "trailer": {"description": "挂车", "unit": "整备质量每吨", "rate": "货车税额的50%"},
        "other_vehicles": {
            "special_work": {"description": "专业作业车（不含拖拉机）", "unit": "整备质量每吨", "tax_range": {"low": 16, "high": 120}, "tax_mid": 68},
            "wheeled_machinery": {"description": "轮式专用机械车（不含拖拉机）", "unit": "整备质量每吨", "tax_range": {"low": 16, "high": 120}, "tax_mid": 68},
        },
        "motorcycle": {"description": "摩托车", "unit": "每辆", "tax_range": {"low": 36, "high": 180}, "tax_mid": 108},
        "vessels": {
            "motor": {"description": "机动船舶", "unit": "净吨位每吨", "tax_range": {"low": 3, "high": 6}, "tax_mid": 4.5, "note": "拖船、非机动驳船按50%计算"},
            "yacht": {"description": "游艇", "unit": "艇身长度每米", "tax_range": {"low": 600, "high": 2000}, "tax_mid": 1300},
        },
    }

    # ── 3. 印花税 ──
    data["tables"]["stamp_tax"] = {
        "description": "印花税税目税率表（2022年7月1日起施行）",
        "contracts": [
            {"type": "借款合同", "basis": "借款金额", "rate": 0.00005, "rate_text": "万分之零点五", "note": "银行业金融机构与借款人（不含同业拆借）"},
            {"type": "融资租赁合同", "basis": "租金", "rate": 0.0003, "rate_text": "万分之三"},
            {"type": "买卖合同", "basis": "价款", "rate": 0.0003, "rate_text": "万分之三", "note": "动产买卖（不含个人书立）"},
            {"type": "承揽合同", "basis": "报酬", "rate": 0.0003, "rate_text": "万分之三"},
            {"type": "建设工程合同", "basis": "价款", "rate": 0.0003, "rate_text": "万分之三"},
            {"type": "运输合同", "basis": "运输费用", "rate": 0.0003, "rate_text": "万分之三", "note": "货运和多式联运（不含管道运输）"},
            {"type": "技术合同", "basis": "价款/报酬/使用费", "rate": 0.0003, "rate_text": "万分之三", "note": "不含专利权、专有技术使用权转让"},
            {"type": "租赁合同", "basis": "租金", "rate": 0.001, "rate_text": "千分之一"},
            {"type": "保管合同", "basis": "保管费", "rate": 0.001, "rate_text": "千分之一"},
            {"type": "仓储合同", "basis": "仓储费", "rate": 0.001, "rate_text": "千分之一"},
            {"type": "财产保险合同", "basis": "保险费", "rate": 0.001, "rate_text": "千分之一", "note": "不含再保险合同"},
        ],
        "property_transfer": [
            {"type": "土地使用权出让书据", "basis": "价款", "rate": 0.0005, "rate_text": "万分之五"},
            {"type": "土地使用权/房屋所有权转让书据", "basis": "价款", "rate": 0.0005, "rate_text": "万分之五", "note": "不含土地承包经营权和土地经营权转移"},
            {"type": "股权转让书据", "basis": "价款", "rate": 0.0005, "rate_text": "万分之五", "note": "不含证券交易印花税"},
            {"type": "商标/著作权/专利/专有技术使用权转让书据", "basis": "价款", "rate": 0.0003, "rate_text": "万分之三"},
        ],
        "business_books": [
            {"type": "营业账簿", "basis": "实收资本+资本公积合计金额", "rate": 0.00025, "rate_text": "万分之二点五"},
        ],
        "securities": [
            {"type": "证券交易", "basis": "成交金额", "rate": 0.001, "rate_text": "千分之一", "note": "对出让方征收"},
        ],
    }

    return data


def main():
    data = build_json()
    out_path = Path("F:/lest/rag-data/processed/national/rates/tax_rate_tables.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已生成 {out_path}")
    print(f"   个人所得税: {len(data['tables']['personal_income_tax']['comprehensive']['brackets'])} + {len(data['tables']['personal_income_tax']['business']['brackets'])} 级")
    print(f"   车船税: 乘用车{len(data['tables']['vehicle_vessel_tax']['passenger_cars'])}档 + 商用/挂车/摩托/船舶")
    print(f"   印花税: 合同{len(data['tables']['stamp_tax']['contracts'])}类 + 产权转移{len(data['tables']['stamp_tax']['property_transfer'])}类")


if __name__ == "__main__":
    main()
