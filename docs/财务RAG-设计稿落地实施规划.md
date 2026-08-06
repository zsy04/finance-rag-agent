# 财务 RAG Agent · 设计稿落地实施规划（统合版）

> **用途**：设计稿（Ardot「网页设计-自定义提示词」）落地到前后端的**唯一实施蓝图**。统合原《设计稿落地与前端改造清单》《后端补充需求-地区资料库接口》《前端改造实施清单》三份文档，已定案决策直接固化，仅保留极少数待确认项。
> **依据**：设计稿两屏（展开 300px / 折叠 68px）+ `rag-data/processed/**` 数据盘点 + 前端现有代码实况
> **更新**：2026-08-06 统合创建；三项决策定案（法规分类筛选 / 基准全 10 项指标 / 法规正文后端转 HTML；申报记录不做）
> **2026-08-06 晚更新**：**前后端已全部实施完成** —— 前端任务 A/B/C + 3 新视图已落地（tsc 零错误）；后端资料库 3+1 接口已实现并联调通过（10 项验收全绿）；前端已从 mock 切换真实接口。详见《财务RAG-资料库接口-前端联调文档》。

---

## 1. 产品决策总记录

| # | 决策项 | 结论 | 状态 |
|---|--------|------|:---:|
| 1 | 顶栏功能 tab 导航（4 tab） | ✅ 做 | 定案 |
| 2 | 侧边栏重构（会话区 + 资料库区） | ✅ 做 | 定案 |
| 3 | 折叠态图标校准 | ✅ 做；**仅 3 个图标：会话 / 政策法规 / 行业基准**（申报记录已删，不占位） | 定案 |
| 4 | 申报记录入口 | ❌ **不做**（与右侧会话列表重复） | 定案 |
| 5 | 政策法规分类 | ✅ **按分类筛选**（法律/行政法规/部门规章/规范性文件） | 定案 |
| 6 | 行业基准展示粒度 | ✅ **全部 10 项指标** | 定案 |
| 7 | 法规正文渲染 | ✅ **后端转 HTML**（后端返回 HTML 字符串，前端直接渲染） | 定案 |
| 8 | 顶栏用户区 | ⏸️ 暂缓（无登录体系） | 待定 |
| 9 | 顶栏 4 tab → 视图映射 | ✅ **方案 2：申报指引 = 独立静态指引页（复用 `national/operations/个税操作指南.md`），材料生成 = form** | 定案 |
| 10 | 展开态宽度 | ✅ **300px（设计稿）** | 定案 |

---

## 2. 设计稿定稿状态

| 项目 | 内容 |
|------|------|
| 画布 | Ardot「网页设计-自定义提示词」，两屏上下对比（第一屏 y≈0、第二屏 y=1200） |
| 第一屏（状态 A） | 侧边栏**展开态 300px**：会话区（标题+新建+列表）+ 分隔线 + 资料库区（政策法规/行业基准） |
| 第二屏（状态 B） | 侧边栏**折叠态 68px**：3 个图标（会话/法规/基准），悬停展开 300px |
| 顶栏 | logo + 产品名 + 4 功能 tab + 新会话按钮（用户区暂缓） |
| 主内容区 | 智能问答默认；税率计算 / 申报材料 / 资料库两页 |
| 视觉 | 暖白 #F5F6F8、深蓝 #014DB2、白卡片 12-16px 圆角、轻阴影、Noto Sans SC + Inter |

---

## 3. 前端改造任务

> 改动文件：`TopBar.tsx` / `Sidebar.tsx` / `types.ts` / `App.tsx` / 图标资源。纯前端，不依赖后端。

### 任务 A — 顶栏 tab 导航

- `types.ts`：`ActiveView = 'chat' | 'calculator' | 'form' | 'guide' | 'documents' | 'benchmark'`（✅ 方案 2 已确认：新增 `guide` 视图承载申报指引静态页）
- `TopBar.tsx`：新增 4 tab（智能问答/税率计算/申报指引/材料生成），激活深蓝实心白字、非激活白底灰字，点击 `setActiveView`
  - 映射：智能问答→`chat`、税率计算→`calculator`、**申报指引→`guide`（独立静态指引页）**、材料生成→`form`
- `App.tsx`：补 `guide` / `documents` / `benchmark` 视图分支
- 申报指引页（新组件 `components/guide/GuideView.tsx`）：静态渲染 `rag-data/processed/national/operations/个税操作指南.md` 内容（标题 + 正文 Markdown，前端静态引用或后端只读接口）
- `Sidebar.tsx`：移除 3 个导航项（职责移交顶栏）
- 验收：4 tab 点击切换正常；激活样式对齐设计稿；Sidebar 不再显示导航项；申报指引页展示《个税操作指南》内容

### 任务 B — 侧边栏重构

```
┌─────────────────────────────┐
│ 会话             [+ 新建]    │  ← 会话区（独立，不依赖 hover）
│ 小微企业所得税优惠  3条 今天10:20 │
│ 个税专项附加扣除    5条 昨天   │
│ 增值税申报材料清单  2条 08-04 │
├─────────────────────────────┤  ← 分隔线
│ 资料库                       │  ← 资料库区
│ 📖 政策法规                   │
│ 📊 行业基准                   │
└─────────────────────────────┘
```

- 宽度：`w-16 hover:w-[300px]`（✅ 按设计稿 300px 已确认）
- 会话项元信息：`N 条消息 · 今天HH:MM/昨天/MM-DD`（按 `updated_at` 分档；数据源 `ThreadMeta.message_count/updated_at`，核对字段名）
- 资料库 2 项：政策法规 → `documents` 视图；行业基准 → `benchmark` 视图
- 折叠态：仅 3 图标，hover 展开显示全部
- 验收：展开 300px 结构与设计稿一致；元信息分档正确；资料库 2 项可点入

### 任务 C — 折叠态图标校准

- 折叠态图标 = **3 个**：会话 / 政策法规 / 行业基准（申报记录不占位）
- 图标资源：会话复用 `ChatSvg`（或新增 `icon-conversation.svg`）、法规复用 `DocumentSvg`、基准新增 `icon-benchmark.svg`（柱状图）
- 验收：折叠态仅 3 图标，与展开后菜单一致

---

## 4. 后端补充任务（地区资料库接口）

> 新文件：`backend/services/library_engine.py` + `backend/routers/library.py`；注册 `main.py`。数据已收集完毕，只读接口。

### 数据资产（已就绪）

| 数据 | 位置 | 规模 |
|------|------|------|
| 政策法规 | `rag-data/processed/national/tax_law/*.md` | 53 部（YAML frontmatter：title/category/doc_number/source_url 等） |
| 行业基准 | `rag-data/processed/national/rates/industry_benchmark.json` | 97 条 × 10 指标 |
| 城市索引 | `rag-data/processed/metadata/cities_index.json` | 郑州（预留多城市） |

### 行业基准 JSON 真实结构（2026-08-06 已核实，后端实现以此为准）

```json
{
  "tool_usage": { "...": "..." },
  "meta": { "total_industries": 97, "total_categories": 20, "...": "..." },
  "industries": [
    {
      "category": "农、林、牧、渔业",
      "sub_industry": "农业",
      "vat_burden": { "low": 0, "high": 0.02 },        // 比率小数（0.02 = 2%）
      "cit_burden": { "low": 0, "high": 0.05 },
      "gross_margin": { "low": 0.2, "high": 0.35 },
      "net_margin": { "low": 0.05, "high": 0.12 },
      "ar_turnover": { "low": 3, "high": 8 },           // 倍数（次）
      "inventory_turnover": { "low": 2, "high": 6 },
      "debt_ratio": { "low": 0.4, "high": 0.6 },
      "current_ratio": { "low": 1, "high": 2 },
      "quick_ratio": { "low": 0.5, "high": 1.2 },
      "expense_ratio": { "low": 0.08, "high": 0.15 }
    }
  ]
}
```

> ⚠️ **10 项指标字段名（后端必须原样透传，勿改名）**：`vat_burden` / `cit_burden` / `gross_margin` / `net_margin` / `ar_turnover`（应收周转，非 receivable_turnover）/ `inventory_turnover` / `debt_ratio` / `current_ratio` / `quick_ratio` / `expense_ratio`。比率类为小数（0~1），周转/流动类为倍数。`null` 表示该指标不适用。前端负责格式化显示（比率 ×100 加 %）。

### 接口设计

| 接口 | 用途 | 参数 | 响应要点 |
|------|------|------|---------|
| `GET /api/library/documents` | 法规列表 | `category`（法律/行政法规/部门规章/规范性文件）、`keyword`、`limit`、`offset` | `{total, items:[{id,title,category,level,updated,source}]}` |
| `GET /api/library/documents/{id}` | 法规正文 | — | `{id,title,category,html_content}`（**后端转 HTML**） |
| `GET /api/library/benchmark` | 行业基准 | `category`（行业门类）、`keyword`（细分行业） | `{total, industries:[{category,sub_industry,indicators:{10项}}]}`（**全 10 项原样透传**） |
| `GET /api/library/cities` | 城市列表 | — | MVP 仅郑州，预留扩展 |

### 实施要点

1. `library_engine.py`：
   - `list_documents(category, keyword, limit, offset)`：扫描 tax_law/*.md，读 frontmatter，按分类/关键词过滤
   - `get_document(doc_id)`：读 .md → **Markdown 转 HTML**（`markdown` 库或现有依赖），返回正文 HTML
   - `query_benchmark(category, keyword)`：读 JSON，过滤，**10 项指标原样透传**（字段名/小数格式不动，前端自行格式化）
   - `query_benchmark(category, keyword)`：读 JSON，过滤，**返回全部 10 项指标**
   - `lru_cache` 缓存（53 md + 84KB JSON，首读后缓存）
2. `routers/library.py`：3 GET 端点 + pydantic 响应模型，复用 `config.DATA_DIR`
3. `main.py`：`include_router(library.router, prefix="/api/library", tags=["资料库"])`
4. 验收：
   - `curl /api/library/documents?category=法律` → 过滤正确
   - `curl /api/library/documents/个人所得税法` → `html_content` 含 `<h1>/<p>` 标签
   - `curl "/api/library/benchmark?category=制造业"` → 10 项指标完整

---

## 5. 资料库页面联动（前端 × 后端）

| 视图 | 后端接口 | 前端页面 | 依赖 |
|------|---------|---------|------|
| 政策法规列表 | `GET /api/library/documents` | 列表 + 分类筛选 + 关键词搜索 | 后端 |
| 法规详情 | `GET /api/library/documents/{id}` | 直接渲染 `html_content`（`dangerouslySetInnerHTML` 或 iframe） | 后端 |
| 行业基准 | `GET /api/library/benchmark` | 搜索 + 表格（10 项指标范围） | 后端 |

> 后端就绪前，`documents` / `benchmark` 视图可先做「建设中」占位页。

---

## 6. 决策确认记录

> ✅ 全部决策已定案，无待确认项。执行时按 §1 决策总记录为准。

| # | 决策项 | 最终结论 |
|---|--------|---------|
| 6.1 | 顶栏 4 tab 映射 | 方案 2：申报指引 = 独立静态指引页（《个税操作指南.md》），材料生成 = form |
| 6.2 | 展开态宽度 | 300px（设计稿） |

## 7. 工作量汇总

| 模块 | 前端 | 后端 |
|------|:---:|:---:|
| A 顶栏 tab 导航（含 guide 静态页） | 0.5-1 天 | — |
| B 侧边栏重构 | 0.5-1 天 | — |
| C 折叠态图标（3 个） | 0.25 天 | — |
| 资料库接口 ×3 | — | 0.5-1 天 |
| 政策法规页 | 0.5-1 天 | — |
| 行业基准页 | 0.5-1 天 | — |
| 合计 | 2.5-4 天 | 0.5-1 天 |

## 8. 执行顺序建议

1. **后端先行**（资料库接口，0.5-1 天）→ 前端页面有数据可用
2. **前端任务 A**（顶栏 tab + guide 页）→ B（侧边栏重构）→ C（折叠态图标），纯前端 1.5-2.5 天
3. **资料库两页**（依赖接口）→ 联调验收

> ✅ 实施前置条件已全部满足（§6 决策全定案），可直接转开发任务。
