# 财务 RAG Agent · 后端补充需求：地区资料库接口

> **用途**：设计稿落地（《财务RAG-设计稿落地与前端改造清单.md》C 项）的后端补充实现蓝图。数据资产已收集完毕，本次只需后端**读取/整理**并暴露只读接口，前端展示。
> **依据**：`财务RAG-前后端对照表.md`、`rag-data/processed/**` 真实数据盘点、`backend/routers/*` 现有路由风格
> **更新**：2026-08-06 — 产品决策定案：① 地区资料库（政策法规+行业基准）后端读取接口；② **申报记录删除**（不做）；③ 折叠态图标校准（前端，见文档 §5）

---

## 1. 产品决策记录

| # | 决策项 | 结论 | 说明 |
|---|--------|------|------|
| 1 | 资料库范围 | ✅ **政策法规 + 行业基准**（保留） | 数据已收集完毕（53 部法规 / 97 条行业基准） |
| 2 | 申报记录 | ❌ **删除** | 与右侧会话列表功能重复，不做独立入口 |
| 3 | 折叠态图标校准 | ✅ **要做**（前端） | 折叠态仅保留 4 图标：会话/法规/基准/记录 |
| 4 | 顶栏 tab 映射 | 🔲 待定 | 见《设计稿落地与前端改造清单》§5 |
| 5 | 顶栏用户区 | ⏸️ 暂缓 | 无登录体系，暂不放 |

---

## 2. 数据资产盘点（已收集完毕，无需再采集）

### 2.1 政策法规库 `rag-data/processed/national/tax_law/`（53 个 .md）

```
个人所得税法.md / 企业所得税法.md / 增值税法.md / 印花税法.md / 契税法.md /
税收征收管理法.md / 社会保险法.md / 个人所得税法实施条例.md /
国务院关于印发个人所得税专项附加扣除暂行办法的通知.md / …（共 53 个）
```

- 每个文件为带 YAML frontmatter 的 Markdown（title / source_url / category 等）
- 分类：法律 / 行政法规 / 部门规章 / 规范性文件（可由 frontmatter 或文件名推断）

### 2.2 行业指标基准 `rag-data/processed/national/rates/industry_benchmark.json`

```
顶层结构: { tool_usage, meta, industries }
industries: 20 个行业门类 × 97 个细分行业 × 10 项指标
指标: vat_burden(增值税税负率) / cit_burden(企业所得税税负率) / gross_margin(毛利率)
      net_margin(净利率) / receivable_turnover(应收周转) / inventory_turnover(存货周转)
      debt_ratio(资产负债率) / current_ratio(流动比率) / quick_ratio(速动比率) / expense_ratio(费用率)
每项: {low, high} 范围对象，不适用为 null
```

### 2.3 城市数据 `rag-data/processed/metadata/cities_index.json` + `cities/zhengzhou/`

```
cities_index: { _description, _updated, cities: { zhengzhou: { city_code, province,
               data_version, social_insurance: {effective_from/to, file} } } }
cities/zhengzhou/social_insurance.json: 郑州社保缴费基数/比例（MVP 已用）
```

> **路由决策**：政策法规 = 全国统一库（`national/tax_law`）；城市差异化数据 = `cities/{city_code}` 目录，MVP 仅郑州，架构预留多城市扩展。

---

## 3. 新增接口设计

> 风格对齐现有 `routers/tax.py` / `routers/social.py`（FastAPI APIRouter + pydantic 响应模型 + 中文注释）。
> 新增文件：`backend/routers/library.py`（资料库路由）+ `backend/services/library_engine.py`（数据读取/整理逻辑）。
> 注册：`backend/main.py` 的 `include_router` 追加。

### 3.1 `GET /api/library/documents` — 政策法规列表

**用途**：资料库「政策法规」页展示法规清单（前端列表页数据源）。

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
      "updated": "2026-07-27",
      "source": "fgk.chinatax.gov.cn"
    }
  ]
}
```

- `category`：法律 / 行政法规 / 部门规章 / 规范性文件（从 frontmatter 或文件名归类）
- 支持查询参数：`?category=法律&keyword=个税&limit=20&offset=0`（前端搜索/筛选）

### 3.2 `GET /api/library/documents/{id}` — 法规详情

**用途**：点击列表项查看法规正文（Markdown 渲染）。

**响应**：

```json
{
  "id": "个人所得税法",
  "title": "中华人民共和国个人所得税法",
  "category": "法律",
  "content": "# 中华人民共和国个人所得税法\n\n（1980年…）\n\n第一条 …",
  "updated": "2026-07-27"
}
```

### 3.3 `GET /api/library/benchmark` — 行业指标基准

**用途**：资料库「行业基准」页展示/查询 97 条行业财务指标。

**请求参数**：`?category=制造业`（行业门类，可选）`&keyword=电子`（细分行业关键词，可选）

**响应**：

```json
{
  "total": 97,
  "industries": [
    {
      "category": "制造业",
      "sub_industry": "电子设备制造业",
      "indicators": {
        "vat_burden": { "low": 0.8, "high": 2.1 },
        "cit_burden": { "low": 0.6, "high": 1.5 },
        "gross_margin": { "low": 12.5, "high": 28.3 }
      }
    }
  ]
}
```

> 指标字段与 `industry_benchmark.json` 原生结构一致（10 项全量返回，前端按需展示）。

### 3.4 可选 `GET /api/library/cities` — 城市列表（预留，MVP 可不做）

**用途**：城市切换 UI 数据源。MVP 仅郑州，返回单条即可；架构预留多城市。

---

## 4. 实施步骤

1. **新建 `backend/services/library_engine.py`**：
   - `list_documents(category, keyword, limit, offset)`：扫描 `DATA_DIR/national/tax_law/*.md`，读 YAML frontmatter（title/category/updated/source），按参数过滤排序
   - `get_document(doc_id)`：读取单个 .md 全量内容（去 frontmatter，返回正文 Markdown）
   - `query_benchmark(category, keyword)`：读 `industry_benchmark.json`，按行业门类/细分关键词过滤
   - 缓存：模块级 `lru_cache`（文件不大，53 个 md 首读后缓存；benchmark 84KB 全量缓存）
2. **新建 `backend/routers/library.py`**：3 个 GET 端点，pydantic 响应模型，复用现有 `config.DATA_DIR`
3. **注册路由**：`backend/main.py` → `include_router(library.router, prefix="/api/library", tags=["资料库"])`
4. **前端对接**（另见《设计稿落地与前端改造清单》C 项）：Sidebar「政策法规/行业基准」入口 → 资料库页调用上述接口
5. **验收**：
   - `curl localhost:8000/api/library/documents` → 53 条，字段完整
   - `curl localhost:8000/api/library/documents/个人所得税法` → 正文完整返回
   - `curl "localhost:8000/api/library/benchmark?category=制造业"` → 过滤正确
   - 前端点击「政策法规」→ 列表 → 点击 → 正文渲染；「行业基准」→ 表格展示

---

## 5. 前端配套改动（联动）

| 项 | 内容 | 工作量 |
|---|------|:---:|
| 折叠态图标校准 | 折叠态仅保留 会话/法规/基准/记录 4 图标（删导航类图标） | 0.25 天 |
| 资料库入口 | Sidebar「资料库」区 2 项（政策法规/行业基准）→ 点击切换视图 | 0.5 天 |
| 政策法规页 | 列表 + 搜索/分类筛选 + 详情 Markdown 渲染 | 0.5-1 天 |
| 行业基准页 | 搜索框 + 表格展示（指标范围） | 0.5-1 天 |
| 申报记录 | ❌ 删除（产品决策） | — |

---

## 6. 待确认

1. **政策法规分类规则**：是否需要按「法律/行政法规/部门规章」细分筛选，还是 MVP 只做全文关键词搜索？
2. **行业基准展示粒度**：全部 10 项指标展示，还是只展示核心 5 项（税负率/毛利率/净利率/周转率/负债率）？
3. **法规正文渲染**：前端直接用 Markdown 渲染库（如 react-markdown），还是后端转 HTML？
