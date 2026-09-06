#!/usr/bin/env python3
"""
元数据补全 + 相关性分层（一次性处理）
两件事：
1. 为空 source_url 的文件填入 fgk.chinatax.gov.cn（标记来源域）
2. 按四层权重写入 YAML relevance_tier 字段：
   - tax_law (税法本体) → 权重 10
   - tax_regulation (条例/实施细则/管理办法) → 权重 8  
   - qa_corpus (Q&A 问答) → 权重 6
   - general_law (关联法律法规) → 权重 3
"""

import re
import sys
import yaml
from pathlib import Path

# ── 文件分类规则 ─────────────────────────────────────────

# 税法本体：以"法"结尾的核心税种法律
TAX_LAW_NAMES = {
    "个人所得税法", "企业所得税法", "增值税法", "契税法", "印花税法",
    "关税法", "车船税法", "车辆购置税法", "船舶吨税法", "烟叶税法",
    "耕地占用税法", "城市维护建设税法", "环境保护税法", "资源税法",
}

# 条例/实施细则/管理办法/通知/办法
TAX_REGULATION_PATTERNS = [
    r"实施条例", r"实施细则",
    r"管理办法", r"暂行办法", r"试行办法", r"公告办法",
    r"计税办法", r"操作办法", r"征收管理办法",
    r"汇算清缴管理办法",
    r"关于.*的通知", r"关于.*的公告", r"关于.*的决定",
    r"关于.*的补充通知",
    r"条例$", r"办法$",
]

# 关联法律法规（不是税法本身，但与税收征管相关）
GENERAL_LAW_NAMES = {
    "民事诉讼法", "刑事诉讼法", "行政处罚法", "行政强制法",
    "企业破产法", "会计法", "劳动合同法", "合伙企业法",
    "电子商务法", "社会保险法", "海关法", "环境保护法",
    "矿产资源法", "价格法", "城市房地产管理法",
}

def classify_file(filename, category, doc_title):
    """根据文件名和类别判断层级"""
    # 去掉 .md 后缀用于模式匹配
    name_no_ext = filename.replace(".md", "")
    
    # QA 问答单独分类
    if category == "qa_corpus":
        return "qa_corpus", 6
    
    # 先检查是否是关联法律法规
    for name in GENERAL_LAW_NAMES:
        if name in name_no_ext or name in (doc_title or ""):
            return "general_law", 3
    
    # 检查是否税法本体
    for name in TAX_LAW_NAMES:
        if name in name_no_ext or name in (doc_title or ""):
            # 排除：个人所得税法实施条例等
            for pat in TAX_REGULATION_PATTERNS:
                if re.search(pat, name_no_ext) or re.search(pat, doc_title or ""):
                    return "tax_regulation", 8
            return "tax_law", 10
    
    # 检查是否条例/细则
    for pat in TAX_REGULATION_PATTERNS:
        if re.search(pat, name_no_ext) or re.search(pat, doc_title or ""):
            return "tax_regulation", 8
    
    # 默认
    return "tax_law", 10


def parse_frontmatter(text):
    """提取 YAML frontmatter"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, [], 0
    
    end_idx = None
    for i in range(1, min(len(lines), 30)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    
    if end_idx is None:
        return {}, lines, 0
    
    yaml_text = "\n".join(lines[1:end_idx])
    try:
        meta = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        meta = {}, lines, 0
    
    body_lines = lines[end_idx + 1:]
    return meta, body_lines, end_idx + 1


def process_file(filepath):
    """处理单个文件：补全元数据 + 添加相关性层级"""
    with open(filepath, "r", encoding="utf-8") as f:
        original = f.read()
    
    meta, body_lines, fm_end = parse_frontmatter(original)
    
    if not meta:
        return False, "no frontmatter"
    
    category = meta.get("category", "")
    doc_title = meta.get("doc_title", "")
    filename = filepath.name
    
    changes = []
    
    # 1. 补全 source_url
    source_url = meta.get("source_url", "")
    if not source_url or source_url == "":
        if category == "tax_law":
            meta["source_url"] = "fgk.chinatax.gov.cn"
            changes.append("source_url → fgk.chinatax.gov.cn")
    
    # 2. 添加相关性层级
    tier_name, tier_weight = classify_file(filename, category, doc_title)
    meta["relevance_tier"] = tier_name
    meta["relevance_weight"] = tier_weight
    changes.append(f"tier={tier_name}, weight={tier_weight}")
    
    # 重新组装文件
    result_lines = ["---"]
    
    # 字段排序：source_url, doc_number, effective_from, expiry_date, module, category, city, 
    #           doc_title, relevance_tier, relevance_weight, cleaned_at
    field_order = [
        "source_url", "doc_number", "effective_from", "expiry_date",
        "module", "category", "city", "doc_title",
        "relevance_tier", "relevance_weight", "cleaned_at"
    ]
    
    ordered = {}
    # 先按顺序插入
    for key in field_order:
        if key in meta:
            ordered[key] = meta[key]
    # 再插入任何未知字段
    for key, value in meta.items():
        if key not in ordered:
            ordered[key] = value
    
    for key, value in ordered.items():
        if value is None:
            pass  # 不写入 None 值
        elif value == "" or (isinstance(value, str) and value.strip() == ""):
            result_lines.append(f"{key}: ")
        elif isinstance(value, str):
            needs_quotes = ":" in value or value.startswith(" ") or value.endswith(" ")
            if needs_quotes:
                result_lines.append(f'{key}: "{value}"')
            else:
                result_lines.append(f"{key}: {value}")
        elif isinstance(value, bool):
            result_lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            result_lines.append(f"{key}: {value}")
    
    result_lines.append("---")
    result_lines.append("")
    result_lines.extend(body_lines)
    result_lines.append("")
    
    result = "\n".join(result_lines)
    
    if result != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result)
        return True, ", ".join(changes)
    return False, "no change"


def main():
    base_dir = Path(__file__).resolve().parent.parent / "rag-data" / "processed" / "national"
    
    stats = {"tax_law": 0, "tax_regulation": 0, "qa_corpus": 0, "general_law": 0}
    updated = 0
    
    for subdir in ["tax_law", "qa_corpus"]:
        dir_path = base_dir / subdir
        if not dir_path.exists():
            continue
        
        for md_file in sorted(dir_path.glob("*.md")):
            try:
                changed, detail = process_file(md_file)
                if changed:
                    updated += 1
                    print(f"  ✓ {md_file.name}  [{detail}]")
                    
                    # 统计
                    with open(md_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    for tier in stats:
                        if f"relevance_tier: {tier}" in content:
                            stats[tier] += 1
                            break
            except Exception as e:
                print(f"  ✗ {md_file.name}: {e}", file=sys.stderr)
    
    print(f"\n处理完成: {updated} 个文件更新")
    print(f"分层统计: tax_law={stats['tax_law']}, tax_regulation={stats['tax_regulation']}, "
          f"qa_corpus={stats['qa_corpus']}, general_law={stats['general_law']}")


if __name__ == "__main__":
    main()
