#!/usr/bin/env python3
"""
RAG 数据最终预处理（全流程）
============================
1. 删除损坏的税率表文件
2. 标题标准化：第X章 → ##, 第X条 → ###
3. 智能换行：按 。；： 边界断行
4. 清理 UI 噪声残留
5. 添加相关性分层（relevance_tier + relevance_weight）
"""

import re
import sys
import yaml
from pathlib import Path

# ═══════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════

TAX_LAW_DIR = Path("F:/lest/rag-data/processed/national/tax_law")
QA_DIR = Path("F:/lest/rag-data/processed/national/qa_corpus")

# 文件分类规则
TAX_LAW_NAMES = {
    "个人所得税法", "企业所得税法", "增值税法", "契税法", "印花税法",
    "关税法", "车船税法", "车辆购置税法", "船舶吨税法", "烟叶税法",
    "耕地占用税法", "城市维护建设税法", "环境保护税法", "资源税法",
}

GENERAL_LAW_NAMES = {
    "民事诉讼法", "刑事诉讼法", "行政处罚法", "行政强制法",
    "企业破产法", "会计法", "劳动合同法", "合伙企业法",
    "电子商务法", "社会保险法", "海关法", "环境保护法",
    "矿产资源法", "价格法", "城市房地产管理法",
}

TAX_REGULATION_PATTERNS = [
    r"实施条例", r"实施细则",
    r"管理办法", r"暂行办法", r"试行办法", r"公告办法",
    r"计税办法", r"操作办法", r"征收管理办法",
    r"汇算清缴管理办法",
    r"关于.*的通知", r"关于.*的公告", r"关于.*的决定",
    r"关于.*的补充通知",
    r"条例$", r"办法$",
]

# 损坏的税率表文件（图片引用，不是文字）
CORRUPTED_FILES = [
    "资源税税目税率表.md",
    "车船税税目税额表.md",
    "船舶吨税率表 .md",
]

# ═══════════════════════════════════════════════════════════
# 正则模式
# ═══════════════════════════════════════════════════════════

# 噪声行
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
    re.compile(r"^\s*收藏\s*$"),
    re.compile(r"^\s*分享\s*$"),
    re.compile(r"^\s*订阅\s*$"),
    re.compile(r"^\s*注释\s*$"),
    # 合并形式的噪声
    re.compile(r"^【打印】\s*【下载】\s*$"),
]

DATE_PATTERN = re.compile(r"成文日期[：:]\s*(\d{4}-\d{2}-\d{2})")

# 章标题：第X章 名称
CHAPTER_RE = re.compile(
    r'^(第[一二三四五六七八九十百]+章)\s*[\u3000\s]*(.+)$'
)
# 节标题
SECTION_RE = re.compile(
    r'^(第[一二三四五六七八九十百]+节)\s*[\u3000\s]*(.+)$'
)
# 目录块标记
TOC_LINE = re.compile(r'^目[\u3000\s]*录[\u3000\s]*$')
TOC_CHAPTER = re.compile(r'^第[一二三四五六七八九十百]+章[\u3000\s]')

# ====== 关键：文章边界 ======
# 法条边界：。第X条 或 ；第X条（前一 article 结束 + 下一 article 开始）
ARTICLE_BOUNDARY = re.compile(
    r'([。；])\s*(第[一二三四五六七八九十百]+条[\u3000\s])'
)
# 正文第一个文章：行首的"第X条"
ARTICLE_START = re.compile(
    r'^(第[一二三四五六七八九十百]+条)\s*[\u3000\s]*(.+)'
)

# 附件引用行
ATTACHMENT_RE = re.compile(r'^附件[：:]\s*.*\.(doc|ppt)x?$|^附[：:]\s*.*税目税率表')


# ═══════════════════════════════════════════════════════════
# 核心逻辑
# ═══════════════════════════════════════════════════════════

def classify_file(name_no_ext, doc_title):
    """判断文件层级"""
    for name in GENERAL_LAW_NAMES:
        if name in name_no_ext or name in (doc_title or ""):
            return "general_law", 3
    
    for name in TAX_LAW_NAMES:
        if name in name_no_ext or name in (doc_title or ""):
            for pat in TAX_REGULATION_PATTERNS:
                if re.search(pat, name_no_ext) or re.search(pat, doc_title or ""):
                    return "tax_regulation", 8
            return "tax_law", 10
    
    for pat in TAX_REGULATION_PATTERNS:
        if re.search(pat, name_no_ext) or re.search(pat, doc_title or ""):
            return "tax_regulation", 8
    
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
    return meta, lines[end_idx + 1:], end_idx + 1


def split_article_content(text):
    """法条正文按 。；： 边界断行"""
    if not text.strip():
        return text
    
    result = []
    sentences = text.split('。')
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        # 处理 ； 和 ; （全角/半角分号）
        if '；' in sent or ';' in sent:
            clauses = re.split(r'[；;]', sent)
            for clause in clauses:
                clause = clause.strip()
                if not clause:
                    continue
                # 处理 ： 和 : （全角/半角冒号）
                if ('：' in clause or ':' in clause) and len(re.split(r'[：:]', clause, 1)[-1].strip()) > 10:
                    parts = re.split(r'[：:]', clause, 1)
                    result.append(parts[0] + '：')
                    result.append('  ' + parts[1].strip())
                else:
                    result.append(clause)
        # 处理 ： 和 :
        elif ('：' in sent or ':' in sent) and len(re.split(r'[：:]', sent, 1)[-1].strip()) > 20:
            parts = re.split(r'[：:]', sent, 1)
            result.append(parts[0] + '：')
            result.append('  ' + parts[1].strip())
        else:
            result.append(sent)
    
    return '\n'.join(result)


def split_articles_in_line(line):
    """将包含多个法条的超长行拆分成 (条号, 内容) 列表
    
    核心策略：用 ARTICLE_BOUNDARY (。第X条) 分割，不匹配正文内的交叉引用。
    """
    articles = []
    text = line.strip()
    
    # 先用 ARTICLE_BOUNDARY 在所有 。第X条 处切分
    parts = ARTICLE_BOUNDARY.split(text)
    # parts = ['第一条...', '。', '第二条', '...', '。', '第三条', '...']
    
    if len(parts) == 1:
        # 可能只有一个 article
        m = ARTICLE_START.match(text.strip())
        if m:
            articles.append((m.group(1), m.group(2)))
        return articles
    
    # 多个 article：重组
    # parts[0] 是第一个 article 的前半部分
    first_part = parts[0].strip()
    if first_part:
        m = ARTICLE_START.match(first_part)
        if m:
            articles.append((m.group(1), m.group(2)))
        elif '第' in first_part[:5]:
            # 可能是不标准的格式
            articles.append(("", first_part))
    
    # parts[1:] 按 (punct, num, content) 三元组
    idx = 1
    while idx + 2 <= len(parts):
        punct = parts[idx]      # 。或；
        art_num = parts[idx + 1].strip()  # 第X条
        content = parts[idx + 2].strip()  # 条内容
        articles.append((art_num, content))
        idx += 3
    
    return articles


def process_body(body_lines, meta):
    """处理正文"""
    result = []
    in_toc = False
    extracted_date = None
    
    for line in body_lines:
        stripped = line.strip()
        
        # 跳过噪声
        is_noise = False
        for pat in NOISE_PATTERNS:
            if pat.match(stripped):
                is_noise = True
                break
        if is_noise:
            continue
        
        # 跳过附件引用
        if ATTACHMENT_RE.match(stripped):
            continue
        
        # 提取日期
        if not extracted_date:
            m = DATE_PATTERN.search(stripped)
            if m:
                extracted_date = m.group(1)
                if not meta.get("effective_from"):
                    meta["effective_from"] = extracted_date
                continue
        
        # 跳过目录
        if in_toc:
            if TOC_CHAPTER.match(stripped):
                continue
            if stripped == '':
                continue
            in_toc = False
        if TOC_LINE.match(stripped):
            in_toc = True
            continue
        
        # ── 标题标准化 ──
        m = CHAPTER_RE.match(stripped)
        if m:
            result.append(f"## {m.group(1)}　{m.group(2).strip()}")
            continue
        
        m = SECTION_RE.match(stripped)
        if m:
            result.append(f"### {m.group(1)}　{m.group(2).strip()}")
            continue
        
        # ── 法条拆分 ──
        if len(stripped) > 500 and '第' in stripped:
            articles = split_articles_in_line(stripped)
            if len(articles) >= 2:
                for art_num, content in articles:
                    result.append(f"### {art_num}")
                    processed = split_article_content(content)
                    if processed.strip():
                        result.append(processed)
                continue
        
        # ── 长行换行（含；的内容自动分行）──
        if '；' in stripped or ';' in stripped:
            processed = split_article_content(stripped)
            if processed.strip() and '\n' in processed:
                result.append(processed)
                continue
        
        # 单行一个 article
        m = ARTICLE_START.match(stripped)
        if m:
            result.append(f"### {m.group(1)}")
            processed = split_article_content(m.group(2))
            if processed.strip():
                result.append(processed)
            continue
        
        # 已有标题标记，保持
        if stripped.startswith('### ') or stripped.startswith('## ') or stripped.startswith('# '):
            result.append(stripped)
            continue
        
        # 普通文本
        if stripped:
            result.append(stripped)
        elif result and result[-1] != '':
            result.append('')
    
    # 清理尾部空行
    while result and result[-1] == '':
        result.pop()
    
    return result, extracted_date


def write_output(filepath, meta, body_lines):
    """写入最终文件"""
    lines = ["---"]
    
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
        if value == "" or (isinstance(value, str) and not value.strip()):
            lines.append(f"{key}: ")
        elif isinstance(value, str):
            if ":" in value or value.startswith(" ") or value.endswith(" "):
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    
    lines.append("---")
    lines.append("")
    lines.extend(body_lines)
    lines.append("")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))


def process_tax_law(filepath):
    """处理单个税法文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()
    
    meta, body_lines, _ = parse_frontmatter(original)
    if not meta:
        return False
    
    # 分类
    name_no_ext = filepath.name.replace(".md", "")
    doc_title = meta.get("doc_title", "")
    tier_name, tier_weight = classify_file(name_no_ext, doc_title)
    meta["relevance_tier"] = tier_name
    meta["relevance_weight"] = tier_weight
    
    # 处理正文
    processed_body, extracted_date = process_body(body_lines, meta)
    
    if extracted_date and not meta.get("effective_from"):
        meta["effective_from"] = extracted_date
    
    write_output(filepath, meta, processed_body)
    return True


def process_qa(filepath):
    """QA 文件：只添加 tier 标签，不改正文结构"""
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()
    
    meta, body_lines, _ = parse_frontmatter(original)
    if not meta:
        return False
    
    meta["relevance_tier"] = "qa_corpus"
    meta["relevance_weight"] = 6
    
    write_output(filepath, meta, body_lines)
    return True


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def main():
    # 1. 删除损坏文件
    for fname in CORRUPTED_FILES:
        fpath = TAX_LAW_DIR / fname
        if fpath.exists():
            fpath.unlink()
            print(f"  🗑 删除损坏文件: {fname}")
    
    # 2. 处理税法文件
    tax_count = 0
    for md_file in sorted(TAX_LAW_DIR.glob("*.md")):
        try:
            if process_tax_law(md_file):
                tax_count += 1
                print(f"  ✓ tax_law: {md_file.name}")
        except Exception as e:
            print(f"  ✗ {md_file.name}: {e}", file=sys.stderr)
    
    # 3. 处理 QA 文件
    qa_count = 0
    for md_file in sorted(QA_DIR.glob("*.md")):
        try:
            if process_qa(md_file):
                qa_count += 1
        except Exception as e:
            print(f"  ✗ {md_file.name}: {e}", file=sys.stderr)
    
    # 4. 统计
    stats = {"tax_law": 0, "tax_regulation": 0, "qa_corpus": 0, "general_law": 0}
    for subdir in [TAX_LAW_DIR, QA_DIR]:
        for md_file in subdir.glob("*.md"):
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            for tier in stats:
                if f"relevance_tier: {tier}" in content:
                    stats[tier] += 1
                    break
    
    print(f"\n{'='*50}")
    print(f"  税法文件: {tax_count} 个")
    print(f"  QA 文件: {qa_count} 个")
    print(f"  分层统计: tax_law={stats['tax_law']}, tax_regulation={stats['tax_regulation']}, "
          f"qa_corpus={stats['qa_corpus']}, general_law={stats['general_law']}")


if __name__ == "__main__":
    main()
