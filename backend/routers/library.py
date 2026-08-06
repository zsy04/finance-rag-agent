"""资料库只读路由 — 政策法规列表/正文、行业指标基准、城市列表

纯文件读取，不依赖 LLM / Qdrant（由 services/library_engine.py 承载全部逻辑）。
"""

from fastapi import APIRouter, HTTPException, Query

from services.library_engine import (
    get_document_content,
    list_benchmark,
    list_cities,
    list_documents,
)

router = APIRouter(prefix="/api/library", tags=["资料库"])


@router.get("/documents")
async def documents(
    category: str | None = Query(
        default=None, description="法规分类：法律/行政法规/部门规章/规范性文件"
    ),
    keyword: str | None = Query(default=None, description="标题关键词模糊匹配"),
    limit: int = Query(default=20, ge=1, le=100, description="每页条数（1~100）"),
    offset: int = Query(default=0, ge=0, description="分页偏移量"),
):
    """政策法规列表（纯文件读取，秒回，不依赖 LLM / Qdrant）。"""
    return list_documents(category=category, keyword=keyword, limit=limit, offset=offset)


@router.get("/documents/{doc_id}")
async def document_content(doc_id: str):
    """法规正文（Markdown 转 HTML，供前端直接渲染）。"""
    result = get_document_content(doc_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到法规：{doc_id}")
    return result


@router.get("/benchmark")
async def benchmark(
    category: str | None = Query(default=None, description="行业门类精确匹配（如：制造业）"),
    keyword: str | None = Query(default=None, description="细分行业名模糊匹配"),
):
    """行业指标基准查询（10 项指标，比率/倍数原样返回，不格式化）。"""
    return list_benchmark(category=category, keyword=keyword)


@router.get("/cities")
async def cities():
    """城市列表（MVP 仅郑州，架构预留城市扩展）。"""
    return list_cities()
