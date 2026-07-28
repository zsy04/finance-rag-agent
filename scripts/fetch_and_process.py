#!/usr/bin/env python3
"""
财务 RAG 资料半自动化采集脚本
==============================

设计原则：
  - 不是爬虫：只抓取 manifest.json 中已列出的已知 URL，不递归发现链接
  - 尊重政府网站：请求间隔默认 2 秒，单线程串行
  - 支持断点续传：每处理完一项立即写 manifest.json，中断后可继续
  - 人工校对优先：自动抓取 + 人工验证，不是全自动

功能流程：
  读取 manifest.json
      ↓
  筛选待处理项（pending + 有 source_url）
      ↓
  ┌─ 网页 (md): fetch HTML → BeautifulSoup 清洗 → 添加 YAML frontmatter → 保存 .md
  ├─ PDF (pdf): 下载到 raw/pdf/ → 后续用 MarkItDown 手动转换
  └─ JSON (json): 跳过，提示手动整理
      ↓
  更新 manifest.json（status + local_path）
      ↓
  输出汇总报告

使用方式：
  python fetch_and_process.py                     # 抓取所有 pending 网页
  python fetch_and_process.py --dry-run           # 预览：只看不抓
  python fetch_and_process.py --round 1           # 只抓第一轮（~35 个网页）
  python fetch_and_process.py --id 1,3,5,7        # 只抓指定 ID
  python fetch_and_process.py --category tax_law  # 只抓税法类
  python fetch_and_process.py --retry-failed      # 重试之前失败的项
  python fetch_and_process.py --delay 3           # 自定义请求间隔（秒）
"""

import json
import os
import sys
import time
import argparse
import re
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# ============================================================
# 路径配置
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # F:\lest
RAG_DATA_DIR = PROJECT_ROOT / "rag-data"
MANIFEST_PATH = RAG_DATA_DIR / "manifest.json"
RAW_DIR = RAG_DATA_DIR / "raw"
PROCESSED_DIR = RAG_DATA_DIR / "processed"

# ============================================================
# 请求配置
# ============================================================

REQUEST_TIMEOUT = 30   # 单个请求超时（秒）
REQUEST_DELAY = 2.0    # 请求间隔（秒），对政府网站友好
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ============================================================
# YAML frontmatter 模板
# ============================================================

FRONTMATTER_TEMPLATE = """---
source_url: {source_url}
doc_number: {doc_number}
effective_from: {effective_from}
expiry_date: {expiry_date}
module: {module}
category: {category}
city: {city}
doc_title: {doc_title}
fetched_at: {fetched_at}
---

"""

# ============================================================
# 分类 → 输出子目录映射
# ============================================================

CATEGORY_DIR_MAP = {
    "tax_law":    "national/tax_law",
    "qa_corpus":  "national/qa_corpus",
    "rates":      "national/rates",
    "operations": "national/operations",
    "templates":  "national/templates",
}

# ============================================================
# 政府网站正文提取选择器（按优先级排序）
# ============================================================

CONTENT_SELECTORS = [
    "div.article",             # chinatax.gov.cn / fgk.chinatax.gov.cn ✅ 实测可用
    "div.Custom_UnionStyle",   # 部分政府站新版样式
    "div.TRS_Editor",          # 部分政府站编辑器内容
    "div.TRS_PreAppend",       # 税总法规库内容
    "div#UCAP-CONTENT",        # 旧版 gov.cn
    "div.news_content",        # chinatax 新闻页
    "div.xw_box",              # gov.cn 新闻正文
    "div.pages_content",       # gov.cn 新版（可能 JS 渲染）
    "article",                 # HTML5 语义标签
    "main",                    # HTML5 语义标签
    "div#zoom",                # 部分政府站正文
    "div.wrapper.index",       # chinatax 新版页面
    "div.content",             # 通用回退
]

# 要移除的噪音元素
NOISE_TAGS = [
    "script", "style", "noscript", "iframe", "nav", "header", "footer"
]

NOISE_SELECTORS = [
    ".breadcrumb", ".nav", ".navbar", ".sidebar",
    ".footer", ".header", ".top_bar", ".banner",
    ".share", ".print", ".toolbar", ".page_tools",
    ".related_links", ".links", ".hot", ".recommend",
    "#footer", "#header", "#nav",
    "div.function",
]


# ============================================================
# 核心函数
# ============================================================

def load_manifest():
    """加载 manifest.json"""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(data):
    """保存 manifest.json（每处理一项就调用，支持断点续传）"""
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_output_path(item):
    """根据 item 的 city/category 确定输出路径"""
    city = item.get("city", "national")
    category = item.get("category", "")
    fmt = item.get("format", "md")
    item_id = item["id"]

    if city != "national":
        subdir = f"cities/{city}"
    elif category in CATEGORY_DIR_MAP:
        subdir = CATEGORY_DIR_MAP[category]
    else:
        subdir = "national"

    safe_name = re.sub(r'[\\/:*?"<>|]', '_', item["name"])[:60]
    filename = f"{item_id:03d}_{safe_name}.{fmt}"
    return PROCESSED_DIR / subdir / filename


def extract_content(html, url):
    """
    从政府网站 HTML 中提取正文。

    策略：
    1. 移除导航/侧边栏/页脚等噪音
    2. 用已知选择器定位正文容器
    3. 回退：取文本最长的 div
    4. 保留表格为 Markdown 格式
    5. 清理多余空行
    """
    soup = BeautifulSoup(html, "lxml")

    # ---- 1. 移除噪音 ----
    for tag in NOISE_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    for selector in NOISE_SELECTORS:
        for el in soup.select(selector):
            el.decompose()

    # ---- 2. 定位正文容器 ----
    content_div = None
    for selector in CONTENT_SELECTORS:
        content_div = soup.select_one(selector)
        if content_div and len(content_div.get_text(strip=True)) > 200:
            break
        content_div = None

    # ---- 3. 回退策略 ----
    if content_div is None:
        candidates = []
        for div in soup.find_all("div"):
            text_len = len(div.get_text(strip=True))
            if text_len > 500:
                candidates.append((text_len, div))
        candidates.sort(key=lambda x: x[0], reverse=True)
        content_div = candidates[0][1] if candidates else soup.body

    if content_div is None:
        return ""

    # ---- 4. 表格转 Markdown ----
    for table in content_div.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            col_count = rows[0].count("|") - 1
            sep = "|" + "|".join(["---"] * col_count) + "|"
            rows.insert(1, sep)
        table.replace_with(
            BeautifulSoup(f"\n\n{chr(10).join(rows)}\n\n", "html.parser")
        )

    # ---- 5. 提取格式化文本 ----
    lines = []
    for el in content_div.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]):
        tag = el.name
        txt = el.get_text(strip=True)
        if not txt:
            continue

        if tag.startswith("h"):
            level = int(tag[1])
            lines.append(f"\n{'#' * level} {txt}\n")
        elif tag == "li":
            lines.append(f"- {txt}")
        elif tag == "blockquote":
            for line in txt.split("\n"):
                lines.append(f"> {line}")
        else:
            # <p> 段落
            lines.append(f"\n{txt}\n")

    text = "\n".join(lines)

    # ---- 6. 清理 ----
    # 合并多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 移除行首行尾空白
    text = text.strip()
    # 确保末尾有换行
    if text and not text.endswith("\n"):
        text += "\n"

    return text


def build_frontmatter(item):
    """为 item 构建 YAML frontmatter"""
    return FRONTMATTER_TEMPLATE.format(
        source_url=item.get("source_url") or "",
        doc_number=item.get("doc_number") or "",
        effective_from=item.get("effective_from") or "",
        expiry_date=item.get("expiry_date") or "",
        module=item.get("module") or "",
        category=item.get("category") or "",
        city=item.get("city") or "national",
        doc_title=item.get("name") or "",
        fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def fetch_webpage(item, session):
    """
    抓取单个网页。

    返回 (success: bool, content_or_error: str)
    如果 success=True，content 是清洗后的 Markdown 文本
    如果 success=False，content 是错误描述
    """
    url = item.get("source_url")
    if not url:
        return False, "无 source_url"

    try:
        resp = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()

        if "application/pdf" in content_type:
            return _download_pdf(item, resp)
        else:
            # 编码处理：政府网站可能声明 ISO-8859-1 但实际是 UTF-8
            if resp.apparent_encoding and resp.apparent_encoding.lower() in ("utf-8", "utf8"):
                resp.encoding = resp.apparent_encoding
            elif resp.encoding and resp.encoding.lower() not in ("utf-8", "utf8"):
                # 强制 UTF-8，因为中文政府网站基本都是 UTF-8
                resp.encoding = "utf-8"

            text = extract_content(resp.text, url)

            if not text or len(text) < 100:
                # 可能是 JS 渲染页面（如 gov.cn），给出明确提示
                domain = urlparse(url).netloc
                if "gov.cn" in domain:
                    return False, (
                        f"内容过短（{len(text)} 字符），可能是 JS 渲染页面"
                        f"——请手动在浏览器打开该 URL 复制正文"
                    )
                return False, f"内容过短（{len(text)} 字符），正文提取可能失败"

            return True, text

    except requests.exceptions.Timeout:
        return False, "请求超时"
    except requests.exceptions.ConnectionError as e:
        return False, f"连接失败: {str(e)[:80]}"
    except requests.exceptions.HTTPError as e:
        return False, f"HTTP {e.response.status_code}"
    except Exception as e:
        return False, f"未知错误: {str(e)[:120]}"


def _download_pdf(item, resp):
    """下载 PDF 到 raw/pdf/ 目录"""
    output_dir = RAW_DIR / "pdf"
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r'[\\/:*?"<>|]', '_', item["name"])[:60]
    filename = f"{item['id']:03d}_{safe_name}.pdf"
    filepath = output_dir / filename

    with open(filepath, "wb") as f:
        f.write(resp.content)

    return True, f"PDF 已保存: {filepath.relative_to(PROJECT_ROOT)}"


def save_processed_md(item, content):
    """保存 Markdown 文件（内容 + YAML frontmatter）"""
    output_path = get_output_path(item)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    full_content = build_frontmatter(item) + content

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return str(output_path.relative_to(PROJECT_ROOT))


# ============================================================
# 筛选逻辑
# ============================================================

def filter_items(manifest, args):
    """按命令行参数筛选需要处理的 items"""
    items = manifest[:]

    if args.format:
        items = [i for i in items if i.get("format") == args.format]
    if args.round is not None:
        items = [i for i in items if i.get("round") == args.round]
    if args.category:
        items = [i for i in items if i.get("category") == args.category]
    if args.module:
        items = [i for i in items if i.get("module") == args.module]
    if args.id:
        ids = [int(x.strip()) for x in args.id.split(",")]
        items = [i for i in items if i["id"] in ids]
    if args.city:
        items = [i for i in items if i.get("city") == args.city]

    # 状态筛选
    if args.retry_failed:
        items = [i for i in items if i.get("status") == "failed"]
    elif not args.include_done:
        items = [i for i in items if i.get("status") == "pending"]

    # 跳过 Phase 2/3
    items = [i for i in items if i.get("priority") != "📋"]

    return items


# ============================================================
# 统计工具
# ============================================================

def categorize_items(items):
    """将筛选后的 items 分类统计"""
    web = [i for i in items if i.get("format") == "md" and i.get("source_url")]
    pdf = [i for i in items if i.get("format") == "pdf" and i.get("source_url")]
    json_items = [i for i in items if i.get("format") == "json"]
    manual = [i for i in items if not i.get("source_url") and i.get("format") != "json"]
    return web, pdf, json_items, manual


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="财务 RAG 资料半自动化采集 — 不是爬虫，是定向抓取 + 清洗",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python fetch_and_process.py                      抓取所有 pending 网页
  python fetch_and_process.py --dry-run            预览：只看不抓
  python fetch_and_process.py --round 1            只抓第一轮（~35个网页）
  python fetch_and_process.py --id 1,3,5,7         只抓指定 ID
  python fetch_and_process.py --category tax_law   只抓税法类
  python fetch_and_process.py --retry-failed       重试失败项
  python fetch_and_process.py --delay 3            间隔 3 秒（默认 2 秒）

输出结构:
  rag-data/
  ├── manifest.json               ← 进度追踪（每项即写，支持断点续传）
  ├── raw/pdf/                    ← 下载的 PDF 原件
  ├── processed/
  │   ├── national/tax_law/       ← 税法原文 .md
  │   ├── national/qa_corpus/     ← 即问即答 .md
  │   ├── national/rates/         ← 税率表 .json（手动整理）
  │   ├── national/operations/    ← 操作指引 .md
  │   ├── national/templates/     ← 申报表模板
  │   └── cities/zhengzhou/       ← 郑州地方数据
        """
    )

    parser.add_argument("--dry-run", action="store_true",
                        help="预览模式：列出将要处理的项，不实际抓取")
    parser.add_argument("--round", type=int, choices=[1, 2, 3],
                        help="只处理指定轮次")
    parser.add_argument("--id", type=str,
                        help="只处理指定 ID，逗号分隔（如: 1,3,7）")
    parser.add_argument("--category", type=str,
                        choices=["tax_law", "qa_corpus", "rates", "operations", "templates"],
                        help="只处理指定分类")
    parser.add_argument("--module", type=str,
                        choices=["一", "二", "三", "四", "五"],
                        help="只处理指定模块")
    parser.add_argument("--city", type=str,
                        choices=["national", "zhengzhou"],
                        help="只处理指定城市层级")
    parser.add_argument("--format", type=str,
                        choices=["md", "json", "pdf"],
                        help="只处理指定格式（预览用）")
    parser.add_argument("--retry-failed", action="store_true",
                        help="只重试 status=failed 的项")
    parser.add_argument("--include-done", action="store_true",
                        help="包含已完成的项（重新抓取，慎用）")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY,
                        help=f"请求间隔秒数（默认 {REQUEST_DELAY}s）")

    args = parser.parse_args()

    # ---- 加载 manifest ----
    if not MANIFEST_PATH.exists():
        print(f"❌ 找不到 manifest.json: {MANIFEST_PATH}")
        print("   请先确保 rag-data/manifest.json 存在")
        sys.exit(1)

    manifest = load_manifest()
    items = filter_items(manifest, args)
    web_items, pdf_items, json_items, manual_items = categorize_items(items)

    # ---- 显示筛选结果 ----
    total_pending = sum(1 for i in manifest if i.get("status") == "pending" and i.get("priority") != "📋")
    total_done = sum(1 for i in manifest if i.get("status") == "done")
    total_failed = sum(1 for i in manifest if i.get("status") == "failed")

    print()
    print("=" * 64)
    print("  财务 RAG 资料半自动化采集")
    print("=" * 64)
    print(f"  全量进度: ✅ {total_done}  |  ⏳ {total_pending}  |  ❌ {total_failed}")
    print(f"  本次筛选: 共 {len(items)} 项")
    print(f"    🌐 网页抓取: {len(web_items)}")
    print(f"    📄 PDF 下载: {len(pdf_items)}")
    print(f"    📊 JSON (手动整理): {len(json_items)}")
    print(f"    ✍️  自建资料 (手动整理): {len(manual_items)}")
    print()

    if args.dry_run:
        print("🔍 [预览模式] 以下是将要处理的项:\n")
        for item in items:
            fmt_icon = {"md": "🌐", "pdf": "📄", "json": "📊"}.get(item.get("format"), "❓")
            url_or_note = item.get("source_url") or "(无 URL, 需手动整理)"
            print(f"  [{item['id']:03d}] {fmt_icon} {item['name']}")
            print(f"        ↳ {url_or_note}")
            if item.get("notes"):
                print(f"        📝 {item['notes']}")
            print()
        print(f"共 {len(items)} 项。去掉 --dry-run 执行实际采集。")
        return

    if not items:
        print("✅ 没有需要处理的项。")
        return

    # ---- 实际抓取 ----
    print("🚀 开始抓取...\n")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    success_count = 0
    fail_count = 0
    skip_count = 0
    manual_count = 0

    for idx, item in enumerate(items):
        item_id = item["id"]
        item_name = item["name"]
        fmt = item.get("format", "md")

        # ---- 需要手动处理的类型 ----
        if fmt == "json":
            print(f"  [{item_id:03d}] 📊 {item_name}")
            print(f"         ↳ JSON 结构化数据，需手动整理，已跳过")
            skip_count += 1
            continue

        if not item.get("source_url"):
            print(f"  [{item_id:03d}] ✍️  {item_name}")
            print(f"         ↳ 无采集链接，需手动整理到对应目录")
            manual_count += 1
            continue

        # ---- 开始抓取 ----
        print(f"  [{item_id:03d}] ⏳ {item_name} ...", end=" ", flush=True)

        success, result = fetch_webpage(item, session)

        if success:
            saved_path = save_processed_md(item, result)
            item["status"] = "done"
            item["local_path"] = saved_path
            print(f"✅ → {saved_path}")
            success_count += 1
        else:
            item["status"] = "failed"
            item["notes"] = (
                (item.get("notes") or "") + f" [采集失败: {result}]"
            ).strip()
            print(f"❌ {result}")
            fail_count += 1

        # 每项立即保存，支持 Ctrl+C 中断后继续
        save_manifest(manifest)

        # 请求间隔
        if idx < len(items) - 1:
            time.sleep(args.delay)

    # ---- 汇总报告 ----
    print()
    print("=" * 64)
    print("  📊 采集完毕")
    print("=" * 64)
    print(f"  ✅ 成功: {success_count}")
    print(f"  ❌ 失败: {fail_count}")
    print(f"  ⏭️  跳过 (JSON): {skip_count}")
    if manual_count:
        print(f"  ✍️  跳过 (需手动整理): {manual_count}")
    print()
    print(f"  📁 处理后文件: {PROCESSED_DIR.relative_to(PROJECT_ROOT)}/")
    print(f"  📋 进度文件:   {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    print()
    print("  ⚠️  重要提醒：")
    print("     1. 采集成功的 .md 文件需人工校对标题/金额/税率数字")
    print("     2. JSON 结构化数据（税率表/社保比例）需手动整理")
    print("     3. 自建资料（速查表/发票大全）需手动编写")
    print("     4. PDF 下载后需用 MarkItDown 转换")

    if fail_count > 0:
        print(f"\n  💡 {fail_count} 项失败，可用 --retry-failed 重试")
        print("     也可查看 manifest.json 中 status=failed 的项，手动处理")


if __name__ == "__main__":
    main()
