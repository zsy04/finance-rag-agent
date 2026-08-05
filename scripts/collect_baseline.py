"""
基线采集自动化执行器
====================
一条命令完成 P0-0 基线采集五步：
  ① 加载长对话场景（gen_long_dialogues.SCENARIOS）
  ② 逐轮跑真实 Agent，记录每轮历史 token（曲线）
  ③ 启发式建议 trigger 触发阈值
  ④ 模拟摘要 + probe 问答 + 关键事实自动判定
  ⑤ keep 三档对比（10/20/30），定推荐值
产出：eval/dialog_baseline.json + 终端报告

前置：Qdrant 容器运行中 + backend/.env 配置 DEEPSEEK_API_KEY
用法（在 backend 目录下）:
    venv/Scripts/python.exe ../scripts/collect_baseline.py --dry-run     # 链路验证（1 场景 3 轮）
    venv/Scripts/python.exe ../scripts/collect_baseline.py               # 全量采集
    venv/Scripts/python.exe ../scripts/collect_baseline.py --limit-turns 10 --keep "10,20"
"""

from __future__ import annotations

import argparse
import json
import os  # noqa: F401  (环境变量必须在任何第三方 import 之前设置)
import re
import sys
import time

# ⚠️⚠️ 必须在任何第三方 import 之前执行（huggingface_hub.constants 在 import 时
# 快照 HF_ENDPOINT/offline 标志，事后设置一律无效——retriever.py 顶部设置太晚，
# 因为 agent.engine → langchain 链会提前把 hf_hub 拉进内存）：
#   ① 国内镜像 hf-mirror.com：网络到不了 huggingface.co 时兜底
#   ② 双 offline：transformers 5.x 即使本地缓存完整也会强制 list_repo_templates()
#      联网检查（ConnectTimeout 卡 10-30 秒/次，实测踩坑）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from gen_long_dialogues import SCENARIOS  # noqa: E402

# 摘要 prompt（与集成设计文档 v2 §3.4 一致）
SUMMARY_PROMPT = """你是对话历史摘要器。将以下多轮对话压缩为 300 字以内的摘要。
必须逐项保留（若对话中出现过）：用户所在城市、月薪/年薪、收入类型、
所有专项附加扣除项及其金额、社保公积金信息、已办理或询问过的业务。
其余内容按信息价值取舍，闲聊与寒暄一律删除。
只输出摘要正文，不要任何解释。
--- 对话 ---
{messages}"""

# 关键事实 → probe 问题（中文标签）
FACT_LABELS = {
    "city": "所在城市",
    "salary": "月薪/工资",
    "income_type": "收入类型",
    "housing_rent": "租房扣除额",
    "children_edu": "子女教育扣除额",
    "elderly_support": "赡养老人扣除额",
    "previous_loss": "上年亏损金额",
    "business_name": "店铺名称",
    "deduction_mortgage": "房贷利息扣除额",
}

# 数值型字段（用词边界正则匹配，防子串误判如 1500 ⊂ 15000）
NUMERIC_FACTS = {"salary", "housing_rent", "children_edu", "elderly_support",
                 "previous_loss", "deduction_mortgage"}


def est_tokens(text: str) -> int:
    """中文 token 估算：1 字 ≈ 1.75 token（与 token_est.py 口径一致）"""
    return max(1, int(len(text) * 1.75))


def messages_to_text(messages) -> str:
    return "\n".join(
        f"{getattr(m, 'type', 'msg')}: {m.content}"
        for m in messages if getattr(m, "content", None)
    )


def summarize_messages(llm, messages) -> tuple[str, int]:
    """LLM 摘要旧消息，返回 (摘要文本, 摘要token数)"""
    text = messages_to_text(messages)
    resp = llm.invoke(SUMMARY_PROMPT.format(messages=text))
    summary = resp.content.strip()
    return summary, est_tokens(summary)


def check_fact_in_answer(fact_key: str, expected: str, answer: str) -> bool:
    """判定 probe 回答是否包含期望事实。数值型用词边界，字符串型用包含匹配"""
    expected = str(expected).strip()
    answer = (answer or "").strip()
    if not answer:
        return False
    if fact_key in NUMERIC_FACTS:
        return bool(re.search(rf"(?<!\d){re.escape(expected)}(?!\d)", answer))
    return expected in answer


def probe_facts(llm, context_text: str, facts: dict) -> dict:
    """对每条关键事实发 probe 问题，返回命中情况"""
    results = {}
    for key, value in facts.items():
        label = FACT_LABELS.get(key, key)
        prompt = (
            f"以下是此前对话的上下文（可能是摘要+最近几条消息）。\n"
            f"问题：我刚才说过我的{label}是什么？请只回答数值或名称，不要解释。\n"
            f"--- 上下文 ---\n{context_text}"
        )
        resp = llm.invoke(prompt)
        results[key] = {
            "expected": str(value),
            "hit": check_fact_in_answer(key, str(value), resp.content),
            "answer_snippet": resp.content.strip()[:50],
        }
    return results


def suggest_trigger(curves_by_scenario: dict) -> dict:
    """启发式：取各场景第 15 轮 token 的中位数，向上取整到千位"""
    at_turn15 = []
    for sc in curves_by_scenario:
        curve = curves_by_scenario[sc]["curve"]
        target = min(15, len(curve))
        at_turn15.append(curve[target - 1]["tokens"])
    median = sorted(at_turn15)[len(at_turn15) // 2]
    trigger = max(8_000, int(median / 1_000) * 1_000)
    return {"tokens": trigger, "based_on": f"各场景第15轮token中位数={median}"}


async def run_scenario(agent, llm, scenario: dict, limit_turns: int | None) -> dict:
    """跑单场景（async，与生产 astream_events 链路一致）：
    逐轮 ainvoke 记录曲线；摘要；keep 三档 probe 对比。
    ⚠️ 必须用 ainvoke：lest 的 @tool 是 async 定义，agent.invoke 同步路径会报
    "StructuredTool does not support sync invocation"，导致所有工具执行失败。"""
    sid = scenario["id"]
    thread_id = f"baseline-{sid}"
    config = {"configurable": {"thread_id": thread_id}}

    from tools.user_context import set_current_thread_id

    curve = []
    turns = scenario["turns"] if not limit_turns else scenario["turns"][:limit_turns]

    print(f"\n=== 场景 {sid}: {scenario['desc']}（{len(turns)} 轮）===")
    for i, turn in enumerate(turns, 1):
        set_current_thread_id(thread_id)          # 模拟路由层，画像工具才能工作
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": turn}]}, config=config
        )
        history = result["messages"]
        tokens = sum(est_tokens(m.content) for m in history if getattr(m, "content", None))
        curve.append({"turn": i, "tokens": tokens})
        print(f"  轮{i:2d} 历史token={tokens:6d}  ← {turn[:30]}")

    history = result["messages"]  # 全量历史（摘要模拟输入）
    total_tokens = sum(est_tokens(m.content) for m in history if getattr(m, "content", None))

    # ── 摘要 + keep 三档对比（不重放 Agent，直接组装上下文问 probe）──
    keep_results = []
    for keep in KEEP_CANDIDATES:
        older = list(history[:-keep]) if keep < len(history) else []
        recent = history[-keep:] if keep < len(history) else history
        if older:
            summary, summary_tok = summarize_messages(llm, older)
            recent_tok = sum(est_tokens(m.content) for m in recent if getattr(m, "content", None))
            ctx_text = f"[历史摘要] {summary}\n--- 最近对话 ---\n{messages_to_text(recent)}"
            ctx_tokens = summary_tok + recent_tok
        else:
            ctx_text = messages_to_text(recent)
            ctx_tokens = recent_tok = total_tokens

        checks = probe_facts(llm, ctx_text, scenario["facts"])
        hit_rate = sum(1 for c in checks.values() if c["hit"]) / len(checks) if checks else 0
        keep_results.append({
            "keep": keep,
            "probe_accuracy": round(hit_rate, 3),
            "context_tokens": ctx_tokens,
            "summary_tokens": ctx_tokens - recent_tok if older else 0,
            "checks": {k: {"expected": v["expected"], "hit": v["hit"]} for k, v in checks.items()},
        })
        print(f"  keep={keep:2d}  probe命中={hit_rate:.0%}  上下文token={ctx_tokens}")

    return {
        "id": sid,
        "turns": len(turns),
        "total_tokens_at_end": total_tokens,
        "curve": curve,
        "keep_comparison": keep_results,
    }


async def main():
    parser = argparse.ArgumentParser(description="基线采集自动化")
    parser.add_argument("--dry-run", action="store_true", help="链路验证：仅 1 场景 3 轮")
    parser.add_argument("--limit-turns", type=int, default=None, help="每场景轮次上限")
    parser.add_argument("--scenarios", type=str, default=None, help="逗号分隔的场景 id，如 s1,s2")
    parser.add_argument("--keep", type=str, default="10,20,30", help="keep 对比档位")
    parser.add_argument("--output", default=str(BACKEND.parent / "eval" / "dialog_baseline.json"))
    args = parser.parse_args()

    global KEEP_CANDIDATES
    KEEP_CANDIDATES = [int(k) for k in args.keep.split(",")]

    from agent.engine import get_agent

    print("⏳ 加载 Agent...")
    agent = get_agent()

    # 预加载检索器（BGE-M3 + Reranker，18-30s）：
    # 避免首轮工具调用时才加载——否则模型加载的耗时/潜在网络超时
    # 会污染第一轮工具结果（超时失败 → 检索结果不进历史 → 曲线失真）
    from rag.retriever import get_retriever

    print("⏳ 预加载检索器（BGE-M3 + Reranker，约 20-30s）...")
    get_retriever()
    print("✅ 检索器就绪")

    # 摘要/probe 用独立 DeepSeek 实例（同 key/模型，temperature=0）。
    # 不依赖 agent.nodes 内部结构（PregelNode 无 .model 属性，已实测）。
    from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com/v1",
        temperature=0,
    )
    print("✅ Agent 就绪\n")

    scenarios = SCENARIOS
    if args.scenarios:
        wanted = set(args.scenarios.split(","))
        scenarios = [s for s in scenarios if s["id"] in wanted]
    if args.dry_run:
        scenarios = scenarios[:1]

    curves_by_scenario = {}
    results = []
    t0 = time.time()

    for sc in scenarios:
        res = await run_scenario(agent, llm, sc, limit_turns=3 if args.dry_run else args.limit_turns)
        results.append(res)
        curves_by_scenario[sc["id"]] = {"curve": res["curve"]}

    # ── 汇总：trigger 建议 + keep 推荐 ──
    trigger = suggest_trigger(curves_by_scenario) if not args.dry_run else {"tokens": None, "based_on": "dry-run"}

    keep_agg = {}
    for res in results:
        for kc in res["keep_comparison"]:
            k = kc["keep"]
            keep_agg.setdefault(k, []).append(kc["probe_accuracy"])
    keep_summary = [
        {"keep": k, "avg_accuracy": round(sum(v) / len(v), 3), "n_scenarios": len(v)}
        for k, v in sorted(keep_agg.items())
    ]
    # 推荐：平均命中率 100% 且 token 最小的 keep
    perfect = [k for k in keep_summary if k["avg_accuracy"] == 1.0]
    recommended_keep = min(perfect, key=lambda x: 0) if perfect else None
    if recommended_keep is None and keep_summary:
        recommended_keep = max(keep_summary, key=lambda x: x["avg_accuracy"])
    keep_recommend = recommended_keep["keep"] if recommended_keep else 20

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": args.dry_run,
        "trigger_suggestion": trigger,
        "keep_recommendation": {"keep_messages": keep_recommend, "detail": keep_summary},
        "scenarios": results,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("  基线采集报告")
    print("=" * 60)
    print(f"  场景数: {len(results)}  耗时: {time.time()-t0:.0f}s")
    print(f"  trigger 建议: {trigger['tokens']} token ({trigger['based_on']})")
    print(f"  keep 对比: " + ", ".join(f"keep={k['keep']} 命中{k['avg_accuracy']:.0%}" for k in keep_summary))
    print(f"  推荐 keep: {keep_recommend}")
    print(f"  报告已保存: {out_path}")
    if args.dry_run:
        print("  ⚠️ dry-run 模式：仅验证链路，trigger 建议无效")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
