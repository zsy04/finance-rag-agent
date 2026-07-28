#!/usr/bin/env python3
"""
财务 RAG PDF 批量转换脚本
=========================

用法：
  1. 把 PDF 文件放到 rag-data/raw/pdf/
  2. （可选）编辑 rag-data/raw/pdf/metadata.json 填写元数据
  3. python scripts/pdf_to_md.py
  4. 检查 processed/ 下的输出

如果没有 metadata.json，脚本会自动从文件名提取标题，默认 category="tax_law"。
"""

import json
import re
import argparse
from pathlib import Path
from datetime import datetime

from markitdown import MarkItDown

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = PROJECT_ROOT / "rag-data" / "raw" / "pdf"
OUTPUT_DIR = PROJECT_ROOT / "rag-data" / "processed"
METADATA_PATH = PDF_DIR / "metadata.json"

CATEGORY_DIR = {
    "tax_law":    "national/tax_law",
    "qa_corpus":  "national/qa_corpus",
    "rates":      "national/rates",
    "operations": "national/operations",
    "templates":  "national/templates",
}

FRONTMATTER = """---
source_url: {source_url}
doc_number: {doc_number}
effective_from: {effective_from}
expiry_date: {expiry_date}
module: {module}
category: {category}
city: {city}
doc_title: {doc_title}
converted_at: {converted_at}
---

"""


def load_metadata():
    if METADATA_PATH.exists():
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def auto_meta(filename):
    """从文件名自动生成元数据"""
    name = Path(filename).stem
    # 去掉"中华人民共和国"前缀让标题更简洁
    title = name.replace("中华人民共和国", "").strip()
    if not title:
        title = name
    return {
        "doc_title": title,
        "source_url": "",
        "doc_number": "",
        "module": "",
        "category": "tax_law",
        "city": "national",
    }


def get_output_path(meta):
    city = meta.get("city", "national")
    category = meta.get("category", "tax_law")
    if city != "national":
        subdir = f"cities/{city}"
    else:
        subdir = CATEGORY_DIR.get(category, "national")
    safe = re.sub(r'[\\/:*?"<>|]', "_", meta.get("doc_title", "untitled"))[:60]
    return OUTPUT_DIR / subdir / f"{safe}.md"


def build_frontmatter(meta):
    return FRONTMATTER.format(
        source_url=meta.get("source_url", ""),
        doc_number=meta.get("doc_number", ""),
        effective_from=meta.get("effective_from", ""),
        expiry_date=meta.get("expiry_date", ""),
        module=meta.get("module", ""),
        category=meta.get("category", "tax_law"),
        city=meta.get("city", "national"),
        doc_title=meta.get("doc_title", ""),
        converted_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def main():
    parser = argparse.ArgumentParser(
        description="批量转换 PDF → Markdown（使用 Microsoft MarkItDown）"
    )
    parser.add_argument("--input", "-i", type=str, default=str(PDF_DIR))
    parser.add_argument("--output", "-o", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--dry-run", action="store_true", help="预览")
    args = parser.parse_args()

    pdf_dir = Path(args.input)
    if not pdf_dir.exists():
        print(f"❌ 目录不存在: {pdf_dir}")
        return

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"❌ {pdf_dir} 下没有 PDF 文件")
        return

    metadata = load_metadata()
    print(f"📋 元数据: {len(metadata)} 条")
    print(f"📄 PDF: {len(pdfs)} 个\n")

    if args.dry_run:
        print("🔍 预览:\n")
        for p in pdfs:
            meta = metadata.get(p.name, auto_meta(p.name))
            print(f"  {p.name} → {meta['doc_title']}")
        print(f"\n共 {len(pdfs)} 个。去掉 --dry-run 执行转换。")
        return

    print("🚀 开始转换...\n")
    md = MarkItDown()
    ok = fail = 0

    for pdf_file in pdfs:
        print(f"  ⏳ {pdf_file.name} ...", end=" ", flush=True)
        try:
            result = md.convert(str(pdf_file))
            text = result.text_content.strip()

            if len(text) < 100:
                print(f"⚠️ 内容过短（{len(text)} 字符），跳过")
                fail += 1
                continue

            meta = metadata.get(pdf_file.name, auto_meta(pdf_file.name))
            out_path = get_output_path(meta)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(build_frontmatter(meta))
                f.write(text)
                if not text.endswith("\n"):
                    f.write("\n")

            size_kb = len(text) / 1024
            rel = out_path.relative_to(PROJECT_ROOT)
            print(f"✅ → {rel} ({size_kb:.1f} KB)")
            ok += 1

        except Exception as e:
            print(f"❌ {e}")
            fail += 1

    print(f"\n{'='*60}")
    print(f"  完成: ✅ {ok}  |  ❌ {fail}")
    print(f"  输出: {Path(args.output).relative_to(PROJECT_ROOT)}/")


if __name__ == "__main__":
    main()
