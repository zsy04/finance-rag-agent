# 后端资料库接口 · AI 代码生成上下文包

> **用途**：交给负责后端开发的 AI 直接使用——本项目已有的代码范式、接口规格、真实数据结构、验收标准全部在此，无需翻其他文档。
> **适用任务**：为 lest 财税 RAG Agent 新增「资料库」只读接口（3 个 GET 端点）。
> **更新**：2026-08-06 — 数据结构已核实（10 项指标字段名 + 比率小数格式）。

---

## 0. 一句话任务

在 FastAPI 后端新增资料库只读接口：**政策法规列表 / 法规正文（Markdown→HTML）/ 行业指标基准查询**。数据文件已全部就绪，只做读取、过滤、转换，不改动任何现有代码逻辑。

---

## 1. 项目背景（一句话）

财税 RAG Web 应用「lest 财税助手」：DeepSeek 负责 Agent 调度，税率/社保计算走纯代码引擎，法规知识来自税总法规库清洗后的 Markdown。本任务是 UI 设计稿落地的一部分——给「资料库」页面提供数据接口。

---

## 2. 项目结构（后端相关）

```
backend/
├── main.py                 # FastAPI 入口，include_router 注册（在此加 library_router）
├── config.py               # 配置（DATA_DIR = PROJECT_ROOT/"rag-data"/"processed" 已存在）
├── routers/
│   ├── tax.py              # 个税计算路由（风格参照）
│   ├── social.py
│   ├── chat.py
│   └── form.py
├── services/
│   ├── tax_engine.py       # 纯逻辑服务层（风格参照）
│   └── social_engine.py
└── data/                   # SQLite（与本次无关）
```

**依赖**：`fastapi` / `pydantic` 已有；Markdown 转 HTML 可用 `markdown` 库（requirements.txt 如无则需添加）。

---

## 3. 代码范式（严格遵守，模仿现有风格）

### 路由层（参照 `backend/routers/tax.py`）

```python
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/library", tags=["资料库"])


@router.get("/documents")
async def list_documents(
    category: str | None = Query(default=None, description="法规分类：法律/行政法规/部门规章/规范性文件"),
    keyword: str | None = Query(default=None, description="标题关键词"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    ...
```

**风格要求**：
- 路由函数在 `routers/`，纯逻辑在 `services/`（薄路由 + 厚服务）
- 参数用 `Query` + 中文 `description`（对齐 tax.py 的 Field 风格）
- 路由注册到 `main.py`：`from routers.library import router as library_router` + `app.include_router(library_router)`
- 中文注释、无类型省略、无 `any`、无 try/except 吞错（让异常自然抛出）

### 服务层（参照 `backend/services/tax_engine.py` 的纯函数风格）

```python
# backend/services/library_engine.py
from pathlib import Path
from functools import lru_cache
from config import DATA_DIR

TAX_LAW_DIR = DATA_DIR / "national" / "tax_law"
BENCHMARK_FILE = DATA_DIR / "national" / "rates" / "industry_benchmark.json"
```

---

## 4. 接口规格（3 个端点）

### 4.1 `GET /api/library/documents` — 法规列表

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `category` | str | 否 | 法律 / 行政法规 / 部门规章 / 规范性文件 |
| `keyword` | str | 否 | 标题关键词模糊匹配 |
| `limit` | int | 否 | 默认 20，≤100 |
| `offset` | int | 否 | 默认 0 |

**响应**：

```json
{
  "total": 53,
  "items": [
    {
      "id": "个人所得税法",
      "title": "中华人民共和国个人所得税法",
      "category": "法律",
      "level": "法律",
      "updated": "2026-07-28",
      "source": "fgk.chinatax.gov.cn"
    }
  ]
}
```

**实现要点**：
- `id` = 文件名去 `.md`；`title` = frontmatter 的 `doc_title` 或 `title` 字段
- `category` = frontmatter `category`（注意：frontmatter 里 `category: tax_law` 是文档类型，**法规分类需从 `doc_title`/文件名推断或查 mapping**，输出为：法律/行政法规/部门规章/规范性文件）
- `updated` = frontmatter `cleaned_at` 日期部分；`source` = `source_url` 域名

### 4.2 `GET /api/library/documents/{doc_id}` — 法规正文

**响应**：

```json
{
  "id": "个人所得税法",
  "title": "中华人民共和国个人所得税法",
  "category": "法律",
  "html_content": "<h1>中华人民共和国个人所得税法</h1>\n<p>（1980年…）</p>..."
}
```

**实现要点**：
- 读取 .md 正文（去掉 YAML frontmatter），**Markdown 转 HTML**（用 `markdown` 库：`markdown.markdown(text, extensions=['tables', 'fenced_code'])`）
- 找不到返回 404

### 4.3 `GET /api/library/benchmark` — 行业指标基准

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `category` | str | 否 | 行业门类（如"制造业"）精确匹配 |
| `keyword` | str | 否 | 细分行业名模糊匹配 |

**响应**：

```json
{
  "total": 97,
  "industries": [
    {
      "category": "农、林、牧、渔业",
      "sub_industry": "农业",
      "indicators": {
        "vat_burden": { "low": 0, "high": 0.02 },
        "cit_burden": { "low": 0, "high": 0.05 },
        "gross_margin": { "low": 0.2, "high": 0.35 },
        "net_margin": { "low": 0.05, "high": 0.12 },
        "ar_turnover": { "low": 3, "high": 8 },
        "inventory_turnover": { "low": 2, "high": 6 },
        "debt_ratio": { "low": 0.4, "high": 0.6 },
        "current_ratio": { "low": 1, "high": 2 },
        "quick_ratio": { "low": 0.5, "high": 1.2 },
        "expense_ratio": { "low": 0.08, "high": 0.15 }
      }
    }
  ]
}
```

**⚠️ 关键约束（易错）**：
- JSON 原生字段是 `ar_turnover`（**不是** `receivable_turnover`），必须原样透传，勿改名
- 指标值保留原始格式：比率类为小数（0~1），周转/流动类为倍数——**后端不格式化**，前端负责显示
- 原 JSON 是扁平结构（`{category, sub_industry, vat_burden, ...}`），本接口需组装为 `indicators` 嵌套对象
- 返回全 10 项指标（含值为 null 的也带上）

---

## 5. 真实数据文件

### 5.1 法规文件示例 `rag-data/processed/national/tax_law/个人所得税法.md`

```markdown
---
source_url: "https://fgk.chinatax.gov.cn/zcfgk/c100009/c5193028/content.html"
doc_number: 主席令第9号
module: 一
category: tax_law
city: national
doc_title: 个人所得税法
relevance_tier: tax_law
relevance_weight: 10
cleaned_at: 2026-07-28 21:48:39
---

# 中华人民共和国个人所得税法
（1980年9月10日第五届全国人民代表大会第三次会议通过...）
...
```

- frontmatter 用 `---` 包裹；`doc_title` 是简称，正文 H1 是全称
- 共 53 个文件；部分文件名带"中华人民共和国"前缀，部分不带

### 5.2 行业基准文件 `rag-data/processed/national/rates/industry_benchmark.json`

```json
{
  "tool_usage": { "description": "全行业财务指标基准库，含 20 个行业门类 × 97 个细分行业 × 10 项财务指标..." },
  "meta": { "total_industries": 97, "total_categories": 20, "notes": "low/high 为行业平均范围。null 表示不适用" },
  "industries": [
    {
      "category": "农、林、牧、渔业",
      "sub_industry": "农业",
      "vat_burden": { "low": 0, "high": 0.02 },
      "cit_burden": { "low": 0, "high": 0.05 },
      "gross_margin": { "low": 0.2, "high": 0.35 },
      "net_margin": { "low": 0.05, "high": 0.12 },
      "ar_turnover": { "low": 3, "high": 8 },
      "inventory_turnover": { "low": 2, "high": 6 },
      "debt_ratio": { "low": 0.4, "high": 0.6 },
      "current_ratio": { "low": 1, "high": 2 },
      "quick_ratio": { "low": 0.5, "high": 1.2 },
      "expense_ratio": { "low": 0.08, "high": 0.15 }
    }
  ]
}
```

---

## 6. 要创建/修改的文件

| 文件 | 操作 | 说明 |
|------|:---:|------|
| `backend/services/library_engine.py` | **新建** | 数据读取/过滤/转换（lru_cache 缓存 53 md + 84KB JSON） |
| `backend/routers/library.py` | **新建** | 3 个 GET 端点 |
| `backend/main.py` | 修改 | `include_router` 注册 library_router |
| `requirements.txt` | 修改 | 如需 `markdown` 库则添加 |

---

## 7. 验收标准

- [ ] `curl "localhost:8000/api/library/documents?category=法律"` → 返回法规列表，字段完整
- [ ] `curl "localhost:8000/api/library/documents?keyword=个人"` → 模糊搜索生效
- [ ] `curl "localhost:8000/api/library/documents/个人所得税法"` → `html_content` 含 `<h1>`/`<p>` 标签
- [ ] `curl "localhost:8000/api/library/documents/不存在"` → 404
- [ ] `curl "localhost:8000/api/library/benchmark?category=制造业"` → 过滤正确，`indicators` 含全 10 项，`ar_turnover` 字段名正确
- [ ] `curl "localhost:8000/api/library/benchmark?keyword=电子"` → 细分行业模糊匹配
- [ ] 接口不依赖 LLM / Qdrant（纯文件读取，秒回）
- [ ] 无 try/except 吞错、无 `any` 类型、中文注释（对齐现有代码风格）

---

## 8. 常见坑（务必避免）

1. **字段名**：`ar_turnover` 不是 `receivable_turnover`；别改任何指标 key
2. **小数 vs 百分数**：JSON 里 0.02 就是 2%，后端原样返回，不 ×100
3. **frontmatter**：用 `---` 分隔，解析时注意文件首行就是 `---`，无 BOM
4. **文件编码**：所有 .md 为 UTF-8，`open(..., encoding='utf-8')` 必须显式指定
5. **不要在 routers 里写大段逻辑**：薄路由 + 厚服务（services 层）
6. **缓存**：`@lru_cache(maxsize=1)` 缓存目录扫描与 JSON 读取结果，文件小不占内存
