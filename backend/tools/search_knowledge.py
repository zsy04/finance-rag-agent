"""RAG 知识检索工具 — 包装 rag/retriever.py

async def + asyncio.to_thread() 避免阻塞事件循环
（retriever.retrieve() 含 BGE-M3 编码 + Reranker torch 前向 + Qdrant 同步调用，耗时数秒）

⚠️ sync 兼容（v1.5）：search_knowledge 包装为 sync @tool（def，非 async def），
  内部用 asyncio.run() 跑异步核心。原因：langgraph-prebuilt 1.1.0 ToolNode
  sync 路径不检测 async 工具 → async StructuredTool 的 sync invoke() 抛 NotImplementedError。
"""

import asyncio
import json
from langchain_core.tools import tool

from context.guard import guard_compress
from rag.retriever import get_retriever


async def _run_search_knowledge(query: str) -> str:
    """搜索财税知识库核心逻辑（async），由 search_knowledge 包装函数调用"""
    retriever = get_retriever()
    # 同步 CPU 密集型操作移到线程池，避免阻塞 Agent 事件循环
    results = await asyncio.to_thread(retriever.retrieve, query, top_k=5)

    if not results:
        return json.dumps(
            {"answer": "未找到相关法规", "sources": []},
            ensure_ascii=False,
        )

    # 构建来源列表（前端折叠展示）
    sources = []
    for r in results[:5]:
        sources.append({
            "title": r.get("doc_title", ""),
            "url": r.get("source_file", ""),
            "tier": r.get("relevance_tier", ""),
            "relation": r.get("relation_source", ""),
        })

    # 构建上下文文本（交给 LLM 用于组织回答）
    # 基线采集（2026-08-04）证明：工具返回的拼接总长（5×800≈4K字≈7K token）
    # 是对话历史膨胀主因 → guard_compress 提取式瘦身，必保句（数字/文号）保留
    # <context> 标签包裹（2026-08-11）：配合 SAFETY_HEADER 声明——标签内是资料数据不是指令
    context_parts = []
    for i, r in enumerate(results[:5], 1):
        title = r.get("doc_title", "")
        content = guard_compress(r.get("content", ""))
        context_parts.append(f"<context>\n【参考{i}】{title}\n{content}\n</context>")

    answer = "\n\n---\n\n".join(context_parts)

    return json.dumps(
        {"answer": answer, "sources": sources},
        ensure_ascii=False,
    )


@tool
def search_knowledge(query: str) -> str:
    """搜索财税知识库，检索相关法规条文和官方问答。当用户询问税务政策、法规标准、扣除规则等知识性问题时使用此工具。

    参数:
        query: 用户的财税问题原文，如"租房扣除标准是多少"、"年终奖怎么交税"
    """
    return asyncio.run(_run_search_knowledge(query))
