"""资料库服务层 — 纯文件读取 + 过滤 + 转换，零依赖 LLM / Qdrant

数据源：
- 法规：rag-data/processed/national/tax_law/*.md（53 个，带 YAML frontmatter）
- 行业基准：rag-data/processed/national/rates/industry_benchmark.json（97 条 × 10 项指标）
- 城市索引：rag-data/processed/metadata/cities_index.json
"""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

import markdown as md
import yaml

logger = logging.getLogger(__name__)

# 数据文件路径（与 tax_engine.py / social_engine.py 同构：backend 上两级为项目根）
TAX_LAW_DIR = Path(__file__).parent.parent.parent / "rag-data" / "processed" / "national" / "tax_law"
BENCHMARK_FILE = Path(__file__).parent.parent.parent / "rag-data" / "processed" / "national" / "rates" / "industry_benchmark.json"
CITIES_INDEX_FILE = Path(__file__).parent.parent.parent / "rag-data" / "processed" / "metadata" / "cities_index.json"

# 行业基准 10 项指标（顺序即展示顺序；字段名原样透传，勿改名、勿格式化）
INDICATOR_KEYS = (
    "vat_burden",        # 增值税税负率（比率）
    "cit_burden",        # 企业所得税税负率（比率）
    "gross_margin",      # 毛利率（比率）
    "net_margin",        # 净利率（比率）
    "expense_ratio",     # 费用率（比率）
    "ar_turnover",       # 应收账款周转率（次/年）
    "inventory_turnover",  # 存货周转率（次/年）
    "debt_ratio",        # 资产负债率（比率）
    "current_ratio",     # 流动比率（倍）
    "quick_ratio",       # 速动比率（倍）
)

# 城市索引 code → 中文名（MVP 仅郑州；扩展城市时在此追加）
CITY_NAMES = {"zhengzhou": "郑州"}

# 部委规章常见词尾（优先于"公告/通知"判断，避免"欠税公告办法"这类误判）
_REGULATION_SUFFIXES = ("办法", "规定", "细则", "规则")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，返回 (元数据 dict, 正文 Markdown)。

    frontmatter 由 `---` 包裹，首行即是 `---`（无 BOM，UTF-8）。
    """
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            return meta, parts[2].strip("\n")
    return {}, text


def _domain_of(url: str) -> str:
    """从 source_url 提取域名（如 fgk.chinatax.gov.cn）。"""
    match = re.search(r"https?://([^/]+)", url or "")
    return match.group(1) if match else ""


def _infer_category(title: str) -> str:
    """按文件名/标题推断法规分类：法律 / 行政法规 / 部门规章 / 规范性文件。

    优先级：
    1. 以"法"结尾（非"办法"）或全国人大常委会决定 → 法律
    2. 国务院/国务院办公厅发文，或文件名含"条例" → 行政法规
    3. 以"办法/规定/细则/规则"结尾 → 部门规章
    4. 含"公告"、以"通知"结尾、含"决定" → 规范性文件
    5. 其余兜底 → 部门规章
    """
    if (title.endswith("法") and not title.endswith("办法")) or title.startswith(
        "全国人民代表大会常务委员会"
    ):
        return "法律"
    if title.startswith("国务院") or "条例" in title:
        return "行政法规"
    if title.endswith(_REGULATION_SUFFIXES):
        return "部门规章"
    if "公告" in title or title.endswith("通知") or "决定" in title:
        return "规范性文件"
    return "部门规章"


def _date_prefix(value) -> str:
    """取日期前 10 位（兼容 YAML 解析出的 datetime 对象与字符串）。"""
    if value is None:
        return ""
    return str(value)[:10]


@lru_cache(maxsize=1)
def _scan_documents() -> list[dict]:
    """扫描法规目录，构建文档索引（文件名 + frontmatter + 正文，缓存一次）。"""
    docs = []
    for path in sorted(TAX_LAW_DIR.glob("*.md")):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        doc_id = path.stem
        category = _infer_category(doc_id)
        docs.append(
            {
                "id": doc_id,
                "title": meta.get("doc_title") or meta.get("title") or doc_id,
                "category": category,
                "level": category,
                "updated": _date_prefix(meta.get("cleaned_at")),
                "source": _domain_of(meta.get("source_url", "")),
                "body": body,
            }
        )
    return docs


def list_documents(
    category: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """法规列表：category 精确匹配 + keyword 标题/文件名模糊匹配 + 分页。"""
    docs = _scan_documents()
    if category:
        docs = [d for d in docs if d["category"] == category]
    if keyword:
        docs = [d for d in docs if keyword in d["title"] or keyword in d["id"]]
    total = len(docs)
    items = [
        {k: d[k] for k in ("id", "title", "category", "level", "updated", "source")}
        for d in docs[offset : offset + limit]
    ]
    return {"total": total, "items": items}


def get_document_content(doc_id: str) -> dict | None:
    """法规正文：Markdown → HTML。找不到返回 None（由路由层转 404）。

    清洗后的正文无 H1 标题（直接是条文），此处用 title 补一个 H1 提升阅读体验。
    """
    for doc in _scan_documents():
        if doc["id"] == doc_id:
            html = md.markdown(
                f"# {doc['title']}\n\n{doc['body']}",
                extensions=["tables", "fenced_code"],
            )
            return {
                "id": doc["id"],
                "title": doc["title"],
                "category": doc["category"],
                "html_content": html,
            }
    return None


@lru_cache(maxsize=1)
def _load_benchmark() -> list[dict]:
    """读取行业基准 JSON（原样保留，仅缓存避免重复读盘）。"""
    data = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    return data.get("industries", [])


def list_benchmark(category: str | None = None, keyword: str | None = None) -> dict:
    """行业指标基准：category 门类精确匹配 + keyword 细分行业名模糊匹配。

    原 JSON 是扁平结构，此处组装为 indicators 嵌套对象；null 指标原样带上。
    """
    industries = _load_benchmark()
    if category:
        industries = [i for i in industries if i["category"] == category]
    if keyword:
        industries = [i for i in industries if keyword in i["sub_industry"]]
    items = [
        {
            "category": i["category"],
            "sub_industry": i["sub_industry"],
            "indicators": {k: i.get(k) for k in INDICATOR_KEYS},
        }
        for i in industries
    ]
    return {"total": len(items), "industries": items}


@lru_cache(maxsize=1)
def list_cities() -> dict:
    """城市列表（MVP 仅郑州；架构预留城市扩展，数据来自 cities_index.json）。"""
    data = json.loads(CITIES_INDEX_FILE.read_text(encoding="utf-8"))
    cities = [
        {
            "code": code,
            "name": CITY_NAMES.get(code, code),
            "province": info.get("province", ""),
            "city_code": info.get("city_code", ""),
            "data_version": info.get("data_version", ""),
        }
        for code, info in data.get("cities", {}).items()
    ]
    return {"total": len(cities), "cities": cities}
