"""申报流程指引工具 — RAG 检索 operations/ 目录

检索个税操作指南，返回分步骤操作指引 + 官方入口链接。

⚠️ sync 兼容（v1.5）：filing_guide 包装为 sync @tool（def，非 async def），
  内部用 asyncio.run() 跑异步核心。原因同 search_knowledge。
"""

import asyncio
import json
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from rag.retriever import get_retriever


class FilingGuideInput(BaseModel):
    """申报指引输入参数。"""
    scenario: str = Field(
        description='申报场景: "个税年度汇算"(退税/补税), "个体户B表"(个体工商户申报), "小规模增值税"(小规模纳税人增值税申报)'
    )


async def _run_filing_guide(scenario: str) -> str:
    """申报流程指引核心逻辑（async），由 filing_guide 包装函数调用"""
    retriever = get_retriever()

    # 检索操作指南（用 category 或 tier 过滤 operations 类文档）
    results = await asyncio.to_thread(
        retriever.retrieve, scenario, 5, None, "qa_corpus", None
    )

    if not results:
        return json.dumps(
            {
                "answer": "未找到相关操作指南。建议访问国家税务总局官网或拨打 12366 咨询。",
                "sources": [],
            },
            ensure_ascii=False,
        )

    # 构建来源列表
    sources = []
    for r in results[:5]:
        sources.append({
            "title": r.get("doc_title", ""),
            "url": r.get("source_file", ""),
            "tier": r.get("relevance_tier", ""),
        })

    # 构建上下文
    context_parts = []
    for i, r in enumerate(results[:5], 1):
        title = r.get("doc_title", "")
        content = r.get("content", "")[:800]
        context_parts.append(f"【参考{i}】{title}\n{content}")

    answer = "\n\n---\n\n".join(context_parts)

    # 追加官方入口
    answer += "\n\n---\n\n"
    answer += "官方入口:\n"
    answer += '- 个人所得税 APP（各大应用商店搜索"个人所得税"）\n'
    answer += "- 自然人电子税务局: https://etax.chinatax.gov.cn\n"
    answer += "- 咨询热线: 12366"

    return json.dumps(
        {"answer": answer, "sources": sources},
        ensure_ascii=False,
    )


@tool(args_schema=FilingGuideInput)
def filing_guide(scenario: str) -> str:
    """获取个税申报操作流程指引。当用户问"怎么退税"、"个税APP怎么操作"、"如何申报"等操作流程问题时使用此工具。返回分步骤操作指南和官方入口链接。

    参数:
        scenario: 申报场景，如 "个税年度汇算"、"个体户B表"、"小规模增值税"、"退税"、"申报"
    """
    return asyncio.run(_run_filing_guide(scenario))
