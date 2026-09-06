#!/usr/bin/env python3
"""
税法文件预处理：标题标准化 + 智能换行
──────────────────────────────────
1. 标题标准化：第X章 → ## 第X章, 第X条 → ### 第X条
2. 智能换行：对正文中内容，按 。；： 边界断行
3. 修复残留噪声：【打印】【下载】、重复空行
"""

import re
import sys
import yaml
from pathlib import Path


# ── 正则模式 ─────────────────────────────────────────────

# 匹配"第X章"（含全角空格、各种间隔符）
CHAPTER_PATTERN = re.compile(
    r'^(第[一二三四五六七八九十百]+章)\s*[\u3000\s]*(.+)$'
)
# 匹配"第X节"
SECTION_PATTERN = re.compile(
    r'^(第[一二三四五六七八九十百]+节)\s*[\u3000\s]*(.+)$'
)
# 文章边界：。第X条 或 ；第X条（前一条结束 + 下一条开始）
ARTICLE_BOUNDARY = re.compile(
    r'[。；]\s*(第[一二三四五六七八九十百]+条[\u3000\s])'
)
# 正文开头的第一条：行首的"第X条"
ARTICLE_START = re.compile(
    r'^(第[一二三四五六七八九十百]+条)\s*[\u3000\s]*(.+)'
)
# 单独一行的"第X条"（可能是残留的条号标记）
ARTICLE_LINE = re.compile(
    r'^(第[一二三四五六七八九十百]+条)\s*$'
)

# 目录块（"目　　录" 到后半部分的内容）
TOC_START = re.compile(r'^目[\u3000\s]*录[\u3000\s]*$')
TOC_CHAPTER = re.compile(r'^第[一二三四五六七八九十百]+章[\u3000\s]')

# 残留噪声
NOISE_TAIL = re.compile(r'【打印】\s*【下载】\s*$')
NOISE_SINGLE = re.compile(r'^【打印】\s*$|^【下载】\s*$')

# 附件引用行（税率表引用，已经损坏的文件删掉了）
ATTACHMENT_PATTERN = re.compile(r'^附件[：:]\s*.*\.(doc|ppt)x?$|^附[：:]\s*.*税目税率表')

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
    return meta, lines[end_idx + 1:], end_idx + 1


def is_long_line(line, threshold=500):
    """判断是否是需要拆分的超长行"""
    return len(line) > threshold


def split_article_content(text):
    """将法条正文按 。；： 边界断行
    
    规则：
    1. 先按 。 分割 → 每句一行
    2. 句内如有 ；→ 在 ；处断行（保持缩进）
    3. ：后内容 → 换行缩进
    """
    if not text.strip():
        return text
    
    result = []
    
    # Step 1: 按 。分割
    sentences = text.split('。')
    for i, sent in enumerate(sentences):
        sent = sent.strip()
        if not sent:
            continue
        
        # 对每个句子，进一步按 ；分割
        if '；' in sent:
            clauses = sent.split('；')
            for j, clause in enumerate(clauses):
                clause = clause.strip()
                if not clause:
                    continue
                
                # 处理：后的内容
                if '：' in clause:
                    # 冒号前的内容和冒号后的内容分开
                    parts = clause.split('：', 1)
                    if len(parts) == 2:
                        prefix, suffix = parts
                        result.append(prefix + '：')
                        result.append('  ' + suffix.strip())
                    else:
                        result.append(clause)
                else:
                    result.append(clause)
        elif '：' in sent:
            # 没有分号但有冒号
            parts = sent.split('：', 1)
            if len(parts) == 2 and len(parts[1]) > 20:
                # 冒号后内容较长，换行
                result.append(parts[0] + '：')
                result.append('  ' + parts[1].strip())
            else:
                result.append(sent)
        else:
            result.append(sent)
    
    return '\n'.join(result)


def process_body_lines(body_lines):
    """处理正文：添加标题标记 + 智能换行"""
    result = []
    in_toc = False
    toc_section = False
    
    for i, line in enumerate(body_lines):
        stripped = line.strip()
        
        # 跳过残留噪声
        if NOISE_TAIL.search(stripped) or NOISE_SINGLE.match(stripped):
            continue
        
        # 跳过附件引用行
        if ATTACHMENT_PATTERN.match(stripped):
            continue
        
        # 处理目录块
        if TOC_START.match(stripped):
            in_toc = True
            continue
        if in_toc:
            if TOC_CHAPTER.match(stripped):
                continue  # 跳过目录中的章节引用
            if stripped == '':
                continue
            # 不是章节目录行，结束 TOC 模式
            # 检视后续：如果连续 3 行都是章节行，仍在 TOC 中
            if i + 3 < len(body_lines):
                next_lines = [body_lines[i+j].strip() for j in range(3)]
                if all(TOC_CHAPTER.match(l) or l == '' for l in next_lines if l):
                    continue
            in_toc = False
        
        # ── 标题标准化 ──
        
        # 章节标题：第X章 → ## 第X章 XXX
        m = CHAPTER_PATTERN.match(stripped)
        if m:
            chap_num = m.group(1)
            chap_name = m.group(2).strip()
            if chap_name:
                result.append(f"## {chap_num}　{chap_name}")
            else:
                result.append(f"## {chap_num}")
            continue
        
        # 节标题：第X节 → ### 第X节 XXX（与条同级别，或可考虑 ####）
        m = SECTION_PATTERN.match(stripped)
        if m:
            sec_num = m.group(1)
            sec_name = m.group(2).strip()
            if sec_name:
                result.append(f"### {sec_num}　{sec_name}")
            else:
                result.append(f"### {sec_num}")
            continue
        
        # ── 处理含法条的超长行 ──
        
        if is_long_line(stripped) and ARTICLE_BOUNDARY.search(stripped):
            # 用"。」第X条"或"；」第X条"作为边界分割
            # 策略：先用 ARTICLE_BOUNDARY 分割，得到每篇文章
            # 格式：['第一条...', '第二条...', '第三条...']
            
            # 把 stripped 用 。第X条 模式切分
            parts = ARTICLE_BOUNDARY.split(stripped)
            # parts: ['第一条...', '。', '第二条', '...。', '第三条', '...。']
            # 重组：取 0, 2+3, 5+6, ...
            
            articles = []
            # 第一部分是整个第一条的内容（从开头到第一个 。第X条 之前）
            if parts[0].strip():
                articles.append(parts[0].strip())
            
            # 之后的每两对是一个 article: [punctuation, article_number, content, ...]
            idx = 1
            while idx + 2 < len(parts):
                article_num = parts[idx + 1].strip()
                content = parts[idx + 2].strip()
                articles.append(article_num + content)
                idx += 3
            
            # 输出所有 articles
            for art_text in articles:
                m = ARTICLE_START.match(art_text)
                if m:
                    art_num = m.group(1)
                    art_content = m.group(2)
                    result.append(f"### {art_num}")
                    processed = split_article_content(art_content)
                    if processed.strip():
                        result.append(processed)
                else:
                    # 没有匹配到"第X条"前缀，可能是残留文本
                    processed = split_article_content(art_text)
                    if processed.strip():
                        result.append(processed)
            
            continue
        
        # 单行只有一个"第X条"
        single_match = ARTICLE_START.match(stripped)
        if single_match:
            article_num = single_match.group(1)
            content = single_match.group(2)
            result.append(f"### {article_num}")
            processed = split_article_content(content)
            if processed.strip():
                result.append(processed)
            continue
        
        # 普通行（已经是正确格式的）
        # 如果是已存在的 ### 或 ## 标题行，保持不变
        if stripped.startswith('### ') or stripped.startswith('## ') or stripped.startswith('# '):
            result.append(stripped)
            continue
        
        # 其他普通文本行
        if stripped:
            result.append(stripped)
        else:
            # 避免连续空行
            if result and result[-1] != '':
                result.append('')
    
    # 清理尾部空行
    while result and result[-1] == '':
        result.pop()
    
    return result


def clean_file(filepath):
    """清洗单个文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()
    
    meta, body_lines, fm_end = parse_frontmatter(original)
    if not meta:
        return False, "no frontmatter"
    
    processed = process_body_lines(body_lines)
    
    # 重新组装
    result_lines = ["---"]
    
    field_order = [
        "source_url", "doc_number", "effective_from", "expiry_date",
        "module", "category", "city", "doc_title",
        "relevance_tier", "relevance_weight", "cleaned_at"
    ]
    
    ordered = {}
    for key in field_order:
        if key in meta and meta[key] is not None:
            ordered[key] = meta[key]
    for key, value in meta.items():
        if key not in ordered and value is not None:
            ordered[key] = value
    
    for key, value in ordered.items():
        if value == "" or (isinstance(value, str) and value.strip() == ""):
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
    result_lines.extend(processed)
    result_lines.append("")
    
    result = "\n".join(result_lines)
    
    if result != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(result)
        return True, "updated"
    return False, "no change"


def main():
    tax_law_dir = Path(__file__).resolve().parent.parent / "rag-data" / "processed" / "national" / "tax_law"
    
    updated = 0
    skipped = 0
    
    for md_file in sorted(tax_law_dir.glob("*.md")):
        try:
            changed, status = clean_file(md_file)
            if changed:
                updated += 1
                print(f"  ✓ {md_file.name}")
            else:
                skipped += 1
        except Exception as e:
            print(f"  ✗ {md_file.name}: {e}", file=sys.stderr)
    
    print(f"\n处理完成: {updated} 个文件更新, {skipped} 个文件无变化")


if __name__ == "__main__":
    main()
