"""轻量 Trace 记录器（JSONL，一行一个事件）— 自建可观测性

背景（2026-08-11 定案）：LangSmith 不接——单机演示需离线可控、数据不上云、
trace 需求轻（每轮工具调用 + token + 耗时）。自建 JSONL：离线、本地、每行可讲。

用法：
    from context.trace import append_trace
    append_trace({"event": "tool_call", "request_id": rid, "tool": "search_knowledge"})
    append_trace({"event": "request_end", "request_id": rid, "duration_ms": 1234,
                  "ai_chars": 320, "tool_count": 3})

输出：backend/data/trace/{YYYY-MM-DD}.jsonl（线程安全：锁保护单写）。
原则：trace 失败绝不影响主流程（try/except 吞异常）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

# backend/data/trace/（backend 包上一级 /data/trace）
_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trace"
)

_LOCK = threading.Lock()


def append_trace(entry: dict) -> None:
    """追加一行 trace 事件。entry 会被补 ts 字段后写入当日 JSONL。

    Args:
        entry: 事件字典，建议含 event / request_id / thread_id 等
    """
    entry.setdefault("ts", datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
    try:
        os.makedirs(_DIR, exist_ok=True)
        fname = os.path.join(_DIR, datetime.now().strftime("%Y-%m-%d") + ".jsonl")
        line = json.dumps(entry, ensure_ascii=False)
        with _LOCK:
            with open(fname, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as exc:  # 记录失败绝不影响主流程
        logger.debug("trace 写入失败: %s", exc)


def read_trace(limit: int = 200) -> list[dict]:
    """读取今日 trace（调试/排查用，默认最近 200 条）。"""
    fname = os.path.join(_DIR, datetime.now().strftime("%Y-%m-%d") + ".jsonl")
    if not os.path.exists(fname):
        return []
    try:
        with open(fname, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as exc:
        logger.debug("trace 读取失败: %s", exc)
        return []


if __name__ == "__main__":
    # 自检：写读验证
    append_trace({"event": "selftest", "request_id": "unit-test", "note": "trace self check"})
    rows = read_trace(5)
    print(f"✅ trace 自检通过，最近 {len(rows)} 条，末条: {rows[-1]['event'] if rows else 'EMPTY'}")
