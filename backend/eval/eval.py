"""
RAG 检索评测脚本
================
加载 eval_set.json → 逐条调用 retriever → 计算 recall@k / MRR / NDCG → 输出报告

用法:
    cd backend
    python eval/eval.py              # 完整评测
    python eval/eval.py --category 个税   # 按分类评测
    python eval/eval.py --verbose          # 逐条打印详情
"""

from __future__ import annotations

import json
import sys
import time
import argparse
from pathlib import Path
from collections import defaultdict

# 确保可以 import backend 模块
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from rag.retriever import get_retriever


# ── 指标计算 ──────────────────────────────────────────

def recall_at_k(expected: set[str], retrieved: list[str], k: int) -> float:
    """期望文档中有多大比例（去重后）出现在 top-k 中"""
    if not expected:
        return 1.0
    # 去重：同一文档的多个 chunk 只计一次命中
    found = set()
    for doc in retrieved[:k]:
        for exp in expected:
            if exp in doc:
                found.add(exp)
    return len(found) / len(expected)


def precision_at_k(expected: set[str], retrieved: list[str], k: int) -> float:
    """top-k 中有多大比例命中了期望文档（去重）"""
    if k == 0:
        return 0.0
    found = set()
    for doc in retrieved[:k]:
        for exp in expected:
            if exp in doc:
                found.add(exp)
    # precision = 唯一命中数 / k（但 capped at 1.0）
    return min(len(found), k) / k


def mrr(expected: set[str], retrieved: list[str]) -> float:
    """Mean Reciprocal Rank：第一个命中期盼文档的排名的倒数"""
    for rank, doc in enumerate(retrieved, 1):
        for exp in expected:
            if exp in doc:
                return 1.0 / rank
    return 0.0


def ndcg_at_k(expected: set[str], retrieved: list[str], k: int) -> float:
    """
    Normalized Discounted Cumulative Gain。
    命中 = 1，未命中 = 0（简化版，不区分部分相关度）。
    """
    import math
    seen: set[str] = set()
    dcg = 0.0
    for i, doc in enumerate(retrieved[:k]):
        rel = 0
        for exp in expected:
            if exp in doc and exp not in seen:
                rel = 1
                seen.add(exp)
                break
        dcg += rel / math.log2(i + 2)  # i+2 因为 log2(1)=0

    # IDCG: 理想情况下所有期望文档都排在最前面
    n_expected = len(expected)
    ideal_rels = [1] * n_expected + [0] * max(0, k - n_expected)
    idcg = 0.0
    for i, rel in enumerate(ideal_rels[:k]):
        idcg += rel / math.log2(i + 2)

    return dcg / idcg if idcg > 0 else 0.0


# ── 评测主逻辑 ────────────────────────────────────────

def run_eval(
    eval_set: list[dict],
    retriever,
    top_k: int = 5,
    verbose: bool = False,
) -> dict:
    """运行完整评测，返回指标汇总"""
    results = []
    metrics = {
        "recall@1": [], "recall@3": [], "recall@5": [],
        "precision@1": [], "precision@3": [], "precision@5": [],
        "mrr": [], "ndcg@5": [],
    }
    by_category: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "passed": 0, "recall@5": [],
    })

    total = len(eval_set)
    start_time = time.time()

    for i, item in enumerate(eval_set):
        query = item["query"]
        expected = set(item["expected_docs"])
        category = item.get("category", "未分类")

        # 检索
        res = retriever.retrieve(query, top_k=top_k)
        retrieved_titles = [r.get("doc_title", "") for r in res]

        # 计算本条指标
        r1 = recall_at_k(expected, retrieved_titles, 1)
        r3 = recall_at_k(expected, retrieved_titles, 3)
        r5 = recall_at_k(expected, retrieved_titles, 5)
        p1 = precision_at_k(expected, retrieved_titles, 1)
        p3 = precision_at_k(expected, retrieved_titles, 3)
        p5 = precision_at_k(expected, retrieved_titles, 5)
        m = mrr(expected, retrieved_titles)
        n5 = ndcg_at_k(expected, retrieved_titles, 5)

        metrics["recall@1"].append(r1)
        metrics["recall@3"].append(r3)
        metrics["recall@5"].append(r5)
        metrics["precision@1"].append(p1)
        metrics["precision@3"].append(p3)
        metrics["precision@5"].append(p5)
        metrics["mrr"].append(m)
        metrics["ndcg@5"].append(n5)

        passed = r5 > 0
        by_category[category]["total"] += 1
        by_category[category]["passed"] += 1 if passed else 0
        by_category[category]["recall@5"].append(r5)

        results.append({
            "id": item["id"],
            "query": query,
            "category": category,
            "expected": list(expected),
            "retrieved": retrieved_titles[:5],
            "scores": [round(r.get("final_score", 0), 4) for r in res[:5]],
            "recall@5": round(r5, 2),
            "mrr": round(m, 4),
        })

        if verbose:
            status = "✅" if passed else "❌"
            print(f"\n[{status}] #{item['id']} [{category}] {query}")
            print(f"    期望: {', '.join(expected)}")
            for j, (t, s) in enumerate(zip(retrieved_titles[:5], [r.get('final_score',0) for r in res[:5]]), 1):
                marker = " ★" if any(exp in t for exp in expected) else ""
                print(f"    {j}. [{s:.4f}] {t}{marker}")

        # 进度条
        pct = (i + 1) / total * 100
        print(f"\r  [{i+1}/{total}] {pct:.0f}%", end="", flush=True)

    elapsed = time.time() - start_time
    print(f"\r  [{total}/{total}] 100%  耗时 {elapsed:.1f}s\n")

    # ── 汇总 ──
    summary = {}
    for key, values in metrics.items():
        summary[key] = round(sum(values) / len(values), 4) if values else 0.0

    # 失败 case
    failed = [r for r in results if r["recall@5"] == 0]

    return {
        "summary": summary,
        "by_category": {
            cat: {
                "total": v["total"],
                "passed": v["passed"],
                "pass_rate": round(v["passed"] / v["total"], 2) if v["total"] else 0,
                "avg_recall@5": round(sum(v["recall@5"]) / len(v["recall@5"]), 4),
            }
            for cat, v in sorted(by_category.items())
        },
        "failed": failed,
        "total_queries": total,
        "elapsed_seconds": round(elapsed, 1),
    }


def print_report(report: dict):
    """格式化打印评测报告"""

    s = report["summary"]
    bc = report["by_category"]

    print("=" * 60)
    print("  RAG 检索评测报告")
    print("=" * 60)
    print(f"  总查询数: {report['total_queries']}")
    print(f"  总耗时:   {report['elapsed_seconds']}s")
    print()

    # 核心指标
    print("  ── 核心指标 ──")
    print(f"  Recall@1:    {s['recall@1']:.2%}")
    print(f"  Recall@3:    {s['recall@3']:.2%}")
    print(f"  Recall@5:    {s['recall@5']:.2%}")
    print(f"  Precision@5: {s['precision@5']:.2%}")
    print(f"  MRR:         {s['mrr']:.4f}")
    print(f"  NDCG@5:      {s['ndcg@5']:.4f}")
    print()

    # 按分类
    print("  ── 按分类 ──")
    print(f"  {'分类':<16} {'数量':>4} {'通过':>4} {'通过率':>8} {'Avg R@5':>8}")
    print(f"  {'-'*44}")
    for cat, v in bc.items():
        print(f"  {cat:<16} {v['total']:>4} {v['passed']:>4} {v['pass_rate']:>7.0%} {v['avg_recall@5']:>8.2%}")
    print()

    # 失败明细
    failed = report["failed"]
    if failed:
        print(f"  ── 未命中 (recall@5 = 0) — {len(failed)} 条 ──")
        for f in failed:
            print(f"  ❌ #{f['id']} [{f['category']}] {f['query']}")
            print(f"     期望: {', '.join(f['expected'])}")
            print(f"     实际 top-3:")
            for j, (t, sc) in enumerate(zip(f['retrieved'][:3], f['scores'][:3]), 1):
                print(f"       {j}. [{sc}] {t}")
            print()
    else:
        print("  🎉 全部命中！")

    print("=" * 60)


# ── CLI ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAG 检索评测")
    parser.add_argument("--eval-set", default="eval/eval_set.json",
                        help="评测集 JSON 路径（相对于 backend/）")
    parser.add_argument("--category", default=None,
                        help="按分类过滤（如 '个税'）")
    parser.add_argument("--top-k", type=int, default=5,
                        help="检索返回数")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="逐条打印详情")
    parser.add_argument("--output", "-o", default=None,
                        help="输出 JSON 报告路径")
    args = parser.parse_args()

    # 加载评测集
    eval_path = BACKEND_DIR / args.eval_set
    if not eval_path.exists():
        print(f"❌ 评测集文件不存在: {eval_path}")
        sys.exit(1)

    with open(eval_path, "r", encoding="utf-8") as f:
        eval_set = json.load(f)

    if args.category:
        eval_set = [item for item in eval_set if args.category in item.get("category", "")]
        print(f"按分类过滤 [{args.category}]: {len(eval_set)} 条\n")

    # 初始化检索器
    print("⏳ 加载检索器（首次需加载 BGE-M3 + Reranker 模型）...")
    retriever = get_retriever()
    print()

    # 运行评测
    report = run_eval(eval_set, retriever, top_k=args.top_k, verbose=args.verbose)

    # 打印报告
    print_report(report)

    # 可选：导出 JSON
    if args.output:
        out_path = BACKEND_DIR / args.output
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n📄 报告已导出: {out_path}")


if __name__ == "__main__":
    main()
