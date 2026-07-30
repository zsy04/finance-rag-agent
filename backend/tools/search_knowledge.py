"""RAG 知识检索工具 — 包装 rag/retriever.py

async def + asyncio.to_thread() 避免阻塞事件循环
（retriever.retrieve() 含 BGE-M3 编码 + Reranker torch 前向 + Qdrant 同步调用，耗时数秒）
"""

import asyncio
import json
from langchain_core.tools import tool

from rag.retriever import get_retriever


@tool
async def search_knowledge(query: str) -> str:
    """搜索财税知识库，检索相关法规条文和官方问答。当用户询问税务政策、法规标准、扣除规则等知识性问题时使用此工具。

    参数:
        query: 用户的财税问题原文，如"租房扣除标准是多少"、"年终奖怎么交税"
    """
    retriever = get_retriever()
    # 同步 CPU 密集型操作移到线程池，避免阻塞 Agent 事件循环
    results = await asyncio.to_thread(retriever.retrieve, query, 5)

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
    context_parts = []
    for i, r in enumerate(results[:5], 1):
        title = r.get("doc_title", "")
        content = r.get("content", "")[:800]  # 截断过长 chunk
        context_parts.append(f"【参考{i}】{title}\n{content}")

    answer = "\n\n---\n\n".join(context_parts)

    return json.dumps(
        {"answer": answer, "sources": sources},
        ensure_ascii=False,
    )
