"""测试 RAG + DeepSeek 流式问答"""
import asyncio
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

try:
    from rag.retriever import get_retriever
    from services.generator import stream_answer
except Exception as e:
    print(f"Import error: {e}")
    traceback.print_exc()
    sys.exit(1)


async def main():
    try:
        print("获取 Retriever...", flush=True)
        r = get_retriever()

        print("检索中...", flush=True)
        results = r.retrieve("租房可以税前扣除多少", top_k=5)
        print(f"检索完成: {len(results)} 条", flush=True)
        for i, item in enumerate(results[:3]):
            print(f"  {i+1}. [{item['relevance_tier']}] {item['doc_title']} score={item['final_score']:.4f}")

        print("\n--- DeepSeek 流式回答 ---", flush=True)
        async for chunk in stream_answer("租房可以税前扣除多少", results):
            line = chunk.strip()
            if not line:
                continue
            # 解析 SSE 数据
            if line.startswith("data: "):
                data = json.loads(line[6:])
                t = data.get("type", "")
                if t == "token":
                    print(data["content"], end="", flush=True)
                elif t == "done":
                    print("\n\n[回答完成]", flush=True)
                elif t == "error":
                    print(f"\n[错误: {data['content']}]", flush=True)
        print()

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
