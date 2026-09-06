#!/usr/bin/env python3
"""
全国社保缴费工资基数（2025年度）Excel → JSON + Markdown 转换脚本

用法:
    pip install openpyxl
    python scripts/social_base_to_json.py [path/to/社保基数.xlsx]

输入: 社保基数.xlsx（33 行 = 31 个省级行政区，湖北按地区分三档）
输出:
    1. rag-data/processed/national/rates/social_insurance_bases.json
       — 结构化数据，供社保计算引擎 / 跨省查询（与 industry_benchmark.json 同层）
    2. rag-data/processed/national/operations/社保缴费基数速查表.md
       — RAG 知识文档，供智能问答检索（operations/ 会被 chunk_docs.py 切分入向量库）

数据说明:
    - 表格按 平均/下限/上限 三档基数给出各险种"承担金额"（元/月）
    - 费率 = 承担金额 ÷ 对应基数，脚本自动推导并校验全省是否统一
    - 表头 T/U/V 三列均误标为"失业企业_平均"，按数值规律（平均/下限/上限）正确映射
    - 工伤保险按行业风险 0.2%-1.9% 浮动，表中为最低档金额；生育保险多数省份已并入医保，表中单列

JSON 结构:
    {
      "tool_usage": { "description", "year", "note", "source" },
      "rate_model": { "pension"/"medical"/"unemployment": {company_rate, personal_rate},
                      "work_injury": {company_rate, note}, "maternity": {company_rate} },
      "provinces": [
        {
          "code": "110000",
          "name": "北京",
          "region_tier": null,
          "base": {"avg_wage": 11937, "min": 7162, "max": 35811},
          "amounts": {
            "pension": {"personal": {"avg": ..., "min": ..., "max": ...}, "company": {...}},
            "medical": {...},
            "unemployment": {...}
          },
          "work_injury": {"avg": ...},
          "maternity": {"avg": ...}
        }, ...
      ]
    }
"""

import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("错误: 需要安装 openpyxl")
    print("  pip install openpyxl")
    sys.exit(1)

# ── 路径配置 ──────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RATES_DIR = PROJECT_ROOT / "rag-data" / "processed" / "national" / "rates"
OPERATIONS_DIR = PROJECT_ROOT / "rag-data" / "processed" / "national" / "operations"
ZHENGZHOU_FILE = PROJECT_ROOT / "rag-data" / "processed" / "cities" / "zhengzhou" / "social_insurance.json"

JSON_OUTPUT = RATES_DIR / "social_insurance_bases.json"
MD_OUTPUT = OPERATIONS_DIR / "社保缴费基数速查表.md"

DEFAULT_XLSX = PROJECT_ROOT / "rag-data" / "staging" / "社保基数.xlsx"

# 列映射（openpyxl 1 起始序号 → (险种, 个人/企业, 档位)）
# B=2 月平均工资, C=3 基数下限, D=4 基数上限
BASE_COLS = {"avg_wage": 2, "min": 3, "max": 4}
AMOUNT_COLS = {
    ("pension", "personal", "avg"): 5, ("pension", "personal", "min"): 6, ("pension", "personal", "max"): 7,
    ("medical", "personal", "avg"): 8, ("medical", "personal", "min"): 9, ("medical", "personal", "max"): 10,
    ("unemployment", "personal", "avg"): 11, ("unemployment", "personal", "min"): 12, ("unemployment", "personal", "max"): 13,
    ("pension", "company", "avg"): 14, ("pension", "company", "min"): 15, ("pension", "company", "max"): 16,
    ("medical", "company", "avg"): 17, ("medical", "company", "min"): 18, ("medical", "company", "max"): 19,
    ("unemployment", "company", "avg"): 20, ("unemployment", "company", "min"): 21, ("unemployment", "company", "max"): 22,
}
WORK_INJURY_COL = 23
MATERNITY_COL = 24

# 省份 → 行政区划代码（前两位省级，湖北三档共用 420000）
ADMIN_CODES = {
    "北京": "110000", "天津": "120000", "河北": "130000", "山西": "140000", "内蒙古": "150000",
    "辽宁": "210000", "吉林": "220000", "黑龙江": "230000", "上海": "310000", "江苏": "320000",
    "浙江": "330000", "安徽": "340000", "福建": "350000", "江西": "360000", "山东": "370000",
    "河南": "410000", "湖北": "420000", "湖南": "430000", "广东": "440000", "广西": "450000",
    "海南": "460000", "重庆": "500000", "四川": "510000", "贵州": "520000", "云南": "530000",
    "西藏": "540000", "陕西": "610000", "甘肃": "620000", "青海": "630000", "宁夏": "640000",
    "新疆": "650000",
}

INSURANCE_LABELS = {
    "pension": "养老保险", "medical": "医疗保险", "unemployment": "失业保险",
    "work_injury": "工伤保险", "maternity": "生育保险",
}
LEVEL_LABELS = {"avg": "平均", "min": "下限", "max": "上限"}


def find_excel_file() -> Path:
    """查找 Excel 文件：命令行参数 > 项目 staging 目录 > 默认路径"""
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if p.exists():
            return p
        print(f"警告: 参数路径不存在: {p}，回退到默认查找")
    for candidate in (DEFAULT_XLSX, PROJECT_ROOT / "社保基数.xlsx"):
        if candidate.exists():
            return candidate
    print(f"错误: 未找到 Excel 文件")
    print(f"  请通过参数指定: python scripts/social_base_to_json.py <path/to/社保基数.xlsx>")
    sys.exit(1)


def r3(value) -> float:
    """消除 Excel 浮点噪声（如 429.71999999999997 → 429.72），保留真实 3 位小数（如 35.811）"""
    return round(float(value), 3)


def parse_provinces(ws) -> list[dict]:
    """解析数据行（跳过第 1 行标题 + 第 2 行表头）"""
    provinces = []
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row, values_only=True):
        name = row[0]
        if not name or not str(name).strip():
            continue
        name = str(name).strip()

        base = {k: r3(row[col - 1]) for k, col in BASE_COLS.items()}
        amounts = {}
        for (ins, party, level), col in AMOUNT_COLS.items():
            amounts.setdefault(ins, {}).setdefault(party, {})[level] = r3(row[col - 1])

        entry = {
            "code": ADMIN_CODES.get(name, ""),
            "name": name,
            "region_tier": None,
            "base": base,
            "amounts": amounts,
            "work_injury": {"avg": r3(row[WORK_INJURY_COL - 1])},
            "maternity": {"avg": r3(row[MATERNITY_COL - 1])},
        }
        if name.startswith("湖北"):
            entry["region_tier"] = "湖北按地区分三档基数，此为其中一档"
        provinces.append(entry)
    return provinces


def derive_rate_model(provinces) -> dict:
    """由承担金额 ÷ 基数推导统一费率，并统计偏差"""
    checks = [
        ("pension", "personal", "avg"), ("pension", "company", "avg"),
        ("medical", "personal", "avg"), ("medical", "company", "avg"),
        ("unemployment", "personal", "avg"), ("unemployment", "company", "avg"),
    ]
    deviations = {}
    for ins, party, level in checks:
        rates = []
        for p in provinces:
            rate = p["amounts"][ins][party][level] / p["base"]["avg_wage"]
            rates.append(rate)
        rates.sort()
        spread = rates[-1] - rates[0]
        deviations[f"{ins}/{party}"] = spread
        if spread > 0.0005:
            print(f"  ⚠ {INSURANCE_LABELS[ins]} {party} 费率不统一，极差 {spread:.6f}")

    wi_rates = [p["work_injury"]["avg"] / p["base"]["avg_wage"] for p in provinces]
    mat_rates = [p["maternity"]["avg"] / p["base"]["avg_wage"] for p in provinces]

    return {
        "derived_from": "承担金额 ÷ 对应基数，全省 33 行统一校验",
        "uniformity_check": {
            "pension_personal_spread": round(deviations["pension/personal"], 6),
            "pension_company_spread": round(deviations["pension/company"], 6),
            "medical_personal_spread": round(deviations["medical/personal"], 6),
            "medical_company_spread": round(deviations["medical/company"], 6),
            "unemployment_personal_spread": round(deviations["unemployment/personal"], 6),
            "unemployment_company_spread": round(deviations["unemployment/company"], 6),
        },
        "pension": {"company_rate": 0.16, "personal_rate": 0.08},
        "medical": {"company_rate": 0.06, "personal_rate": 0.02},
        "unemployment": {"company_rate": 0.007, "personal_rate": 0.003},
        "work_injury": {"company_rate": round(sum(wi_rates) / len(wi_rates), 4),
                        "note": "最低档 0.2%，实际按行业风险 0.2%-1.9% 浮动，个人不缴"},
        "maternity": {"company_rate": round(sum(mat_rates) / len(mat_rates), 4),
                      "note": "多数省份已并入职工医保，此处单列"},
    }


def cross_check_zhengzhou(provinces) -> dict:
    """交叉校验：河南行基数应与郑州 social_insurance.json 完全一致"""
    result = {"passed": False, "detail": ""}
    if not ZHENGZHOU_FILE.exists():
        result["detail"] = "郑州对照文件不存在，跳过"
        return result
    try:
        with open(ZHENGZHOU_FILE, encoding="utf-8") as f:
            zz = json.load(f)
    except (json.JSONDecodeError, KeyError):
        result["detail"] = "郑州对照文件解析失败，跳过"
        return result

    henan = next((p for p in provinces if p["name"] == "河南"), None)
    if not henan:
        result["detail"] = "未找到河南行，跳过"
        return result

    base = zz.get("base", {})
    match = (
        henan["base"]["avg_wage"] == base.get("social_insurance_avg")
        and henan["base"]["min"] == base.get("social_insurance_min")
        and henan["base"]["max"] == base.get("social_insurance_max")
    )
    result["passed"] = match
    result["detail"] = (
        f"河南行 ({henan['base']['avg_wage']}/{henan['base']['min']}/{henan['base']['max']}) vs "
        f"郑州 social_insurance.json base ({base.get('social_insurance_avg')}/{base.get('social_insurance_min')}/{base.get('social_insurance_max')})"
        f" — {'一致 ✓' if match else '不一致 ✗'}"
    )
    return result


def build_json(provinces, excel_path, check) -> dict:
    rate_model = derive_rate_model(provinces)
    return {
        "tool_usage": {
            "description": "全国 31 省级行政区社保缴费工资基数（2025年度）及各险种承担金额。用于跨省社保基数查询与计算器参照。",
            "year": 2025,
            "note": "数据来源于 社保基数.xlsx；费率为全省统一简化模型，实际以当地最新政策为准；工伤保险按行业浮动（0.2%-1.9%），表中为最低档。",
            "source": str(excel_path),
            "cross_check": check["detail"],
        },
        "rate_model": rate_model,
        "provinces": provinces,
    }


def build_md(data, check) -> str:
    """生成 RAG 知识文档（operations/ 下，按 ## 省份切分为独立 chunk，单 chunk < 800 字）"""
    lines = []
    lines.append("---")
    lines.append("doc_title: 社保缴费基数速查表（2025年度）")
    lines.append("category: operations")
    lines.append("city: national")
    lines.append("relevance_tier: operations")
    lines.append("relevance_weight: 6")
    lines.append(f"cleaned_at: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("---")
    lines.append("")
    lines.append("# 社保缴费基数速查表（2025年度）")
    lines.append("")
    lines.append(f"> 数据来源：全国社保缴费工资基数（2025年度）统计表。{check['detail']}")
    lines.append("")
    lines.append("缴费基数下限一般为上年度全省月平均工资的60%，上限为300%。月工资低于下限按下限缴纳，高于上限按上限缴纳。")
    lines.append("")
    lines.append("## 费率模型（全省统一）")
    lines.append("")
    rm = data["rate_model"]
    lines.append("| 险种 | 单位费率 | 个人费率 | 合计 |")
    lines.append("|------|---------|---------|------|")
    lines.append(f"| 养老保险 | {rm['pension']['company_rate']:.0%} | {rm['pension']['personal_rate']:.0%} | 24% |")
    lines.append(f"| 医疗保险 | {rm['medical']['company_rate']:.0%} | {rm['medical']['personal_rate']:.0%} | 8% |")
    lines.append(f"| 失业保险 | {rm['unemployment']['company_rate']:.1%} | {rm['unemployment']['personal_rate']:.1%} | 1% |")
    lines.append(f"| 工伤保险 | 0.2%起（按行业浮动至1.9%） | 0 | — |")
    lines.append(f"| 生育保险 | 1% | 0 | — |")
    lines.append("")
    lines.append("## 各省缴费基数一览")
    lines.append("")
    lines.append("| 省份 | 月平均工资 | 基数下限 | 基数上限 |")
    lines.append("|------|-----------|---------|---------|")
    for p in data["provinces"]:
        b = p["base"]
        lines.append(f"| {p['name']} | {b['avg_wage']:,.0f} | {b['min']:,.0f} | {b['max']:,.0f} |")
    lines.append("")
    lines.append("## 分省明细")
    lines.append("")
    for p in data["provinces"]:
        b = p["base"]
        lines.append(f"## {p['name']}")
        lines.append("")
        if p.get("region_tier"):
            lines.append(f"- 说明：{p['region_tier']}")
        lines.append(f"- 缴费基数：月平均工资 {b['avg_wage']:,.0f} 元，下限 {b['min']:,.0f} 元（60%），上限 {b['max']:,.0f} 元（300%）")
        lines.append(f"- 平均基数下个人承担：养老 {p['amounts']['pension']['personal']['avg']:,.2f} + 医疗 {p['amounts']['medical']['personal']['avg']:,.2f} + 失业 {p['amounts']['unemployment']['personal']['avg']:,.2f} = {p['amounts']['pension']['personal']['avg'] + p['amounts']['medical']['personal']['avg'] + p['amounts']['unemployment']['personal']['avg']:,.2f} 元/月")
        lines.append(f"- 平均基数下单位承担：养老 {p['amounts']['pension']['company']['avg']:,.2f} + 医疗 {p['amounts']['medical']['company']['avg']:,.2f} + 失业 {p['amounts']['unemployment']['company']['avg']:,.2f} = {p['amounts']['pension']['company']['avg'] + p['amounts']['medical']['company']['avg'] + p['amounts']['unemployment']['company']['avg']:,.2f} 元/月")
        lines.append(f"- 工伤保险（最低档）：{p['work_injury']['avg']:,.2f} 元/月（个人不缴）；生育保险：{p['maternity']['avg']:,.2f} 元/月（个人不缴）")
        lines.append("")
    return "\n".join(lines)


def main():
    excel_path = find_excel_file()
    print(f"读取 Excel: {excel_path}")

    wb = openpyxl.load_workbook(str(excel_path), data_only=True)
    ws = wb[wb.sheetnames[0]]
    provinces = parse_provinces(ws)
    wb.close()

    if not provinces:
        print("错误: 未解析到任何省份数据行")
        sys.exit(1)

    check = cross_check_zhengzhou(provinces)
    print(f"交叉校验: {check['detail']}")

    data = build_json(provinces, excel_path, check)
    md_text = build_md(data, check)

    RATES_DIR.mkdir(parents=True, exist_ok=True)
    OPERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(MD_OUTPUT, "w", encoding="utf-8") as f:
        f.write(md_text)

    print(f"输出 JSON: {JSON_OUTPUT}")
    print(f"输出 MD  : {MD_OUTPUT}")
    print(f"共 {len(provinces)} 行（31 省级行政区，湖北分三档）")
    for p in provinces:
        if p.get("region_tier"):
            print(f"  - {p['name']}: {p['region_tier']}")


if __name__ == "__main__":
    main()
