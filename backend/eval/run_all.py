"""评测自动化 — 三层一键串跑

对应《财务RAG-工程收尾待办清单》§2：检索层 + 工具层 + 生成层单命令出报告。

三层：
  ① 检索层  eval.py          RAG 检索 recall@k / MRR / NDCG（eval_set.json 60 条）
  ② 工具层  agent_eval.py    Agent 工具选择准确率（内嵌 26 条，目标 ≥90%）
  ③ 生成层  context_eval.py  历史摘要四指标（probe 完整率 / 忠实度 / token 收益 / 事件触发）

安全层（可选，--injection 开启）：
  ④ 注入层  injection_eval.py  防注入 10 条（canary 泄露 / 画像拒绝 / judge 行为判定）

用法（backend 目录下，用项目的 venv python）:
    python eval/run_all.py                          # 三层全跑
    python eval/run_all.py --skip-context           # 跳过生成层（省 API）
    python eval/run_all.py --skip-agent --skip-context   # 只跑检索层（快速）
    python eval/run_all.py --context-skip-judge     # 生成层跳过 LLM judge（省调用）
    python eval/run_all.py --injection              # 加跑防注入层（需 DEEPSEEK_API_KEY）

产物：
  - eval/retrieval_report.json    （eval.py --output）
  - eval/agent_eval_report.json   （agent_eval.py 自产）
  - eval/context_eval_report.json （context_eval.py 自产）
  - eval/injection_eval_report.json （injection_eval.py 自产）
  - eval/run_all_report.json      （本脚本聚合汇总）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
PYTHON = sys.executable  # 用当前解释器，保证与 run_all 环境一致

LAYER_REPORT_PATHS = {
    "retrieval": BACKEND / "eval" / "retrieval_report.json",
    "agent": BACKEND / "eval" / "agent_eval_report.json",
    "context": BACKEND / "eval" / "context_eval_report.json",
    "injection": BACKEND / "eval" / "injection_eval_report.json",
}


def run_layer(name: str, cmd: list[str], timeout: int | None = None) -> bool:
    """子进程串跑单个评测模块，返回是否成功"""
    print(f"\n{'=' * 64}\n▶ {name}\n{'=' * 64}")
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(BACKEND), check=False, timeout=timeout)
        elapsed = time.time() - t0
        ok = proc.returncode == 0
        status = "✅ 成功" if ok else "❌ 失败"
        print(f"\n→ {name} {status}（{elapsed:.0f}s，exit={proc.returncode}）")
        return ok
    except subprocess.TimeoutExpired:
        print(f"\n→ {name} ⏰ 超时（>{timeout}s）")
        return False
    except FileNotFoundError as e:
        print(f"\n→ {name} ❌ 找不到解释器/脚本: {e}")
        return False


def load_report(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def build_summary() -> dict:
    """读三层报告，聚合摘要"""
    summary: dict[str, dict] = {}

    # ① 检索层
    rep = load_report(LAYER_REPORT_PATHS["retrieval"])
    if rep:
        s = rep.get("summary", {})
        summary["retrieval"] = {
            "total_queries": rep.get("total_queries"),
            "recall@5": s.get("recall@5"),
            "recall@3": s.get("recall@3"),
            "mrr": s.get("mrr"),
            "ndcg@5": s.get("ndcg@5"),
            "failed_count": len(rep.get("failed", [])),
            "elapsed_seconds": rep.get("elapsed_seconds"),
            "report": str(LAYER_REPORT_PATHS["retrieval"].relative_to(BACKEND)),
        }

    # ② 工具层
    rep = load_report(LAYER_REPORT_PATHS["agent"])
    if rep:
        summary["agent"] = {
            "agent_mode": rep.get("agent_mode"),
            "total": rep.get("total"),
            "correct": rep.get("correct"),
            "accuracy": rep.get("accuracy"),
            "report": str(LAYER_REPORT_PATHS["agent"].relative_to(BACKEND)),
        }

    # ③ 生成层
    rep = load_report(LAYER_REPORT_PATHS["context"])
    if rep:
        s = rep.get("summary", {})
        summary["context"] = {
            "probe_accuracy_avg": s.get("probe_accuracy_avg"),
            "faithfulness_avg": s.get("faithfulness_avg"),
            "context_event_rate": s.get("context_event_rate"),
            "summarized_total": s.get("summarized_total"),
            "context_events_total": s.get("context_events_total"),
            "report": str(LAYER_REPORT_PATHS["context"].relative_to(BACKEND)),
        }

    # ④ 注入层
    rep = load_report(LAYER_REPORT_PATHS["injection"])
    if rep:
        summary["injection"] = {
            "judge_enabled": rep.get("judge_enabled"),
            "total": rep.get("total"),
            "passed": rep.get("passed"),
            "rate": rep.get("rate"),
            "report": str(LAYER_REPORT_PATHS["injection"].relative_to(BACKEND)),
        }

    return summary


def print_summary(summary: dict, layer_status: dict[str, bool]) -> None:
    print("\n" + "=" * 64)
    print("  三层评测汇总报告")
    print("=" * 64)

    # 值域说明：retrieval/context 层指标存 0-1 比例；agent 层 accuracy 存 0-100 数值
    PCT_RATIO_KEYS = {"recall@1", "recall@3", "recall@5", "mrr", "ndcg@5",
                      "probe_accuracy_avg", "faithfulness_avg", "context_event_rate",
                      "rate"}
    PCT_NUM_KEYS = {"accuracy"}

    def fmt_value(key: str, v) -> str:
        if isinstance(v, bool):
            return "✅" if v else "❌"
        if isinstance(v, float):
            if key in PCT_RATIO_KEYS:
                return f"{v:.2%}"
            if key in PCT_NUM_KEYS:
                return f"{v:.1f}%"
            return f"{v:.2f}"
        return str(v)

    for layer, label in (("retrieval", "① 检索层"), ("agent", "② 工具层"), ("context", "③ 生成层"), ("injection", "④ 注入层")):
        ok = layer_status.get(layer, False)
        print(f"\n  {label}  {'✅' if ok else '—'}")
        data = summary.get(layer)
        if not data:
            print("    （未运行或无报告）")
            continue
        for k, v in data.items():
            if k == "report":
                continue
            print(f"    {k:<24} {fmt_value(k, v)}")
        print(f"    报告: {data.get('report', '')}")

    # 达标线速览
    print("\n  ── 达标线速览 ──")
    r = summary.get("retrieval")
    if r and r.get("recall@5") is not None:
        r5 = r["recall@5"]
        print(f"    Recall@5:  {r5:.2%}    {'✅ ≥77.5%' if r5 >= 0.775 else '⚠️ <77.5% 需诊断'}")
    a = summary.get("agent")
    if a and a.get("accuracy") is not None:
        acc = a["accuracy"]
        print(f"    工具准确率: {acc:.1f}%   {'✅ ≥90%' if acc >= 90 else '⚠️ <90% 需调优'}")
    c = summary.get("context")
    if c and c.get("probe_accuracy_avg") is not None:
        print(f"    probe 完整率: {c['probe_accuracy_avg']:.0%}   目标 ≥100%")
        if c.get("faithfulness_avg") is not None:
            print(f"    摘要忠实度:  {c['faithfulness_avg']:.0%}   目标 ≥90%")
    inj = summary.get("injection")
    if inj and inj.get("rate") is not None:
        print(f"    防注入通过率: {inj['rate']:.0%}   {'✅ 10/10' if inj.get('rate', 0) >= 1 else '⚠️ 未全绿，需分析'}"
              f"（judge={'开' if inj.get('judge_enabled') else '关'}）")

    print("=" * 64)


def main() -> None:
    parser = argparse.ArgumentParser(description="三层评测一键串跑")
    parser.add_argument("--skip-retrieval", action="store_true", help="跳过检索层")
    parser.add_argument("--skip-agent", action="store_true", help="跳过工具层")
    parser.add_argument("--skip-context", action="store_true", help="跳过生成层")
    parser.add_argument("--injection", action="store_true", help="加跑防注入层（injection_eval.py，需 API）")
    parser.add_argument("--injection-skip-judge", action="store_true",
                        help="防注入层跳过 LLM judge（省 API 调用）")
    parser.add_argument("--context-skip-judge", action="store_true",
                        help="生成层跳过 LLM judge（转发给 context_eval.py，省 API 调用）")
    parser.add_argument("--timeout", type=int, default=None, help="每层超时秒数（默认不限制）")
    parser.add_argument("--output", default="eval/run_all_report.json", help="聚合报告输出路径（相对 backend）")
    args = parser.parse_args()

    if args.skip_retrieval and args.skip_agent and args.skip_context:
        print("⚠️ 三层都被 --skip 跳过，无任务可跑")
        sys.exit(1)

    layer_status: dict[str, bool] = {}

    if not args.skip_retrieval:
        layer_status["retrieval"] = run_layer(
            "检索层 eval.py（eval_set.json 60 条 → recall@k/MRR/NDCG）",
            [PYTHON, "eval/eval.py", "--output", "eval/retrieval_report.json"],
            timeout=args.timeout,
        )

    if not args.skip_agent:
        layer_status["agent"] = run_layer(
            "工具层 agent_eval.py（26 条 → 工具选择准确率）",
            [PYTHON, "eval/agent_eval.py"],
            timeout=args.timeout,
        )

    if not args.skip_context:
        cmd = [PYTHON, "../scripts/context_eval.py"]
        if args.context_skip_judge:
            cmd.append("--skip-judge")
        layer_status["context"] = run_layer(
            "生成层 context_eval.py（历史摘要四指标）",
            cmd,
            timeout=args.timeout,
        )

    if args.injection:
        cmd = [PYTHON, "eval/injection_eval.py"]
        if args.injection_skip_judge:
            cmd.append("--skip-judge")
        layer_status["injection"] = run_layer(
            "注入层 injection_eval.py（防注入 10 条）",
            cmd,
            timeout=args.timeout,
        )

    # 聚合报告
    summary = build_summary()
    print_summary(summary, layer_status)

    out_path = BACKEND / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "layer_status": layer_status,
        "layers": summary,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 聚合报告已保存: {out_path}")

    # 退出码：任一已跑层失败则非 0（方便 CI/脚本判断）
    ran = [ok for ok in layer_status.values()]
    sys.exit(0 if ran and all(ran) else 1)


if __name__ == "__main__":
    main()
