#!/usr/bin/env python3
"""
BGE-M3 向量化 + Qdrant 入库
============================
读取 chunks.jsonl → BGE-M3 双向量编码（稠密+稀疏）→ Qdrant upsert
"""

import json
import sys
from pathlib import Path
from datetime import datetime

try:
    import numpy as np
    from FlagEmbedding import BGEM3FlagModel
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, SparseVectorParams, PointStruct,
        SparseIndexParams, SparseVector, PayloadSchemaType
    )
except ImportError as e:
    print(f"缺少依赖: {e}")
    print("请运行: pip install FlagEmbedding qdrant-client numpy")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = PROJECT_ROOT / "rag-data" / "chunks.jsonl"
COLBERT_DIR = PROJECT_ROOT / "rag-data" / "colbert"
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "finance_knowledge"
BGE_MODEL = "BAAI/bge-m3"
BATCH_SIZE = 32   # 每批编码数量，防止 OOM

# ── 选择性富化：仅对易混淆文档注入区分性关键词 ─────────
# 这些文档与其他文档在 Embedding 空间中距离过近（共享词根太多），
# 追加关键词后 BGE-M3 的稀疏词汇通道可获得区分信号。
DOC_KEYWORDS: dict[str, str] = {
    # 📌 企税 vs 个税混淆 — 注入"企业""法人"区分信号
    "企业所得税法": "企业所得税法 企业所得税 法人企业 法人",
    # 📌 股权激励 QA 标题 73 字太长 — 注入多角度关键词增强召回 + Reranker 可见
    "个人在一个纳税年度内取得两次或者两项以上股权激励所得，如何计算个人所得税？": "股权激励 股票期权 个人所得税 如何计算 合并计算 两次以上 上市公司 激励所得",
    # 📌 个税APP操作指南 — 内容偏操作流程，语义与政策问答距离远
    # 注意：不含"个人所得税"通用词，避免拉偏年终奖等个税计算类查询
    "个人所得税APP操作指南（2025年度汇算清缴）": "个税APP 退税 申报流程 操作指南 年度汇算 操作步骤",
    # 📌 电子商务法 — "电子发票效力"问题易被向量导向增值税发票而非电商法
    "电子商务法": "电子发票 法律效力 电子签名 数据电文 纸质发票 电子合同",
    # 📌 个人所得税法 — 年终奖计算等高频查询覆盖
    "个人所得税法": "个人所得税 年终奖 全年一次性奖金 单独计税 综合所得 税率表 计算",
}

# ── 权重覆盖：确保特定文档在 Reranker 阶段不被淹没 ────────
# 覆盖 chunks.jsonl 中的默认权重，重嵌时自动生效
WEIGHT_OVERRIDES: dict[str, int] = {
    "个人在一个纳税年度内取得两次或者两项以上股权激励所得，如何计算个人所得税？": 12,
    "个人所得税APP操作指南（2025年度汇算清缴）": 10,
}


def load_chunks():
    """加载切分好的 chunks"""
    chunks = []
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def create_collection(client):
    """创建 Qdrant collection（如已存在则跳过）"""
    if client.collection_exists(COLLECTION_NAME):
        print(f"⚠️  Collection '{COLLECTION_NAME}' 已存在，将追加数据")
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": VectorParams(
                size=1024,           # BGE-M3 dense 维度
                distance=Distance.COSINE,
            )
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(
                index=SparseIndexParams()
            )
        },
    )

    # 创建 payload 索引（加速过滤查询）
    for field in ["category", "city", "relevance_tier"]:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )
    for field in ["relevance_weight"]:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=PayloadSchemaType.INTEGER,
        )

    print(f"✅  Collection '{COLLECTION_NAME}' 创建完成 + payload 索引")


def encode_and_upsert(chunks, model, client):
    """分批编码并写入 Qdrant（带详细进度条）"""
    total = len(chunks)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    batch_count = 0
    t_start = datetime.now()

    # 统计 DOC_KEYWORDS 命中文档
    keyworded_docs = set()
    for c in chunks:
        doc = c.get("doc_title", "")
        if doc in DOC_KEYWORDS:
            keyworded_docs.add(doc)

    print(f"\n{'='*60}")
    print(f"  🚀 开始向量化入库")
    print(f"  {'─'*56}")
    print(f"  总 chunk 数:    {total}")
    print(f"  批次数:         {total_batches}（每批 {BATCH_SIZE} 条）")
    print(f"  DOC_KEYWORDS:   {len(keyworded_docs)} 个文档启用关键词增强")
    for doc in sorted(keyworded_docs):
        kw = DOC_KEYWORDS[doc]
        print(f"    • {doc[:50]}")
        print(f"      → {kw[:80]}{'...' if len(kw) > 80 else ''}")
    print(f"{'='*60}\n")

    for start in range(0, total, BATCH_SIZE):
        batch_count += 1
        t_batch_start = datetime.now()
        batch = chunks[start:start + BATCH_SIZE]
        batch_size = len(batch)
        progress = min(start + BATCH_SIZE, total)

        # ── Step 1: 准备文本（DOC_KEYWORDS 注入） ──
        texts = []
        enriched_count = 0
        for c in batch:
            txt = c["content"]
            doc = c.get("doc_title", "")
            if doc in DOC_KEYWORDS:
                txt = f"{txt} {DOC_KEYWORDS[doc]}"
                enriched_count += 1
            texts.append(txt)

        # ── Step 2: BGE-M3 双向量编码 ──
        pct = progress / total * 100
        bar_len = 30
        filled = int(bar_len * progress / total)
        bar = "█" * filled + "░" * (bar_len - filled)

        elapsed = (datetime.now() - t_start).total_seconds()
        if start > 0:
            eta = elapsed / progress * (total - progress)
            eta_str = f"{eta:.0f}s" if eta < 120 else f"{eta/60:.1f}min"
        else:
            eta_str = "计算中..."

        status = f"🔤 编码中" if enriched_count == 0 else f"🔤 编码中（{enriched_count} 条关键词增强）"
        print(f"  [{bar}] {pct:5.1f}%  |  批次 {batch_count}/{total_batches}  |  "
              f"{progress}/{total} chunks  |  ⏱ {elapsed:.0f}s  |  预计剩余 {eta_str}",
              end="\r")

        output = model.encode(
            texts,
            batch_size=BATCH_SIZE,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        dense = output["dense_vecs"]
        sparse = output["lexical_weights"]

        # ── Step 3: 构建 Qdrant points ──
        print(f"  [{bar}] {pct:5.1f}%  |  批次 {batch_count}/{total_batches}  |  "
              f"{progress}/{total} chunks  |  📦 构建向量点...",
              end="\r")

        points = []
        for i, chunk in enumerate(batch):
            sp = sparse[i]
            indices = list(sp.keys())
            values = [float(v) for v in sp.values()]

            point = PointStruct(
                id=start + i,
                vector={
                    "dense": dense[i].tolist(),
                    "sparse": SparseVector(indices=indices, values=values),
                },
                payload={
                    # 使用含 DOC_KEYWORDS 的富化文本，让 Reranker 也能感知关键词信号
                    "content": texts[i],
                    "doc_title": chunk.get("doc_title", ""),
                    "source_file": chunk.get("source_file", ""),
                    "category": chunk.get("category", ""),
                    "city": chunk.get("city", "national"),
                    "relevance_tier": chunk.get("relevance_tier", ""),
                    "relevance_weight": WEIGHT_OVERRIDES.get(
                        chunk.get("doc_title", ""),
                        chunk.get("relevance_weight", 6)
                    ),
                    "chunk_index": chunk.get("chunk_index", 0),
                },
            )
            points.append(point)

        # ── Step 4: 写入 Qdrant ──
        print(f"  [{bar}] {pct:5.1f}%  |  批次 {batch_count}/{total_batches}  |  "
              f"{progress}/{total} chunks  |  💾 写入 Qdrant...",
              end="\r")

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )

        t_batch = (datetime.now() - t_batch_start).total_seconds()
        print(f"  [{bar}] {pct:5.1f}%  |  批次 {batch_count}/{total_batches}  |  "
              f"{progress}/{total} chunks  |  ✅ 完成 ({t_batch:.1f}s)")

    total_time = (datetime.now() - t_start).total_seconds()
    print(f"\n{'='*60}")
    print(f"  ✅ {total} 个 chunk 全部向量化入库完成")
    print(f"  ⏱  总耗时: {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"  🚀 平均速度: {total/total_time:.1f} chunks/s")
    print(f"{'='*60}")


def main():
    # 加载数据
    if not CHUNKS_FILE.exists():
        print(f"❌ chunks 文件不存在: {CHUNKS_FILE}")
        print("请先运行: python scripts/chunk_docs.py")
        sys.exit(1)

    chunks = load_chunks()
    print(f"📄 加载 {len(chunks)} 个 chunk")

    # 连接 Qdrant
    client = QdrantClient(url=QDRANT_URL)
    print(f"🔗 连接 Qdrant: {QDRANT_URL}")

    # 创建 collection
    create_collection(client)

    # 加载模型（首次会下载 ~2.2GB，后续走缓存）
    print(f"\n⏳ 加载 BGE-M3 模型（首次需下载约 2.2GB）...")
    model = BGEM3FlagModel(
        BGE_MODEL,
        use_fp16=True,          # GPU 半精度，8GB 显存够用
        device="cuda",          # RTX 4060
    )
    print(f"✅ BGE-M3 加载完成")

    # 编码 + 入库
    encode_and_upsert(chunks, model, client)

    # 验证
    count = client.count(COLLECTION_NAME).count
    print(f"\n📊 验证: collection 中现有 {count} 个向量点")


if __name__ == "__main__":
    main()
