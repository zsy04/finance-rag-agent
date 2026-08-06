# 财务RAG · 资料库接口 · 前端联调文档

> **用途**：前端开发「资料库」页面（政策法规列表/正文、行业指标基准）时按此文档联调
> **后端状态**：✅ 已实现（2026-08-06），接口已注册，冒烟测试通过
> **新增依赖**：后端 `requirements.txt` 已加 `markdown~=3.8.0`（Markdown→HTML 转换用）
> **适用范围**：只读接口，不涉及登录、不依赖 LLM / Qdrant（纯文件读取，秒回）

---

## 一、接口总览

| 功能 | 方法 | 路径 | 鉴权 | 说明 |
|------|:--:|------|:--:|------|
| 政策法规列表 | GET | `/api/library/documents` | 无 | 分类/关键词过滤 + 分页 |
| 法规正文 | GET | `/api/library/documents/{doc_id}` | 无 | Markdown 已转 HTML，直接渲染 |
| 行业指标基准 | GET | `/api/library/benchmark` | 无 | 97 个细分行业 × 10 项指标 |
| 城市列表（预留） | GET | `/api/library/cities` | 无 | MVP 仅郑州 |

> 前端通过 Vite 代理访问：`/api` → `http://localhost:8000`（现有配置即可，无需改动）。

---

## 二、启动前置（后端）

后端需安装新增依赖后重启：

```bash
# 项目根目录
pip install -r requirements.txt
# 或单独安装
pip install "markdown~=3.8.0"
```

启动方式不变（`start.bat` 或 `uvicorn main:app --port 8000`，在 `backend/` 下）。

---

## 三、接口详情

### 3.1 政策法规列表 `GET /api/library/documents`

**请求参数**（全部可选）

| 参数 | 类型 | 默认 | 说明 |
|------|------|:--:|------|
| `category` | string | 无 | 法规分类，精确匹配：`法律` / `行政法规` / `部门规章` / `规范性文件` |
| `keyword` | string | 无 | 标题/文件名模糊匹配 |
| `limit` | int | 20 | 每页条数，范围 1~100 |
| `offset` | int | 0 | 分页偏移量 |

**响应示例**（已核实真实数据）

```json
{
  "total": 53,
  "items": [
    {
      "id": "个人所得税法",
      "title": "个人所得税法",
      "category": "法律",
      "level": "法律",
      "updated": "2026-07-28",
      "source": "fgk.chinatax.gov.cn"
    }
  ]
}
```

**字段说明**

| 字段 | 说明 |
|------|------|
| `total` | **过滤后**的总条数（分页前），用于前端分页 |
| `id` | 法规唯一标识，中文，即文件名去 `.md`；**取正文时需 URL 编码** |
| `title` | 法规简称（frontmatter `doc_title`） |
| `category` / `level` | 法规分类（同一推断值，前端可只用一个） |
| `updated` | 数据清洗日期 `YYYY-MM-DD` |
| `source` | 来源域名（如 `fgk.chinatax.gov.cn`） |

**真实数据分布**（供分类 Tab 设计参考）：法律 32 条 / 行政法规 6 条 / 部门规章 6 条 / 规范性文件 9 条。

### 3.2 法规正文 `GET /api/library/documents/{doc_id}`

**路径参数**：`doc_id` = 列表返回的 `id`，中文需 `encodeURIComponent`。

**响应示例**

```json
{
  "id": "个人所得税法",
  "title": "个人所得税法",
  "category": "法律",
  "html_content": "<h1>个人所得税法</h1>\n\n<p>1980年9月10日第五届全国人民代表大会…</p>\n\n<h3>第一条</h3>\n<p>在中国境内有住所…</p>"
}
```

**说明**
- `html_content` 已由后端 Markdown→HTML（启用 `tables`、`fenced_code` 扩展），前端直接注入渲染即可，**不要二次转义**
- 正文原文无 H1，后端已补一个 `<h1>` 标题（用 `title`），保证渲染美观
- 不存在 → **HTTP 404**，`detail` 为错误信息

### 3.3 行业指标基准 `GET /api/library/benchmark`

**请求参数**（全部可选）

| 参数 | 类型 | 说明 |
|------|------|------|
| `category` | string | 行业门类精确匹配（如 `制造业`、`住宿和餐饮业`） |
| `keyword` | string | 细分行业名模糊匹配（如 `电子`） |

**响应示例**（已核实真实数据，20 个门类 × 97 个细分行业）

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
        "expense_ratio": { "low": 0.08, "high": 0.15 },
        "ar_turnover": { "low": 3, "high": 8 },
        "inventory_turnover": { "low": 2, "high": 6 },
        "debt_ratio": { "low": 0.4, "high": 0.6 },
        "current_ratio": { "low": 1, "high": 2 },
        "quick_ratio": { "low": 0.5, "high": 1.2 }
      }
    }
  ]
}
```

**10 项指标字段对照**（⚠️ 字段名后端原样透传，勿改名）

| key | 中文名 | 单位 | 前端显示 |
|-----|--------|------|---------|
| `vat_burden` | 增值税税负率 | 比率 | ×100 显示 % |
| `cit_burden` | 企业所得税税负率 | 比率 | ×100 显示 % |
| `gross_margin` | 毛利率 | 比率 | ×100 显示 % |
| `net_margin` | 净利率 | 比率 | ×100 显示 % |
| `expense_ratio` | 费用率 | 比率 | ×100 显示 % |
| `ar_turnover` | 应收账款周转率 | 次/年 | 直接显示 |
| `inventory_turnover` | 存货周转率 | 次/年 | 直接显示 |
| `debt_ratio` | 资产负债率 | 比率 | ×100 显示 % |
| `current_ratio` | 流动比率 | 倍 | 直接显示 |
| `quick_ratio` | 速动比率 | 倍 | 直接显示 |

**⚠️ 关键注意**：
1. **`ar_turnover` 不是 `receivable_turnover`**，后端返回什么前端就消费什么
2. 指标值是**小数**（0.02 = 2%），后端不 ×100、不格式化，**显示层由前端处理**
3. `low` / `high` 为行业平均范围，个别行业某项指标为 `null`（表示不适用，如金融业周转率），前端需处理空值
4. 每项指标都返回，缺值的为 `null`，前端遍历固定 10 个 key 即可

### 3.4 城市列表（预留）`GET /api/library/cities`

**响应示例**

```json
{
  "total": 1,
  "cities": [
    {
      "code": "zhengzhou",
      "name": "郑州",
      "province": "河南",
      "city_code": "410100",
      "data_version": "2025H2"
    }
  ]
}
```

MVP 仅郑州，架构已预留城市扩展；本期前端可不接。

---

## 四、TypeScript 类型定义（供前端直接使用）

```typescript
// ---- 政策法规 ----
interface LibraryDocument {
  id: string;          // 中文标识，取正文需 encodeURIComponent
  title: string;
  category: '法律' | '行政法规' | '部门规章' | '规范性文件';
  level: string;       // 同 category
  updated: string;     // YYYY-MM-DD
  source: string;      // 来源域名
}

interface LibraryListResponse {
  total: number;
  items: LibraryDocument[];
}

interface LibraryDetailResponse {
  id: string;
  title: string;
  category: string;
  html_content: string; // 已转 HTML，直接注入
}

// ---- 行业指标基准 ----
type BenchmarkKey =
  | 'vat_burden' | 'cit_burden' | 'gross_margin' | 'net_margin' | 'expense_ratio'
  | 'ar_turnover' | 'inventory_turnover' | 'debt_ratio' | 'current_ratio' | 'quick_ratio';

interface ValueRange {
  low: number | null;  // 不适用时为 null
  high: number | null;
}

interface BenchmarkIndustry {
  category: string;        // 行业门类
  sub_industry: string;    // 细分行业
  indicators: Record<BenchmarkKey, ValueRange>;
}

interface BenchmarkResponse {
  total: number;
  industries: BenchmarkIndustry[];
}

// ---- 城市（预留）----
interface CityInfo {
  code: string;
  name: string;
  province: string;
  city_code: string;
  data_version: string;
}

interface CitiesResponse {
  total: number;
  cities: CityInfo[];
}
```

---

## 五、前端实现要点

1. **分类 Tab**：`category` 四个固定值直接作为 Tab 参数，不传 = 全部
2. **分页**：`total` 是过滤后的总数；建议 limit=20 分页，滚动加载或页码均可
3. **正文渲染**：`html_content` 用 `v-html` / `dangerouslySetInnerHTML` 注入；渲染容器需要自行添加基础排版样式（h1/h3/p/table 间距、字号），后端不做任何样式
4. **指标展示**：
   - 比率类（vat/cit/margin/ratio 相关）`× 100 + '%'`，如 `0.02 → 2%`
   - 周转/流动类直接显示数字，如 `ar_turnover 3~8 次/年`
   - `null` 值显示「不适用」或「—」
5. **URL 编码**：`doc_id` 是中文（如 `个人所得税法`），请求时用 `encodeURIComponent(doc_id)`
6. **404 处理**：正文接口 404 时提示「未找到该法规」
7. **接口风格**：全部 GET、无鉴权、无分页字段之外的复杂逻辑，可放心联调

---

## 六、联调验收清单（后端已测，前端可复测）

```bash
# 1. 列表全量（应返回 total=53）
curl "http://localhost:8000/api/library/documents"

# 2. 分类过滤（total=32）
curl "http://localhost:8000/api/library/documents?category=法律"

# 3. 关键词模糊（total=15）
curl "http://localhost:8000/api/library/documents?keyword=个人"

# 4. 分页（limit=10 offset=30 → 返回 10 条）
curl "http://localhost:8000/api/library/documents?limit=10&offset=30"

# 5. 法规正文（html_content 含 <h1>、<p> 标签）
curl "http://localhost:8000/api/library/documents/个人所得税法"

# 6. 404（不存在 → HTTP 404）
curl "http://localhost:8000/api/library/documents/不存在的法规"

# 7. 行业基准全量（total=97）
curl "http://localhost:8000/api/library/benchmark"

# 8. 门类过滤（total=31）
curl "http://localhost:8000/api/library/benchmark?category=制造业"

# 9. 细分行业模糊（total=2）
curl "http://localhost:8000/api/library/benchmark?keyword=电子"

# 10. 城市列表（预留）
curl "http://localhost:8000/api/library/cities"
```

**预期**：全部 200；正文含 HTML 标签；benchmark 的 `indicators` 恰好 10 项且含 `ar_turnover`。

---

## 七、前端页面建议（与设计稿对齐）

- **政策法规页**：分类 Tab + 搜索框 + 法规卡片列表（title / category 徽标 / updated / source）→ 点击进正文页
- **行业基准页**：门类下拉（20 个门类）/ 搜索 + 细分行业表格（10 项指标 low~high 区间展示）
- 正文页可加「返回列表」面包屑，正文容器最大宽度约 800px 阅读体验最佳

---

*文档生成：2026-08-06 · 对应后端文件 `backend/services/library_engine.py` + `backend/routers/library.py`（已注册到 `main.py`）*
