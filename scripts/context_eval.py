"""
上下文评测 — 长对话场景集四指标验收（P0 最后一项）
====================================================
评测对象：history_summarizer 历史摘要（真实 Agent 链路，已挂摘要 middleware）
四指标（对齐设计文档 v2 §7.3）：
  ① 画像字段完整率（probe 问答，自动判定）        目标 100%
  ② 摘要忠实度（LLM-as-judge 判定 facts 是否被摘要后历史支持） 目标 ≥90%
  ③ token 收益（无摘要基线 dialog_baseline.json vs 有摘要实测） 
  ④ context 事件触发率（摘要触发 vs 事件 pop）    目标 100%

用法（backend 目录下）:
    venv/Scripts/python.exe ../scripts/context_eval.py                 # 全量 4 场景
    venv/Scripts/python.exe ../scripts/context_eval.py --scenarios s1  # 单场景
    venv/Scripts/python.exe ../scripts/context_eval.py --skip-judge    # 跳过 judge（省调用）
前置：Qdrant 运行中 + backend/.env 有 DEEPSEEK_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os  # noqa: F401
import re
import sys
import time

# ⚠️ 环境变量先于任何第三方 import（hf_hub 快照时机，见《开发踩坑记录》#3）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import asyncio
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from gen_long_dialogues import SCENARIOS  # noqa: E402

# ── 关键事实 → probe 问题（与 collect_baseline 口径一致）──
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
NUMERIC_FACTS = {"salary", "housing_rent", "children_edu", "elderly_support",
                 "previous_loss", "deduction_mortgage"}


def est_tokens(text: str) -> int:
    return max(1, int(len(text) * 1.75))


def count_history_tokens(messages) -> int:
    return sum(est_tokens(m.content) for m in messages if getattr(m, "content", None))


def messages_to_text(messages) -> str:
    return "\n".join(
        f"{getattr(m, 'type', 'msg')}: {m.content}"
        for m in messages if getattr(m, "content", None)
    )


def check_fact_in_answer(fact_key: str, expected: str, answer: str) -> bool:
    expected = str(expected).strip()
    answer = (answer or "").strip()
    if not answer:
        return False
    if fact_key in NUMERIC_FACTS:
        return bool(re.search(rf"(?<!\d){re.escape(expected)}(?!\d)", answer))
    return expected in answer


async def probe_facts(llm, context_text: str, facts: dict) -> dict:
    """对每条关键事实发 probe 问题，判定 LLM 能否从摘要后历史中提取"""
    results = {}
    for key, value in facts.items():
        label = FACT_LABELS.get(key, key)
        prompt = (
            f"以下是此前对话的历史（可能含摘要和最近消息）。\n"
            f"问题：我刚才说过我的{label}是什么？请只回答数值或名称，不要解释。\n"
            f"--- 历史 ---\n{context_text}"
        )
        resp = await llm.ainvoke(prompt)
        results[key] = {
            "expected": str(value),
            "hit": check_fact_in_answer(key, str(value), resp.content),
        }
    return results


async def judge_faithfulness(llm, history_text: str, facts: dict) -> dict:
    """judge 判定：每个 fact 是否被摘要后历史支持（防 LLM 瞎编的独立校验）"""
    fact_list = "\n".join(f"- {k}: {v}" for k, v in facts.items())
    prompt = (
        "你是严格的评测员。下面给出一段【摘要后的对话历史】和【用户关键事实清单】。\n"
        "判断清单中每个事实是否能在历史中找到【原样一致】的依据：数字/金额/名称必须\n"
        "完全一致地出现（如 1500、郑州、工资）；仅概括性表述（如\"有子女教育扣除\"）\n"
        "不算支持，一律计入 missing。历史中完全没有则为 missing。\n"
        "输出严格 JSON：{\"supported\": [\"key1\"], \"missing\": [\"key2\"]}\n"
        "只输出 JSON。\n\n"
        f"【关键事实清单】\n{fact_list}\n\n"
        f"【摘要后的对话历史】\n{history_text[:10000]}"
    )
    resp = await llm.ainvoke(prompt)
    try:
        data = json.loads(resp.content.strip().strip("```json").strip("```").strip())
        supported = set(data.get("supported", []))
        missing = set(data.get("missing", []))
        total = len(facts)
        return {"faithfulness": len(supported) / total if total else 1.0,
                "supported": sorted(supported), "missing": sorted(missing)}
    except (json.JSONDecodeError, AttributeError):
        return {"faithfulness": 0.0, "supported": [], "missing": list(facts.keys()),
                "error": "judge 输出非 JSON"}


async def run_scenario_eval(agent, llm, scenario: dict, limit_turns: int | None,
                            skip_judge: bool = False) -> dict:
    sid = scenario["id"]
    thread_id = f"ceval-{sid}"
    config = {"configurable": {"thread_id": thread_id}}

    from context.history_summarizer import pop_summarized_flag
    from tools.user_context import set_current_thread_id

    turns = scenario["turns"] if not limit_turns else scenario["turns"][: limit_turns]
    curve = []
    summarized = 0
    context_events = 0
    prev_tokens = 0
    max_tokens = 0

    print(f"\n=== 场景 {sid}（{len(turns)} 轮）===")
    for i, turn in enumerate(turns, 1):
        set_current_thread_id(thread_id)

        # 路由层行为：下一轮开头消费摘要标志 → context 事件
        if pop_summarized_flag(thread_id):
            context_events += 1
            print(f"  ✅ 轮{i}: context 事件（上轮已归档）")

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": turn}]}, config=config
        )
        tokens = count_history_tokens(result["messages"])
        max_tokens = max(max_tokens, tokens)
        drop = prev_tokens - tokens
        if drop > 5_000:
            summarized += 1
            print(f"  轮{i:2d} token={tokens:6d} 🎯 摘要触发（骤降 {drop}）← {turn[:20]}")
        prev_tokens = tokens
        curve.append({"turn": i, "tokens": tokens})

    # ── 场景末：probe 字段校验 + judge 忠实度 ──
    history_text = messages_to_text(result["messages"])
    probe = await probe_facts(llm, history_text[:10000], scenario["facts"])
    hit_rate = sum(1 for c in probe.values() if c["hit"]) / len(probe) if probe else 0
    print(f"  字段校验: probe 命中 {hit_rate:.0%}（{sum(1 for c in probe.values() if c['hit'])}/{len(probe)}）")

    judge = None
    if not skip_judge:
        judge = await judge_faithfulness(llm, history_text[:10000], scenario["facts"])
        print(f"  judge 忠实度: {judge['faithfulness']:.0%}（missing={judge.get('missing')}）")

    return {
        "id": sid,
        "turns": len(turns),
        "curve": curve,
        "max_tokens": max_tokens,
        "summarized_count": summarized,
        "context_event_count": context_events,
        "probe_accuracy": round(hit_rate, 3),
        "probe_checks": probe,
        "judge": judge,
    }


async def main():
    parser = argparse.ArgumentParser(description="上下文评测：历史摘要四指标验收")
    parser.add_argument("--scenarios", type=str, default=None, help="逗号分隔场景 id")
    parser.add_argument("--turns", type=int, default=None, help="每场景轮次上限")
    parser.add_argument("--skip-judge", action="store_true", help="跳过 judge 忠实度（省 API）")
    parser.add_argument("--output", default=str(BACKEND / "eval" / "context_eval_report.json"))
    args = parser.parse_args()

    from agent.engine import get_agent
    from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
    from langchain_openai import ChatOpenAI

    print("⏳ 加载 Agent（含 history_summarizer middleware）...")
    agent = get_agent()
    print("⏳ 预加载检索器...")
    from rag.retriever import get_retriever
    get_retriever()

    llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY,
                     base_url="https://api.deepseek.com/v1", temperature=0)
    print("✅ 就绪\n")

    scenarios = SCENARIOS
    if args.scenarios:
        wanted = set(args.scenarios.split(","))
        scenarios = [s for s in scenarios if s["id"] in wanted]

    results = []
    t0 = time.time()
    for sc in scenarios:
        results.append(await run_scenario_eval(agent, llm, sc, args.turns, args.skip_judge))

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print("  Context Evaluation Report")
    print("=" * 60)

    # 无摘要基线对比（dialog_baseline.json，若存在）
    baseline = {}
    baseline_path = BACKEND.parent / "eval" / "dialog_baseline.json"
    if baseline_path.exists():
        try:
            with open(baseline_path, encoding="utf-8") as f:
                bdata = json.load(f)
            baseline = {s["id"]: s["curve"][-1]["tokens"] for s in bdata.get("scenarios", [])}
        except Exception:
            pass

    agg = {"probe_acc": [], "faithfulness": [], "events": 0, "summ": 0}
    print(f"  {'场景':<4} {'峰值tok':>7} {'摘要次数':>6} {'事件':>4} {'probe命中':>8} {'judge':>6} {'基线末轮':>8} {'降幅':>6}")
    for r in results:
        base = baseline.get(r["id"])
        drop = (base - r["max_tokens"]) / base * 100 if base else None
        agg["probe_acc"].append(r["probe_accuracy"])
        if r["judge"]:
            agg["faithfulness"].append(r["judge"]["faithfulness"])
        agg["events"] += r["context_event_count"]
        agg["summ"] += r["summarized_count"]
        print(f"  {r['id']:<4} {r['max_tokens']:>7} {r['summarized_count']:>6} "
              f"{r['context_event_count']:>4} {r['probe_accuracy']:>8.0%} "
              f"{r['judge']['faithfulness'] if r['judge'] else 0:>6.0%} "
              f"{base if base else '-':>8} {f'{drop:.0f}%' if drop is not None else '-':>6}")

    probe_avg = sum(agg["probe_acc"]) / len(agg["probe_acc"]) if agg["probe_acc"] else 0
    faith_avg = sum(agg["faithfulness"]) / len(agg["faithfulness"]) if agg["faithfulness"] else None
    event_rate = agg["events"] / agg["summ"] if agg["summ"] else 0

    print()
    print(f"  probe 字段完整率(均值): {probe_avg:.0%}    目标 ≥100%")
    if faith_avg is not None:
        print(f"  摘要忠实度(judge均值):  {faith_avg:.0%}    目标 ≥90%")
    print(f"  context 事件触发率:      {event_rate:.0%}    目标 100%（摘要 {agg['summ']} 次 / 事件 {agg['events']} 次）")

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "probe_accuracy_avg": round(probe_avg, 3),
            "faithfulness_avg": round(faith_avg, 3) if faith_avg is not None else None,
            "context_event_rate": round(event_rate, 3),
            "summarized_total": agg["summ"],
            "context_events_total": agg["events"],
        },
        "scenarios": results,
        "baseline_tokens": baseline,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
