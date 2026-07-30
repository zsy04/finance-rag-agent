#!/usr/bin/env python3
"""
QA 文档修复：给缺少 ## 标题的 QA 文档添加二级标题
====================================================
将 "数字、" 或 "数字．" 开头的问答行转为 "## 数字、" 格式，
确保 MarkdownHeaderTextSplitter 能按 QA 边界正确切分。

用法:
    python scripts/fix_qa_headings.py          # 预览改动
    python scripts/fix_qa_headings.py --apply  # 执行写入
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QA_DIR = PROJECT_ROOT / "rag-data" / "processed" / "national" / "qa_corpus"


def fix_file(filepath: Path, apply: bool = False) -> tuple[int, str]:
    """修复单个文件，返回 (修复条数, 状态)"""
    with open(filepath, "r", encoding="utf-8") as f:
        original = f.read()

    if original.count("---") < 2:
        return 0, "跳过（无 frontmatter）"

    # 分离 frontmatter 和 body
    parts = original.split("---", 2)
    fm = parts[1]
    body = parts[2]

    # 检查 body 中是否已有 ## 标题
    if re.search(r"^##\s", body, re.MULTILINE):
        return 0, "跳过（已有 ## 标题）"

    # 修复模式：行首 数字+、 或 数字+． → ## 数字+、
    fixed_body, count = re.subn(
        r"^(\d+)([、．])",
        r"## \1、",
        body,
        flags=re.MULTILINE,
    )

    if count == 0:
        # 尝试 ### → ## 保底修复（如股权激励单篇）
        fixed_body, count = re.subn(
            r"^###\s+",
            "## ",
            body,
            flags=re.MULTILINE,
        )
        if count == 0:
            return 0, "跳过（无匹配编号）"

    if apply:
        result = f"---{fm}---\n{fixed_body}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result)

    return count, f"{'✅ 已修复' if apply else '🔍 预览'}（{count} 条）"


def main():
    apply = "--apply" in sys.argv

    if not QA_DIR.exists():
        print(f"❌ 目录不存在: {QA_DIR}")
        sys.exit(1)

    total_fixed = 0
    files_fixed = 0

    for md_file in sorted(QA_DIR.glob("*.md")):
        count, status = fix_file(md_file, apply=apply)
        if count > 0:
            files_fixed += 1
            total_fixed += count
        print(f"  {status:30s} {md_file.name}")

    print(f"\n{'='*50}")
    if apply:
        print(f"  已修复 {files_fixed} 个文件，共 {total_fixed} 条 QA 问答")
        print(f"  下一步：重新切分 → 重新嵌入")
        print(f"    python scripts/chunk_docs.py")
        print(f"    python scripts/embed_and_upsert.py")
    else:
        print(f"  预览 {files_fixed} 个文件，共 {total_fixed} 条待修复")
        print(f"  执行写入：python scripts/fix_qa_headings.py --apply")


if __name__ == "__main__":
    main()
