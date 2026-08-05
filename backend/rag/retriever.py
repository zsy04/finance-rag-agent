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

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

# 必须在 import qdrant_client / FlagEmbedding 等任何间接依赖 HuggingFace 的模块之前设置，
# 否则模型加载会触发网络请求。transformers 5.x 的 from_pretrained 即使本地缓存完整
# 也会强制 list_repo_templates() 联网检查（离线时 ConnectTimeout 卡 10-30 秒），
# 因此需同时设 HF_HUB_OFFLINE + TRANSFORMERS_OFFLINE 双保险。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

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
    EMBEDDING_DEVICE,
)
from rag.query_rewriter import enrich_query

# 关系索引路径
RELATIONS_PATH = PROJECT_ROOT.parent / "rag-data" / "relations.json"

logger = logging.getLogger(__name__)


def _detect_device() -> str:
    """根据配置检测设备：EMBEDDING_DEVICE 可选 auto/cpu/cuda"""
    if EMBEDDING_DEVICE == "cpu":
        return "cpu"
    if EMBEDDING_DEVICE == "cuda":
        return "cuda"
    # auto: 自动检测
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class Retriever:
    """RAG 检索器（懒加载单例，通过 get_retriever() 获取）"""

    def __init__(self):
        logger.info("🔗 连接 Qdrant...")
        self.client = QdrantClient(url=QDRANT_URL)

        device = _detect_device()
        use_fp = (device == "cuda")  # fp16 仅 GPU 可用，CPU 用 fp32
        logger.info("⏳ 加载 BGE-M3 编码器 (device=%s, fp16=%s)...", device, use_fp)
        from FlagEmbedding import BGEM3FlagModel
        self.encoder = BGEM3FlagModel(
            BGE_MODEL_PATH,
            use_fp16=use_fp,
            device=device,
        )

        logger.info("⏳ 加载 Reranker (device=%s)...", device)
        from FlagEmbedding import FlagReranker
        self.reranker = FlagReranker(
            RERANKER_MODEL_PATH,
            use_fp16=use_fp,
        )
        self._reranker_available = True

        logger.info("✅ Retriever 就绪")

        # 加载关系索引
        self.relations = self._load_relations()

    def _load_relations(self) -> list[dict]:
        """加载轻量关系索引（JSON 格式）"""
        import json
        if not RELATIONS_PATH.exists():
            logger.warning("关系索引文件不存在: %s", RELATIONS_PATH)
            return []
        with open(RELATIONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("🔗 加载关系索引: %d 条关联规则", len(data))
        return data

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
        id_to_point: dict[int, Any] = {}
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
        except (RuntimeError, OSError, ValueError) as e:
            # 仅捕获运行时/IO/数值异常（如 CUDA OOM、模型文件损坏），
            # 让 AttributeError/TypeError/KeyError 等编程错误正常抛出便于定位
            logger.warning(
                "Reranker 调用失败，降级为 relevance_weight 纯排序。"
                "请检查 BGE-Reranker 模型是否正确加载。原因: %s", e,
                exc_info=True,
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

    def _expand_relations(
        self,
        query: str,
        primary_results: list[dict],
        max_additional: int = 3,
    ) -> list[dict]:
        """
        轻量知识图谱扩展 — 支持双向遍历 + 两跳推理

        1. 正向: 主结果中的文档作为 source → 拉 target
        2. 逆向: 主结果中的文档作为 target → 反推 source
        3. 二跳: 第一跳找到的 target 再作为 source 拉下一层（最多 2 跳）

        Args:
            query: 用户原始 query（用于关键词匹配）
            primary_results: 主检索结果
            max_additional: 最多补充条数

        Returns:
            补充的关联文档列表（含 relation_source + relation_hop 标记）
        """
        if not self.relations:
            return []

        hit_titles = {r.get("doc_title", "") for r in primary_results}
        all_found = set(hit_titles)  # 避免重复拉取

        def _matches_query_keywords(rel: dict) -> bool:
            """检查 query 是否含触发关键词（无触发词则默认激活）"""
            keywords = rel.get("trigger_keywords", [])
            if not keywords:
                return True  # 无触发词 = 始终激活
            return any(kw in query for kw in keywords)

        # ── 第一跳：正向 + 逆向 ──
        triggered = []

        for rel in self.relations:
            # 正向：主结果中的文档 == source
            if any(rel["source"] in title for title in hit_titles):
                if _matches_query_keywords(rel):
                    triggered.append((rel, 1))
                    continue

            # 逆向：主结果中的文档 == target → 反向激活 source
            if any(rel["target"] in title for title in hit_titles):
                # 创建反向关系
                reverse_rel = {
                    "source": rel["target"],
                    "target": rel["source"],
                    "relation": f"reverse_{rel['relation']}",
                    "trigger_keywords": rel.get("trigger_keywords", []),
                    "description": f"被 {rel['target']} 引用（逆向关联）",
                }
                if _matches_query_keywords(reverse_rel):
                    triggered.append((reverse_rel, 1))

        # ── 去重第一跳目标 ──
        hop1_targets = set()
        hop1_map = {}  # target → list of (rel, hop)
        for rel, hop in triggered:
            t = rel["target"]
            if t not in all_found:
                hop1_targets.add(t)
                if t not in hop1_map:
                    hop1_map[t] = []
                hop1_map[t].append((rel, hop))

        # ── 第二跳：一阶 target 作为新的 source ──
        for rel in self.relations:
            for t in hop1_targets:
                if rel["source"] in t and rel["target"] not in all_found:
                    if _matches_query_keywords(rel):
                        hop2_target = rel["target"]
                        if hop2_target not in hop1_targets:
                            if hop2_target not in hop1_map:
                                hop1_map[hop2_target] = []
                            hop1_map[hop2_target].append((rel, 2))

        # ── 拉取文档 ──
        all_targets = list(hop1_map.keys())[:max_additional + 2]  # 留余量
        additional = []
        fetched = 0

        for target in all_targets:
            if fetched >= max_additional:
                break
            points, _ = self.client.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(
                        key="doc_title",
                        match=MatchValue(value=target),
                    )]
                ),
                limit=2,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                continue

            rels_for_target = hop1_map.get(target, [])
            source_desc = rels_for_target[0][0].get("description", "")
            hop = rels_for_target[0][1] if rels_for_target else 1

            for p in points:
                additional.append({
                    "content": p.payload.get("content", ""),
                    "doc_title": p.payload.get("doc_title", ""),
                    "source_file": p.payload.get("source_file", ""),
                    "relevance_tier": p.payload.get("relevance_tier", ""),
                    "category": p.payload.get("category", ""),
                    "rerank_score": 0.0,
                    "relevance_weight": p.payload.get("relevance_weight", 6),
                    "final_score": 0.0,
                    "relation_source": f"知识图谱（{hop}跳）",
                    "relation_desc": source_desc,
                })
            fetched += 1

        return additional

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        tier_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        city_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        完整检索链路: 过滤 → 混合检索 → 精排加权 → 关系扩展

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

        # Layer 3：Reranker 精排（放宽取 top_k*2，为 Layer 4 的文档级去重留出冗余槽位）
        results = self._rerank_and_weight(query, points, top_k=top_k * 2)

        # Layer 4: 关系索引扩展（关联法规）
        if self.relations:
            additional = self._expand_relations(query, results)
            if additional:
                results = results + additional

        # 文档级去重：同一 doc_title 只保留最高分 chunk，避免超长法规多 chunk 挤占 top-k 槽位
        # （长文档切分多 chunk 后，Reranker 可能让同一文档占满结果列表）
        deduped: list[dict] = []
        seen_titles: set[str] = set()
        for r in results:
            title = r.get("doc_title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)
            deduped.append(r)

        return deduped[:top_k]


# ── 便捷函数（供 Agent @tool 直接调用） ─────────────────

_retriever: Optional[Retriever] = None
_retriever_lock = threading.Lock()


def get_retriever() -> Retriever:
    """获取 Retriever 单例（线程安全，唯一入口）"""
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            # 双重检查，避免多线程下重复加载模型
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    r = get_retriever()

    logger.info("=== 测试 1: 租房扣除 ===")
    for item in r.retrieve("租房可以税前扣除多少"):
        logger.info("  [%s] %s", item['relevance_tier'], item['doc_title'])
        logger.info("    rerank=%.4f weight=%s final=%.4f",
                    item['rerank_score'], item['relevance_weight'], item['final_score'])

    logger.info("=== 测试 2: 增值税税率（仅 tax_law）===")
    for item in r.retrieve("增值税税率是多少", tier_filter="tax_law"):
        logger.info("  [%s] %s final=%.4f", item['relevance_tier'], item['doc_title'], item['final_score'])
