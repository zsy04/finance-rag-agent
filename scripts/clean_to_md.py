#!/usr/bin/env python3
"""
财务 RAG 资料批量清洗脚本
==========================

用法：
  1. 在浏览器中打开财税法规页面 → 另存为 HTML → 放到 staging/ 目录
  2. 编辑 metadata.json，为每个 HTML 文件填写元数据（标题、来源、文号、分类）
  3. 运行脚本 → 输出清洗后的 .md 到 processed/ 目录

  python scripts/clean_to_md.py                           # 转换 staging/ 下所有 HTML
  python scripts/clean_to_md.py --dry-run                 # 预览：看哪些文件将被处理
  python scripts/clean_to_md.py --input rag-data/staging  # 指定输入目录

输入要求：
  staging/                          ← 你把下载的 HTML 放这里
  ├── 个税法.html
  ├── 社保法.html
  └── ...

  metadata.json                     ← 源数据映射（文件名→元数据）
  {
    "个税法.html": {
      "doc_title": "个人所得税法（2018修正）",
      "source_url": "https://www.gov.cn/...",
      "doc_number": "主席令第9号",
      "module": "一",
      "category": "tax_law",
      "city": "national"
    }
  }

输出结构（自动路由）：
  processed/
  ├── national/tax_law/    ← category=tax_law 的文件
  ├── national/qa_corpus/  ← category=qa_corpus 的文件
  ├── national/rates/      ← category=rates 的文件
  ├── national/operations/ ← category=operations 的文件
  ├── national/templates/  ← category=templates 的文件
  └── cities/zhengzhou/    ← city=zhengzhou 的文件
"""

import json
import os
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime

from bs4 import BeautifulSoup

# ============================================================
# 配置
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "rag-data" / "staging"
DEFAULT_OUTPUT = PROJECT_ROOT / "rag-data" / "processed"
DEFAULT_METADATA = DEFAULT_INPUT / "metadata.json"

# YAML frontmatter 模板
FRONTMATTER = """---
source_url: {source_url}
doc_number: {doc_number}
effective_from: {effective_from}
expiry_date: {expiry_date}
module: {module}
category: {category}
city: {city}
doc_title: {doc_title}
cleaned_at: {cleaned_at}
---

"""

# 分类 → 输出子目录
CATEGORY_DIR = {
    "tax_law":    "national/tax_law",
    "qa_corpus":  "national/qa_corpus",
    "rates":      "national/rates",
    "operations": "national/operations",
    "templates":  "national/templates",
}

# 正文选择器（按优先级）
CONTENT_SELECTORS = [
    "div.article",
    "div.Custom_UnionStyle",
    "div.TRS_Editor",
    "div.TRS_PreAppend",
    "div#UCAP-CONTENT",
    "div.news_content",
    "div.xw_box",
    "div.pages_content",
    "article",
    "main",
    "div#zoom",
    "div.wrapper.index",
    "div.content",
]

NOISE_TAGS = ["script", "style", "noscript", "iframe", "nav", "header", "footer"]
NOISE_SELECTORS = [
    ".breadcrumb", ".nav", ".navbar", ".sidebar",
    ".footer", ".header", ".top_bar", ".banner",
    ".share", ".print", ".toolbar", ".page_tools",
    ".related_links", ".links", ".hot", ".recommend",
    "#footer", "#header", "#nav",
    "div.function",
]

# ============================================================
# MHTML 处理：fgk 下载的 .doc 实际是 MIME HTML
# ============================================================

def extract_html_from_mhtml(filepath):
    """
    从 MHTML 中提取 HTML 内容。支持两种格式：
      A. fgk 在线版：Content-Base + 明文 HTML
      B. fgk 下载版：MIME multipart + Base64 编码 HTML

    返回 (html: str, source_url: str | None)
    """
    import base64

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # 提取 source_url
    source_url = None
    for pattern in [r'Content-Base:\s*(https?://\S+)',
                    r'Content-Location:\s*(https?://\S+)']:
        match = re.search(pattern, content)
        if match:
            source_url = match.group(1)
            break

    # --- 格式 A：明文 HTML（fgk 在线保存版）---
    boundary_match = re.search(r'boundary="([^"]+)"', content)
    if boundary_match:
        boundary = boundary_match.group(1)
        # 找 text/html 段，可能是明文也可能是 base64
        section_re = (
            rf'Content-Type:\s*text/html.*?'
            rf'(?:Content-Transfer-Encoding:\s*base64\s*)?\r?\n\r?\n'
            rf'(.*?)'
            rf'(?:\r?\n--{re.escape(boundary)})'
        )
        for m in re.finditer(section_re, content, re.DOTALL | re.IGNORECASE):
            html_part = m.group(1).strip()
            if not html_part:
                continue
            # 检测是否 Base64 编码
            if re.match(r'^[A-Za-z0-9+/=\s]+$', html_part[:200]):
                try:
                    decoded = base64.b64decode(html_part.replace('\n', '').replace('\r', ''))
                    decoded_text = decoded.decode('utf-16-le', errors='replace')
                    # UTF-16LE HTML: find the <html tag
                    html_start = decoded_text.find('<html')
                    if html_start >= 0:
                        html_end = decoded_text.rfind('</html>')
                        if html_end > html_start:
                            decoded_text = decoded_text[html_start:html_end + 7]
                    if len(decoded_text) > 500:
                        return decoded_text, source_url
                except Exception:
                    pass
            else:
                if len(html_part) > 500:
                    return html_part, source_url

    # --- 格式 B：内嵌明文 HTML（非 multipart）---
    # 有些 .doc 文件直接是 MIME 头 + HTML
    html_start = content.find("<!DOCTYPE html>")
    if html_start < 0:
        html_start = content.find("<html")
    if html_start >= 0:
        html_end = content.rfind("</html>")
        if html_end > html_start:
            return content[html_start:html_end + 7], source_url

    return content, source_url


def is_mhtml(filepath):
    """检测文件是否为 MHTML 格式"""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        head = f.read(200)
    head_lower = head.lower()
    return "mime-version:" in head_lower or "content-base:" in head_lower


# ============================================================
# 核心：HTML → Markdown
# ============================================================

def clean_html(filepath):
    """清洗单个 HTML/MHTML 文件，返回干净的 Markdown 文本"""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    # 如果是 MHTML（fgk 下载的 .doc），先剥出 HTML
    if "mime-version:" in raw[:200].lower() or "content-base:" in raw[:200].lower():
        html, _ = extract_html_from_mhtml(filepath)
    else:
        html = raw

    soup = BeautifulSoup(html, "lxml")

    # 移除噪音
    for tag in NOISE_TAGS:
        for el in soup.find_all(tag):
            el.decompose()
    for selector in NOISE_SELECTORS:
        for el in soup.select(selector):
            el.decompose()

    # 定位正文
    content_div = None
    for selector in CONTENT_SELECTORS:
        content_div = soup.select_one(selector)
        if content_div and len(content_div.get_text(strip=True)) > 200:
            break
        content_div = None

    if content_div is None:
        candidates = []
        for div in soup.find_all("div"):
            n = len(div.get_text(strip=True))
            if n > 500:
                candidates.append((n, div))
        candidates.sort(key=lambda x: x[0], reverse=True)
        content_div = candidates[0][1] if candidates else soup.body

    if content_div is None:
        return ""

    # 表格转 Markdown
    _convert_tables(content_div)

    # 段落提取
    lines = []
    for el in content_div.find_all(
        ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]
    ):
        tag = el.name
        txt = el.get_text(strip=True)
        if not txt:
            continue

        if tag.startswith("h"):
            lines.append(f"\n{'#' * int(tag[1])} {txt}\n")
        elif tag == "li":
            lines.append(f"- {txt}")
        elif tag == "blockquote":
            for line in txt.split("\n"):
                lines.append(f"> {line}")
        else:
            lines.append(f"\n{txt}\n")

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if text and not text.endswith("\n"):
        text += "\n"

    return text


def _convert_tables(container):
    """将容器内 HTML 表格转为 Markdown"""
    for table in container.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            cols = rows[0].count("|") - 1
            rows.insert(1, "|" + "|".join(["---"] * cols) + "|")
        table.replace_with(
            BeautifulSoup(f"\n\n{chr(10).join(rows)}\n\n", "html.parser")
        )


# ============================================================
# 输出路径计算
# ============================================================

def get_output_path(meta):
    """根据元数据确定输出路径"""
    city = meta.get("city", "national")
    category = meta.get("category", "")

    if city != "national":
        subdir = f"cities/{city}"
    elif category in CATEGORY_DIR:
        subdir = CATEGORY_DIR[category]
    else:
        subdir = "national"

    safe_name = re.sub(r'[\\/:*?"<>|]', "_", meta.get("doc_title", "unknown"))[:60]
    filename = f"{safe_name}.md"
    return DEFAULT_OUTPUT / subdir / filename


def build_frontmatter(meta):
    """构建 YAML frontmatter"""
    return FRONTMATTER.format(
        source_url=meta.get("source_url", ""),
        doc_number=meta.get("doc_number", ""),
        effective_from=meta.get("effective_from", ""),
        expiry_date=meta.get("expiry_date", ""),
        module=meta.get("module", ""),
        category=meta.get("category", ""),
        city=meta.get("city", "national"),
        doc_title=meta.get("doc_title", ""),
        cleaned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="财务 RAG 批量清洗：下载的 HTML → 干净的 Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用流程:
  1. 浏览器打开法规页面 → 右键"另存为" → 保存 .html 到 staging/
  2. 编辑 staging/metadata.json，为每个文件填写元数据
  3. python scripts/clean_to_md.py
  4. 检查 processed/ 下生成的 .md 文件

示例:
  python scripts/clean_to_md.py                    # 转换 staging/ 下所有 HTML
  python scripts/clean_to_md.py --dry-run           # 预览
  python scripts/clean_to_md.py -i rag-data/staging # 指定输入目录
        """
    )

    parser.add_argument("--input", "-i", type=str, default=str(DEFAULT_INPUT),
                        help=f"HTML 文件目录（默认: {DEFAULT_INPUT.relative_to(PROJECT_ROOT)}）")
    parser.add_argument("--output", "-o", type=str, default=str(DEFAULT_OUTPUT),
                        help=f"输出目录（默认: {DEFAULT_OUTPUT.relative_to(PROJECT_ROOT)}）")
    parser.add_argument("--metadata", "-m", type=str, default=str(DEFAULT_METADATA),
                        help="元数据 JSON 文件路径")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览模式：列出将处理的文件，不实际转换")

    args = parser.parse_args()

    input_dir = Path(args.input)
    metadata_path = Path(args.metadata)

    # 检查输入目录
    if not input_dir.exists():
        print(f"❌ 输入目录不存在: {input_dir}")
        print(f"   请创建该目录并把下载的 HTML 文件放进去")
        print(f"   mkdir {input_dir.relative_to(PROJECT_ROOT)}")
        sys.exit(1)

    # 加载元数据
    metadata = {}
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        print(f"📋 加载元数据: {len(metadata)} 条")
    else:
        print("⚠️  未找到 metadata.json，将使用文件名作为标题")
        print(f"   可创建 {metadata_path.relative_to(PROJECT_ROOT)} 填写元数据")

    # 收集 HTML 文件
    html_files = sorted(input_dir.glob("*.html")) + \
                 sorted(input_dir.glob("*.htm")) + \
                 sorted(input_dir.glob("*.doc")) + \
                 sorted(input_dir.glob("*.mhtml"))

    if not html_files:
        print(f"❌ {input_dir.relative_to(PROJECT_ROOT)}/ 下没有 HTML 文件")
        print("   请先把下载的网页放到该目录")
        sys.exit(1)

    # 预览模式
    if args.dry_run:
        print(f"\n🔍 预览：{len(html_files)} 个 HTML 文件\n")
        for f in html_files:
            meta = metadata.get(f.name, {})
            title = meta.get("doc_title", f.name)
            cat = meta.get("category", "未指定")
            print(f"  📄 {f.name}")
            print(f"     → {title}")
            print(f"     → category={cat}")
            print()
        print(f"共 {len(html_files)} 个文件。去掉 --dry-run 执行转换。")
        return

    # 批量转换
    print(f"\n🚀 开始转换 {len(html_files)} 个文件...\n")

    ok = 0
    fail = 0

    for html_file in html_files:
        fname = html_file.name
        meta = metadata.get(fname, {})

        # 自动补全元数据
        if not meta.get("doc_title"):
            meta["doc_title"] = html_file.stem
        if not meta.get("category"):
            meta["category"] = ""

        # MHTML 文件自动提取 source_url（从 Content-Base 头）
        if not meta.get("source_url") and is_mhtml(str(html_file)):
            _, auto_url = extract_html_from_mhtml(str(html_file))
            if auto_url:
                meta["source_url"] = auto_url

        print(f"  ⏳ {fname} ...", end=" ", flush=True)

        try:
            md_text = clean_html(str(html_file))

            if not md_text or len(md_text) < 100:
                print(f"⚠️ 内容过短（{len(md_text)} 字符），可能提取失败，已跳过")
                fail += 1
                continue

            output_path = get_output_path(meta)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            full_content = build_frontmatter(meta) + md_text
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(full_content)

            size_kb = len(md_text) / 1024
            print(f"✅ → {output_path.relative_to(PROJECT_ROOT)} ({size_kb:.1f} KB)")
            ok += 1

        except Exception as e:
            print(f"❌ {e}")
            fail += 1

    print(f"\n{'='*60}")
    print(f"  完成: ✅ {ok}  |  ❌ {fail}")
    print(f"  输出: {Path(args.output).relative_to(PROJECT_ROOT)}/")
    if ok > 0:
        print(f"\n  ⚠️ 请人工校对转换后的 .md 文件中的金额、税率、表格数据")


if __name__ == "__main__":
    main()
