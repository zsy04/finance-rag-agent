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
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "finance_knowledge"
BGE_MODEL = "BAAI/bge-m3"
BATCH_SIZE = 32   # 每批编码数量，防止 OOM


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
    """分批编码并写入 Qdrant"""
    total = len(chunks)
    print(f"\n开始向量化 {total} 个 chunk...")

    for start in range(0, total, BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        texts = [c["content"] for c in batch]

        # BGE-M3 双向量编码
        output = model.encode(
            texts,
            batch_size=BATCH_SIZE,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        dense = output["dense_vecs"]     # numpy array [batch, 1024]
        sparse = output["lexical_weights"]  # list of dict {token_id: weight}

        # 构建 Qdrant points
        points = []
        for i, chunk in enumerate(batch):
            sp = sparse[i]
            # 转换为 Qdrant SparseVector 格式
            indices = list(sp.keys())
            values = [float(v) for v in sp.values()]

            point = PointStruct(
                id=start + i,
                vector={
                    "dense": dense[i].tolist(),
                    "sparse": SparseVector(indices=indices, values=values),
                },
                payload={
                    "content": chunk["content"],
                    "doc_title": chunk.get("doc_title", ""),
                    "source_file": chunk.get("source_file", ""),
                    "category": chunk.get("category", ""),
                    "city": chunk.get("city", "national"),
                    "relevance_tier": chunk.get("relevance_tier", ""),
                    "relevance_weight": chunk.get("relevance_weight", 6),
                    "chunk_index": chunk.get("chunk_index", 0),
                },
            )
            points.append(point)

        # 写入 Qdrant
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )

        progress = min(start + BATCH_SIZE, total)
        print(f"  [{progress}/{total}] 已写入", end="\r")

    print(f"\n✅ {total} 个 chunk 全部向量化入库完成")


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
