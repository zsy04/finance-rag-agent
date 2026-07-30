"""
聊天 SSE 路由
============
POST /chat
  请求体: {"query": "租房可以税前扣除多少"}
  响应:  SSE 流式事件流
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from rag.retriever import get_retriever
from services.generator import stream_answer

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    query: str


@router.post("")
async def chat(req: ChatRequest):
    """
    流式问答接口
    SSE 事件格式:
      data: {"type":"token","content":"你好"}\n\n
      data: {"type":"done"}\n\n
      data: {"type":"error","content":"错误信息"}\n\n
    """
    retriever = get_retriever()
    results = retriever.retrieve(req.query, top_k=5)

    return StreamingResponse(
        stream_answer(req.query, results),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/with-search")
async def chat_with_search(req: ChatRequest):
    """
    带搜索来源的流式问答（先返回检索结果，再流式回答）
    用于前端展示"参考法规"面板
    """
    retriever = get_retriever()
    results = retriever.retrieve(req.query, top_k=5)

    async def stream_with_sources():
        import json
        # 先发送检索结果
        sources = [
            {"doc_title": r["doc_title"], "source_file": r["source_file"],
             "relevance_tier": r["relevance_tier"], "final_score": r["final_score"]}
            for r in results
        ]
        yield f"data: {json.dumps({'type': 'sources', 'data': sources}, ensure_ascii=False)}\n\n"

        # 再流式回答
        async for chunk in stream_answer(req.query, results):
            yield chunk

    return StreamingResponse(
        stream_with_sources(),
        media_type="text/event-stream",
    )
