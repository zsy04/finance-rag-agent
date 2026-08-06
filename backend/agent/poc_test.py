"""
PoC: 验证 LangGraph @tool 两大关键假设
假设①：contextvar 在 LangGraph 调度 sync @tool 时能传播
假设②：on_tool_end 的 output 是工具返回的 JSON 字符串，可 json.loads 解包

运行：cd F:/lest && C:/Users/22808/.workbuddy/binaries/python/envs/default/bin/python backend/agent/poc_test.py
"""

import json
import os
import asyncio
from contextvars import ContextVar
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# 加载 .env
load_dotenv("backend/.env")

API_KEY = os.getenv("DEEPSEEK_API_KEY")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

print(f"模型: {MODEL}")
print(f"API Key: {API_KEY[:10]}...")

# ── 假设①：contextvar 传播验证 ──
_test_var: ContextVar[str] = ContextVar("test_ctx")

@tool
def contextvar_test(s: str = "") -> str:
    """测试 contextvar 是否在 @tool 内部可读。调用时不传 s 参数。"""
    try:
        val = _test_var.get()
        return json.dumps({
            "answer": f"contextvar 传播成功: {val}",
            "ctx_ok": True
        }, ensure_ascii=False)
    except LookupError:
        return json.dumps({
            "answer": "contextvar 传播失败: LookupError",
            "ctx_ok": False
        }, ensure_ascii=False)

# ── 假设②：结构化返回 + on_tool_end 解包验证 ──
@tool
def structured_return(x: int, y: int) -> str:
    """测试工具返回结构化 JSON，计算两数之和。x 和 y 是需要相加的两个整数。"""
    return json.dumps({
        "answer": f"计算结果: {x} + {y} = {x + y}",
        "result_card": {"type": "test", "data": {"sum": x + y}},
        "disclaimer": "test disclaimer",
        "sources": [{"title": "test source", "url": "https://test.example.com"}]
    }, ensure_ascii=False)


async def main():
    llm = ChatOpenAI(
        model=MODEL,
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0,
    )

    agent = create_react_agent(
        llm,
        [contextvar_test, structured_return],
        checkpointer=MemorySaver(),
    )

    # ── 验证①：contextvar 传播 ──
    _test_var.set("hello_from_router_20260730")
    config = {"configurable": {"thread_id": "poc-ctx-1"}}

    print("\n" + "=" * 60)
    print("=== 验证①：contextvar 传播 ===")
    print("=" * 60)

    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": "调用 contextvar_test 工具"}]},
        config=config, version="v2"
    ):
        kind = event["event"]
        if kind == "on_tool_start":
            print(f"  [tool_start] {event['name']}")
        elif kind == "on_tool_end":
            output = event["data"]["output"]
            print(f"  [tool_end] output 类型: {type(output).__name__}")
            # 实际 output 是 ToolMessage 对象，JSON 在 .content 字段
            raw = output.content if hasattr(output, 'content') else output
            print(f"  [tool_end] content: {raw}")
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                ctx_ok = parsed.get("ctx_ok", "unknown")
                print(f"  → contextvar 传播: {'✅ 成功' if ctx_ok else '❌ 失败'}")
            except Exception as e:
                print(f"  → 解包失败: {e}")
        elif kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                print(f"  [llm] {chunk.content}", end="", flush=True)

    print("\n")

    # ── 验证②：结构化返回 ──
    _test_var.set("poc-struct-2")
    config2 = {"configurable": {"thread_id": "poc-struct-2"}}

    print("=" * 60)
    print("=== 验证②：结构化返回 + on_tool_end 解包 ===")
    print("=" * 60)

    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": "请计算 3 加 5 等于多少"}]},
        config=config2, version="v2"
    ):
        kind = event["event"]
        if kind == "on_tool_start":
            print(f"  [tool_start] {event['name']}")
        elif kind == "on_tool_end":
            output = event["data"]["output"]
            print(f"  [tool_end] output 类型: {type(output).__name__}")
            # 实际 output 是 ToolMessage 对象，JSON 在 .content 字段
            raw = output.content if hasattr(output, 'content') else str(output)
            try:
                parsed = json.loads(raw)
                print(f"  ✅ json.loads 解包成功")
                print(f"     answer:      {parsed.get('answer', 'N/A')}")
                print(f"     result_card: {json.dumps(parsed.get('result_card'), ensure_ascii=False)}")
                print(f"     disclaimer:  {parsed.get('disclaimer', 'N/A')}")
                print(f"     sources:     {json.dumps(parsed.get('sources'), ensure_ascii=False)}")
            except json.JSONDecodeError as e:
                print(f"  ❌ json.loads 失败: {e}")
                print(f"     raw: {raw[:200]}")
        elif kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                print(f"  [llm] {chunk.content}", end="", flush=True)

    print("\n" + "=" * 60)
    print("=== PoC 完成 ===")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
