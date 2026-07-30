"""
RAG 检索链 — 三层分层召回
===========================
Layer 1: 元数据预过滤（relevance_tier, category, city）
Layer 2: Qdrant 混合检索（dense + sparse → RRF 融合 → Top-30）
Layer 3: BGE-Reranker-v2-m3 Cross-encoder 精排 → Top-5
         + relevance_weight 乘入最终分数

用法:
    from backend.rag.retriever import Retriever
    retriever = Retriever()
    results = retriever.retrieve("租房可以税前扣除多少", top_k=5)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client import models as qdrant_models
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
)

# 项目根路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    QDRANT_URL,
    QDRANT_COLLECTION,
    BGE_MODEL_PATH,
    RERANKER_MODEL_PATH,
)
from rag.query_rewriter import enrich_query


class Retriever:
    """RAG 检索器（单例模式，避免重复加载模型）"""

    _instance: Optional["Retriever"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        print("🔗 连接 Qdrant...")
        self.client = QdrantClient(url=QDRANT_URL)

        print("⏳ 加载 BGE-M3 编码器...")
        from FlagEmbedding import BGEM3FlagModel
        self.encoder = BGEM3FlagModel(
            BGE_MODEL_PATH,
            use_fp16=True,
            device="cuda",
        )

        print("⏳ 加载 Reranker...")
        from FlagEmbedding import FlagReranker
        self.reranker = FlagReranker(
            RERANKER_MODEL_PATH,
            use_fp16=True,
        )
        self._reranker_available = True

        print("✅ Retriever 就绪")

    # ── Layer 1: 元数据预过滤 ───────────────────────────

    @staticmethod
    def _build_filter(
        tier: Optional[str] = None,
        category: Optional[str] = None,
        city: Optional[str] = None,
    ) -> Optional[Filter]:
        """构建 Qdrant payload 过滤条件"""
        conditions = []
        if tier:
            conditions.append(FieldCondition(
                key="relevance_tier", match=MatchValue(value=tier)
            ))
        if category:
            conditions.append(FieldCondition(
                key="category", match=MatchValue(value=category)
            ))
        if city:
            conditions.append(FieldCondition(
                key="city", match=MatchValue(value=city)
            ))
        return Filter(must=conditions) if conditions else None

    # ── Layer 2: Qdrant 混合检索 ────────────────────────

    def _hybrid_search(
        self,
        query: str,
        limit: int = 30,
        query_filter: Optional[Filter] = None,
    ) -> list:
        """
        BGE-M3 双向量编码 → Qdrant 混合检索（dense ANN + sparse 词汇）
        使用 RRF（Reciprocal Rank Fusion）融合两个向量通道的 Top-K 结果。
        """
        # 编码
        output = self.encoder.encode(
            query,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        dense_vec = output["dense_vecs"]  # numpy array
        sparse = output["lexical_weights"]  # dict(单条) or list[dict](批量)

        if isinstance(dense_vec, np.ndarray) and dense_vec.ndim == 2:
            dense_vec = dense_vec[0]

        # 单条查询时 lexical_weights 是 defaultdict, 批量是 list[dict]
        if isinstance(sparse, list):
            sp = sparse[0]
        else:
            sp = sparse

        indices = list(sp.keys())
        values = [float(v) for v in sp.values()]

        # 分两路查询（Qdrant 1.18 prefetch+fusion API 兼容性问题，手动 RRF 融合）
        dense_results = self.client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=dense_vec.tolist(),
            using="dense",
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        ).points

        sparse_results = self.client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=qdrant_models.SparseVector(indices=indices, values=values),
            using="sparse",
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        ).points

        # 手动 RRF 融合
        rrf_k = 60  # RRF 常数
        scores: dict[int, float] = {}
        id_to_point: dict[int, any] = {}
        for rank, p in enumerate(dense_results):
            scores[p.id] = scores.get(p.id, 0) + 1.0 / (rrf_k + rank + 1)
            id_to_point[p.id] = p
        for rank, p in enumerate(sparse_results):
            scores[p.id] = scores.get(p.id, 0) + 1.0 / (rrf_k + rank + 1)
            id_to_point[p.id] = p

        # 按 RRF 分数排序返回
        sorted_ids = sorted(scores, key=scores.get, reverse=True)[:limit]
        return [id_to_point[pid] for pid in sorted_ids]

    # ── Layer 3: Reranker 精排 + relevance_weight 加权 ──

    def _rerank_and_weight(
        self,
        query: str,
        points: list,
        top_k: int = 5,
    ) -> list[dict]:
        """用 Reranker 对候选集精排，再乘以 relevance_weight"""
        if not points:
            return []

        # 准备候选文本
        candidates = [p.payload.get("content", "") for p in points]
        pairs = [[query, text] for text in candidates]

        # Reranker 打分
        rerank_ok = False
        rerank_scores = []
        try:
            import torch
            inputs = self.reranker.tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=1024,       # BGE-Reranker-v2-m3 原生支持 8192，1024 留足余量
                return_tensors="pt",
            ).to(self.reranker.model.device)
            with torch.no_grad():
                logits = self.reranker.model(**inputs).logits.squeeze(-1)
            rerank_scores_raw = logits.cpu().tolist()
            if isinstance(rerank_scores_raw, float):
                rerank_scores_raw = [rerank_scores_raw]
            rerank_scores = rerank_scores_raw
            rerank_ok = True
        except Exception:
            import logging
            logging.warning(
                "Reranker 调用失败，降级为 relevance_weight 纯排序。"
                "请检查 BGE-Reranker 模型是否正确加载。"
            )

        # ── 结果整理 ──
        ranked = []

        if rerank_ok:
            # 正常路径：rerank_score × relevance_weight
            min_s = min(rerank_scores)
            max_s = max(rerank_scores)
            score_range = max_s - min_s if max_s > min_s else 1.0

            for i, (point, score) in enumerate(zip(points, rerank_scores)):
                normalized = (score - min_s) / score_range
                weight = float(point.payload.get("relevance_weight", 6))
                final_score = normalized * (weight / 10.0)

                ranked.append({
                    "content": point.payload.get("content", ""),
                    "doc_title": point.payload.get("doc_title", ""),
                    "source_file": point.payload.get("source_file", ""),
                    "relevance_tier": point.payload.get("relevance_tier", ""),
                    "category": point.payload.get("category", ""),
                    "rerank_score": round(normalized, 4),
                    "relevance_weight": weight,
                    "final_score": round(final_score, 4),
                })
        else:
            # 降级路径：仅用 relevance_weight 排序（保留层级信号）
            for point in points:
                weight = float(point.payload.get("relevance_weight", 6))
                ranked.append({
                    "content": point.payload.get("content", ""),
                    "doc_title": point.payload.get("doc_title", ""),
                    "source_file": point.payload.get("source_file", ""),
                    "relevance_tier": point.payload.get("relevance_tier", ""),
                    "category": point.payload.get("category", ""),
                    "rerank_score": 0.0,
                    "relevance_weight": weight,
                    "final_score": round(weight / 10.0, 4),
                })

        # 按 final_score 降序排列
        ranked.sort(key=lambda x: x["final_score"], reverse=True)
        return ranked[:top_k]

    # ── 公共接口 ────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        tier_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        city_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        完整检索链路: 过滤 → 混合检索 → 精排加权

        Args:
            query: 用户问题
            top_k: 返回结果数（默认 5）
            tier_filter: 相关性层级过滤（tax_law / tax_regulation / qa_corpus / general_law）
            category_filter: 分类过滤（tax_law / qa_corpus）
            city_filter: 城市过滤（national / zhengzhou）

        Returns:
            [{content, doc_title, source_file, relevance_tier, rerank_score,
              relevance_weight, final_score}, ...]
        """
        # Query 改写：口语→法条术语标准化（如 "五险一金" → "社会保险 住房公积金"）
        enriched_query = enrich_query(query)

        # Layer 1
        q_filter = self._build_filter(tier_filter, category_filter, city_filter)

        # Layer 2
        points = self._hybrid_search(enriched_query, limit=30, query_filter=q_filter)

        # Layer 3
        results = self._rerank_and_weight(query, points, top_k=top_k)

        return results


# ── 便捷函数（供 Agent @tool 直接调用） ─────────────────

_retriever: Optional[Retriever] = None


def get_retriever() -> Retriever:
    """获取 Retriever 单例"""
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def search_knowledge(
    query: str,
    top_k: int = 5,
    tier: Optional[str] = None,
) -> list[dict]:
    """
    Agent 工具: 智能问答检索
    用法: search_knowledge(query="租房扣除标准", tier="tax_regulation")
    """
    return get_retriever().retrieve(query, top_k=top_k, tier_filter=tier)


# ── 自检 ───────────────────────────────────────────────

if __name__ == "__main__":
    r = get_retriever()

    print("=== 测试 1: 租房扣除 ===")
    for item in r.retrieve("租房可以税前扣除多少"):
        print(f"  [{item['relevance_tier']}] {item['doc_title']}")
        print(f"    rerank={item['rerank_score']:.4f} weight={item['relevance_weight']} final={item['final_score']:.4f}")

    print("\n=== 测试 2: 增值税税率（仅 tax_law）===")
    for item in r.retrieve("增值税税率是多少", tier_filter="tax_law"):
        print(f"  [{item['relevance_tier']}] {item['doc_title']} final={item['final_score']:.4f}")
