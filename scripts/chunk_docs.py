#!/usr/bin/env python3
"""
RAG 文档切分脚本
================
读取 processed/ 下的所有 Markdown 文件，按 grill-me 决议的参数切分：
  - 税法: ### 第X条 边界，上限 800 字/下限 80 字/重叠 120 字(15%)
  - QA:   ## 问句 边界，同上参数
  - 不跨条目合并（下限仅用于条目内子 chunk）
  - 每个 chunk 继承 YAML frontmatter 元数据作为 payload

输出: chunks.jsonl（每行一个 JSON 对象，含 content + metadata）
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

try:
    from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
except ImportError:
    print("请先安装: pip install langchain-text-splitters")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "rag-data" / "processed" / "national"
OUTPUT_FILE = PROJECT_ROOT / "rag-data" / "chunks.jsonl"

# grill-me 决议参数
CHUNK_SIZE = 800        # 上限（字）
CHUNK_OVERLAP = 120     # 重叠（15%）
CHUNK_LOWER = 80        # 下限（低于此不合并，保留独立 chunk）


def parse_frontmatter(text):
    """提取 YAML frontmatter 和正文"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text

    end = None
    for i in range(1, min(len(lines), 30)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text

    yaml_text = "\n".join(lines[1:end])
    meta = {}
    for line in yaml_text.strip().split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            meta[key] = val

    body = "\n".join(lines[end + 1:])
    return meta, body


def chunk_tax_law(text, meta):
    """税法案条目级切分"""
    headers_to_split = [
        ("##", "chapter"),
        ("###", "article"),
    ]
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split,
        strip_headers=False,
    )

    # 先用标题切分
    md_chunks = splitter.split_text(text)

    # 对过长的 chunk 按字符补充切割
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )

    chunks = []
    for md_chunk in md_chunks:
        content = md_chunk.page_content.strip()
        if len(content) <= CHUNK_SIZE:
            chunks.append(content)
        else:
            sub_chunks = char_splitter.split_text(content)
            # 过滤短尾巴：如果最后一个子 chunk < 80字，合并到前一个
            if len(sub_chunks) >= 2 and len(sub_chunks[-1]) < CHUNK_LOWER:
                sub_chunks[-2] = sub_chunks[-2] + sub_chunks[-1]
                sub_chunks.pop()
            chunks.extend(sub_chunks)

    # 构建 payload
    results = []
    for i, chunk_text in enumerate(chunks):
        chunk_text = chunk_text.strip()
        if not chunk_text or len(chunk_text) < CHUNK_LOWER:
            continue
        payload = {
            "content": chunk_text,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "source_file": meta.get("source_url", ""),
            "doc_title": meta.get("doc_title", ""),
            "category": meta.get("category", "tax_law"),
            "city": meta.get("city", "national"),
            "relevance_tier": meta.get("relevance_tier", "tax_law"),
            "relevance_weight": int(meta.get("relevance_weight", 10)),
            "chunked_at": datetime.now().isoformat(),
        }
        results.append(payload)
    return results


def chunk_qa(text, meta):
    """QA 问答按 ## 问句切分"""
    headers_to_split = [
        ("#", "title"),
        ("##", "question"),
    ]
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split,
        strip_headers=False,
    )
    md_chunks = splitter.split_text(text)

    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )

    chunks = []
    for md_chunk in md_chunks:
        content = md_chunk.page_content.strip()
        if not content or content.startswith("# "):
            continue  # 跳过纯标题行
        if len(content) <= CHUNK_SIZE:
            chunks.append(content)
        else:
            sub_chunks = char_splitter.split_text(content)
            if len(sub_chunks) >= 2 and len(sub_chunks[-1]) < CHUNK_LOWER:
                sub_chunks[-2] = sub_chunks[-2] + sub_chunks[-1]
                sub_chunks.pop()
            chunks.extend(sub_chunks)

    results = []
    for i, chunk_text in enumerate(chunks):
        chunk_text = chunk_text.strip()
        if not chunk_text or len(chunk_text) < CHUNK_LOWER:
            continue
        payload = {
            "content": chunk_text,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "source_file": meta.get("source_url", ""),
            "doc_title": meta.get("doc_title", ""),
            "category": meta.get("category", "qa_corpus"),
            "city": meta.get("city", "national"),
            "relevance_tier": meta.get("relevance_tier", "qa_corpus"),
            "relevance_weight": int(meta.get("relevance_weight", 6)),
            "chunked_at": datetime.now().isoformat(),
        }
        results.append(payload)
    return results


def main():
    tax_law_dir = DATA_DIR / "tax_law"
    qa_dir = DATA_DIR / "qa_corpus"
    ops_dir = DATA_DIR / "operations"

    all_chunks = []
    stats = {"tax_law": 0, "qa_corpus": 0, "operations": 0}

    # 处理税法
    for md_file in sorted(tax_law_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        chunks = chunk_tax_law(body, meta)
        all_chunks.extend(chunks)
        stats["tax_law"] += len(chunks)
        print(f"  ✓ tax_law/{md_file.name}: {len(chunks)} chunks")

    # 处理 QA
    for md_file in sorted(qa_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        chunks = chunk_qa(body, meta)
        all_chunks.extend(chunks)
        stats["qa_corpus"] += len(chunks)
        print(f"  ✓ qa_corpus/{md_file.name}: {len(chunks)} chunks")

    # 处理操作指引
    if ops_dir.exists():
        for md_file in sorted(ops_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            chunks = chunk_qa(body, meta)  # 复用 QA 切分逻辑
            all_chunks.extend(chunks)
            stats["operations"] += len(chunks)
            print(f"  ✓ operations/{md_file.name}: {len(chunks)} chunks")

    # 写入
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    total = sum(stats.values())
    print(f"\n{'='*50}")
    print(f"  总 chunks: {total}")
    print(f"  tax_law: {stats['tax_law']}, qa_corpus: {stats['qa_corpus']}, operations: {stats['operations']}")
    print(f"  输出: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
