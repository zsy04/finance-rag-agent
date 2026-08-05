"""
集成测试 — history_summarizer 摘要触发 + context 事件
====================================================
验证目标（P0 核心模块验收）：
  ① 摘要在历史 ≈40K 时真的触发（消息被替换，token 骤降）
  ② context 事件标志位正确置位/消费（模拟路由层"下一轮开头 pop"）
  ③ 摘要后对话能继续不爆窗（token 回到可控水平再增长）

用法（backend 目录下）:
    venv/Scripts/python.exe ../scripts/test_summarizer.py            # 全跑 s1
    venv/Scripts/python.exe ../scripts/test_summarizer.py --turns 12 # 限制轮数（快速验证）
前置：Qdrant 运行中 + backend/.env 有 DEEPSEEK_API_KEY
"""

from __future__ import annotations

import argparse
import os  # noqa: F401

# ⚠️ 与 collect_baseline.py 一致：环境变量必须在任何第三方 import 之前设置
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from gen_long_dialogues import SCENARIOS  # noqa: E402


def est_tokens(text: str) -> int:
    """中文 token 估算：1 字 ≈ 1.75 token"""
    return max(1, int(len(text) * 1.75))


def count_history_tokens(messages) -> int:
    return sum(est_tokens(m.content) for m in messages if getattr(m, "content", None))


async def main():
    parser = argparse.ArgumentParser(description="history_summarizer 集成测试")
    parser.add_argument("--scenario", default="s1", help="场景 id（默认 s1，token 涨最快）")
    parser.add_argument("--turns", type=int, default=None, help="轮次上限")
    args = parser.parse_args()

    from agent.engine import get_agent
    from context.history_summarizer import pop_summarized_flag
    from tools.user_context import set_current_thread_id

    print("⏳ 加载 Agent（含 history_summarizer middleware）...")
    agent = get_agent()

    print("⏳ 预加载检索器...")
    from rag.retriever import get_retriever
    get_retriever()
    print("✅ 就绪\n")

    scenario = next(s for s in SCENARIOS if s["id"] == args.scenario)
    turns = scenario["turns"] if not args.turns else scenario["turns"][: args.turns]
    thread_id = f"itest-{args.scenario}"
    config = {"configurable": {"thread_id": thread_id}}

    prev_tokens = 0
    summarized_events = 0        # 检测到的摘要触发次数
    context_events = 0           # 模拟路由层 pop 到的标志次数
    max_tokens = 0

    print(f"=== 场景 {args.scenario}: {scenario['desc']}（{len(turns)} 轮）===")
    for i, turn in enumerate(turns, 1):
        set_current_thread_id(thread_id)

        # ── 模拟路由层：下一轮开始时消费摘要标志 → 发 context 事件 ──
        flag = pop_summarized_flag(thread_id)
        if flag:
            context_events += 1
            print(f"  ✅ 轮{i}: context 事件触发（上轮已归档摘要）")

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": turn}]}, config=config
        )
        history = result["messages"]
        tokens = count_history_tokens(history)
        max_tokens = max(max_tokens, tokens)

        drop = prev_tokens - tokens
        if drop > 5_000:  # 摘要替换导致历史 token 骤降
            summarized_events += 1
            marker = f"  🎯 摘要触发！token 骤降 {drop}"
        elif drop > 0:
            marker = f"  （↓{drop}）"
        else:
            marker = ""
        print(f"  轮{i:2d} 消息数={len(history):3d} token={tokens:6d}{marker} ← {turn[:24]}")
        prev_tokens = tokens

    # ── 汇总 ──
    print("\n" + "=" * 56)
    print("  集成测试报告")
    print("=" * 56)
    print(f"  场景: {args.scenario}  轮数: {len(turns)}")
    print(f"  摘要触发次数: {summarized_events}")
    print(f"  context 事件次数: {context_events}")
    print(f"  历史峰值 token: {max_tokens}（窗口 64K）")
    if summarized_events > 0 and max_tokens < 64_000:
        print("  ✅ 验收通过：摘要触发 + 未爆窗 + context 事件可用")
    elif summarized_events == 0:
        print("  ⚠️ 未检测到摘要触发——检查 trigger 阈值或场景轮次是否足够")
    else:
        print("  ⚠️ 摘要触发了但仍接近窗口——检查 keep 与摘要长度")

    # 结束前消费剩余标志（若有），避免污染
    set_current_thread_id(thread_id)
    pop_summarized_flag(thread_id)


if __name__ == "__main__":
    asyncio.run(main())
