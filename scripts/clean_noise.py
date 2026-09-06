#!/usr/bin/env python3
"""
清洗 rag-data 中 tax_law 文件的 UI 残留噪声。
处理的模式：
1. 删除纯 UI 噪声行（微信扫一扫、字体切换、纠错建议等）
2. 提取"全文有效成文日期" → 写入 YAML effective_from
3. 合并散落的"注释"标签到上下文
"""

import re
import os
import sys
import yaml
from pathlib import Path

# ── 噪声行正则（整行匹配就删除）─────────────────────────────
NOISE_PATTERNS = [
    re.compile(r"^\s*微信扫一扫[：:].*$"),
    re.compile(r"^\s*字体[：:].*$"),
    re.compile(r"^\s*扫一扫[，,]\s*分享给好友或朋友圈\s*$"),
    re.compile(r"^\s*收藏订阅已推送.*$"),
    re.compile(r"^\s*语音播报[：:].*$"),
    re.compile(r"^\s*扫一扫在手机打开当前页\s*$"),
    re.compile(r"^\s*【打印】\s*$"),
    re.compile(r"^\s*【下载】\s*$"),
    re.compile(r"^\s*纠错或建议\s*$"),
    # 收藏/分享/订阅 按钮
    re.compile(r"^\s*收藏\s*$"),
    re.compile(r"^\s*分享\s*$"),
    re.compile(r"^\s*订阅\s*$"),
    # 空白的"注释"行（后面没有实质内容）
    re.compile(r"^\s*注释\s*$"),
]

# 提取日期的模式
DATE_PATTERN = re.compile(r"成文日期[：:]\s*(\d{4}-\d{2}-\d{2})")
DATE_IN_TEXT = re.compile(r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起施行")

def parse_frontmatter(text):
    """从 Markdown 中提取 YAML frontmatter 和正文"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, lines, 0
    
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
        meta = {}
    
    body_lines = lines[end_idx + 1:]
    return meta, body_lines, end_idx + 1

def clean_body(body_lines):
    """清理正文中的噪声行"""
    cleaned = []
    extracted_date = None
    skip_next_empty = False
    
    for i, line in enumerate(body_lines):
        # 检查是否是噪声行
        is_noise = False
        for pat in NOISE_PATTERNS:
            if pat.match(line):
                is_noise = True
                break
        
        if is_noise:
            skip_next_empty = True
            continue
        
        # 连续空行合并
        stripped = line.strip()
        if stripped == "":
            if skip_next_empty:
                skip_next_empty = False
                continue
            skip_next_empty = False
        else:
            skip_next_empty = False
        
        # 提取成文日期
        if not extracted_date:
            m = DATE_PATTERN.search(stripped)
            if m:
                extracted_date = m.group(1)
                # 删除这行（它已经被提取了）
                skip_next_empty = True
                continue
        
        cleaned.append(line)
    
    # 清理开头的空行
    while cleaned and cleaned[0].strip() == "":
        cleaned.pop(0)
    # 清理结尾的空行
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop(-1)
    
    return cleaned, extracted_date

def should_clean(filepath):
    """判断文件是否需要清洗"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    for pat in NOISE_PATTERNS:
        if pat.search(content):
            return True
    return bool(DATE_PATTERN.search(content))

def clean_file(filepath):
    """清洗单个文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        original = f.read()
    
    meta, body_lines, fm_end = parse_frontmatter(original)
    
    cleaned_lines, extracted_date = clean_body(body_lines)
    
    # 更新元数据
    if extracted_date and not meta.get("effective_from"):
        meta["effective_from"] = extracted_date
    
    # 重新组装
    result_lines = ["---"]
    for key, value in meta.items():
        if value is None or value == "":
            result_lines.append(f"{key}: ")
        elif isinstance(value, str):
            # 如果有冒号或特殊字符，需要引号
            if ":" in value or value.startswith(" ") or value.endswith(" "):
                result_lines.append(f'{key}: "{value}"')
            else:
                result_lines.append(f"{key}: {value}")
        else:
            result_lines.append(f"{key}: {value}")
    result_lines.append("---")
    result_lines.append("")
    result_lines.extend(cleaned_lines)
    result_lines.append("")  # 文件结尾换行
    
    result = "\n".join(result_lines)
    
    # 只有内容发生变化才写入
    if result != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result)
        return True, extracted_date
    return False, None

def main():
    base_dir = Path(__file__).resolve().parent.parent / "rag-data" / "processed" / "national"
    
    tax_law_dir = base_dir / "tax_law"
    cleaned_count = 0
    date_extracted = 0
    
    for md_file in sorted(tax_law_dir.glob("*.md")):
        try:
            changed, date = clean_file(md_file)
            if changed:
                cleaned_count += 1
                date_info = f" (日期: {date})" if date else ""
                print(f"  ✓ {md_file.name}{date_info}")
                if date:
                    date_extracted += 1
        except Exception as e:
            print(f"  ✗ {md_file.name}: {e}", file=sys.stderr)
    
    print(f"\n清洗完成: {cleaned_count} 个文件, 提取 {date_extracted} 个日期")

if __name__ == "__main__":
    main()
