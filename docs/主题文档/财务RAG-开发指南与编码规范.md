---
doc_title: 财务RAG-开发指南与编码规范
category: devguide
source_docs:
  - 财务RAG-开发注意事项.md
  - 财务RAG-后端开发路线图.md
  - 前端开发-完整代码生成包.md
  - 后端资料库接口-AI代码生成上下文包.md
  - 财务RAG-项目补充与添加实施规划.md
重组日期: 2026-08-06
---

# 财务RAG-开发指南与编码规范

> **文档定位**：本项目（财务 RAG Agent「lest 财税助手」）开发阶段的**唯一规范参考**。前端复制 CSS 令牌、使用组件样式；后端参照 SSE 事件格式、API 协议与代码范式。
> **生成方式**：由 5 份来源文档重组而成（来源在 frontmatter 的 `source_docs` 中列出），规范条目、检查清单、模板代码均**全量保留**。
> **配套文档链**：`财务RAG-技术架构与Agent方案.md` + `财务RAG-UI设计方案.md`（上游设计）→ 本文档（编码规范）→ `财务RAG-前后端对照表.md`（接口契约）。

---

## 1. 开发环境准备

### 1.1 Python 后端环境（Python 3.13 + venv）

> 来源：`财务RAG-后端开发路线图.md` Step 1、开发注意事项"环境与资源"。

**版本要求**：Python ≥ 3.10（LangChain 要求）。项目已使用 **3.13.12** 无问题。
**依赖要求**：上下文工程中间件 `SummarizationMiddleware` / `ToolErrorMiddleware` 需要 **langchain 1.3.14** 才具备（`财务RAG-项目补充与添加实施规划.md` §3.1 已查证 API）。

```bash
mkdir backend && cd backend
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
```

```bash
pip install fastapi uvicorn[standard] sse-starlette
pip install langchain-deepseek langgraph langchain-core langchain
pip install FlagEmbedding qdrant-client pydantic python-dotenv
```

**项目骨架文件**：

```
backend/
├── main.py           # FastAPI 入口
├── config.py         # 环境变量 + 常量
├── requirements.txt
└── .env              # DEEPSEEK_API_KEY=sk-xxx
```

### 1.2 Node 前端环境（React + Vite + shadcn/ui）

> 来源：`前端开发-完整代码生成包.md` §1.1。

在 `F:\lest\` 目录下执行：

```bash
cd F:\lest
npm create vite@latest frontend -- --template react-ts
cd F:\lest\frontend
npx shadcn@latest init -d
npx shadcn@latest add button input select card textarea tooltip dialog
npm install lucide-react react-markdown remark-gfm @radix-ui/react-tooltip
npm install -D vite-plugin-svgr
```

### 1.3 Docker Qdrant（向量库）

> 来源：`财务RAG-后端开发路线图.md` Step 3 前置 + 开发注意事项"环境与资源"。

- **Docker Desktop 已安装** + Qdrant 镜像已拉取 → `docker compose up -d`（`docker-compose.yml` 在项目根目录）。
- **启动顺序**：必须在 Step 3（向量化入库）之前 `docker-compose up -d`。
- **演示提示**：演示时提前 5 分钟启动，关掉微信/Chrome 等重应用释放内存。
- **Dashboard**：`http://localhost:6333/dashboard` —— 可视化查看向量分布，演示时打开这个页面展示。
- **collection**：`finance_knowledge`（dense 1024d + sparse 双向量）。
- **验证**：`curl http://localhost:6333/collections/finance_knowledge` → 返回 collection 信息，点数 > 0。

### 1.4 .env 配置

> 来源：`财务RAG-后端开发路线图.md`（.env 说明 + `config.py`）。

`.env` 文件放在 `backend/.env`，包含 `DEEPSEEK_API_KEY=sk-xxx`。**不要提交到 Git**。

`config.py`：

```python
import os
from dotenv import load_dotenv
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "finance_knowledge"
BGE_MODEL_PATH = "BAAI/bge-m3"
RERANKER_MODEL_PATH = "BAAI/bge-reranker-v2-m3"
```

### 1.5 启动三服务

> 来源：`前端开发-完整代码生成包.md` §15（端口与代理）+ `财务RAG-后端开发路线图.md`（开发联调）。

```
开发环境：
  前端 Vite Dev Server :5173
  后端 FastAPI         :8000
  Qdrant Dashboard     :6333
```

- 前端代码中所有 API 请求使用相对路径 `/api/*`，由 Vite 代理（配置在 `F:\lest\frontend\vite.config.ts`）转发到 `localhost:8000`，无需 CORS 配置。
- 后端 `main.py` 运行：`uvicorn main:app --host 0.0.0.0 --port 8000`。
- 模型资源占用（开发注意事项"环境与资源"）：
  - BGE-M3 首次加载从 HuggingFace 下载约 **2.2GB** 模型文件到 `~/.cache/huggingface/`，需联网；之后秒加载。
  - BGE-Reranker 首次下载约 **1.5GB**。两个模型总计约 3.7GB。
  - BGE-M3 fp16 占用约 2GB 显存，Reranker 约 1.5GB，DeepSeek 走 API 不占显存。RTX 4060 8GB 绰绰有余。

---

## 2. 编码规范总则

### 2.1 CSS 设计令牌（完整定义，可直接复制进 globals.css）

> 来源：`财务RAG-开发注意事项.md` 一、设计令牌。前端直接复制到 `globals.css`。
> ⚠️ 注：`前端开发-完整代码生成包.md` §2 也含一份令牌（Tailwind v4 版，写入 `src/index.css`），主色/中性色/字体/圆角/阴影/过渡与本表一致，仅语义色取值不同（success #10B981 / warning #F59E0B / error #EF4444）。以本文档 `globals.css` 版本为权威。

```css
:root {
  /* ═══ 主色调 — 深藏蓝 ═══ */
  --color-primary: #014DB2;
  --color-primary-light: #EBF2FD;
  --color-primary-dark: #001645;

  /* ═══ 中性色 ═══ */
  --color-text-primary: #0A1628;
  --color-text-secondary: #6B7280;
  --color-text-tertiary: #9CA3AF;
  --color-bg-page: #F5F6F8;
  --color-bg-surface: #FFFFFF;
  --color-border: #E5E7EB;

  /* ═══ 语义色 ═══ */
  --color-success: #15803D;
  --color-warning: #B45309;
  --color-error: #B91C1C;
  --color-info: #014DB2;

  /* ═══ 字体 ═══ */
  --font-primary: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-mono: 'JetBrains Mono', 'Courier New', monospace;

  /* ═══ 字号 ═══ */
  --text-xs: 0.75rem; --text-sm: 0.875rem; --text-base: 1rem;
  --text-lg: 1.125rem; --text-xl: 1.25rem; --text-2xl: 1.5rem; --text-3xl: 1.875rem;

  /* ═══ 间距（4px基准） ═══ */
  --space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem;
  --space-4: 1rem; --space-6: 1.5rem; --space-8: 2rem; --space-12: 3rem;

  /* ═══ 圆角 ═══ */
  --radius-sm: 4px; --radius-md: 6px; --radius-lg: 8px; --radius-full: 9999px;

  /* ═══ 阴影 ═══ */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.06);
  --shadow-md: 0 2px 4px rgba(0,0,0,0.08);

  /* ═══ 过渡 ═══ */
  --transition-fast: 120ms ease;
  --transition-base: 200ms ease;
}
```

**硬约束**（来自 `前端开发-完整代码生成包.md` §2）：所有颜色必须用 CSS 变量，不得硬编码 `#014DB2` 等。

### 2.2 组件样式规范（基于 shadcn/ui 定制）

> 来源：`财务RAG-开发注意事项.md` §2.1。

**按钮**：

```css
.btn-primary { background: var(--color-primary); color: #FFF; height: 40px; border-radius: 6px; font-weight: 500; }
.btn-primary:hover { background: var(--color-primary-dark); transform: translateY(-1px); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary { background: var(--color-bg-surface); color: var(--color-primary); border: 1px solid var(--color-primary); height: 40px; border-radius: 6px; }
.btn-secondary:hover { background: var(--color-primary-light); }
```

**输入框**：

```css
.input { height: 40px; border: 1px solid var(--color-border); border-radius: 6px; padding: 0 12px; font-size: 16px; }
.input:focus { border-color: var(--color-primary); box-shadow: 0 0 0 3px rgba(1,77,178,0.15); outline: none; }
```

**结果卡片**：

```css
.result-card { background: #FFF; border: 1px solid #E2E8F0; border-left: 4px solid var(--color-primary); border-radius: 8px; padding: 16px; }
```

**消息气泡**：

```css
.bubble-user { background: var(--color-primary); color: #FFF; border-radius: 16px 16px 4px 16px; max-width: 70%; padding: 12px 16px; margin-left: auto; }
.bubble-ai   { background: var(--color-bg-page); color: var(--color-text-primary); border-radius: 16px 16px 16px 4px; max-width: 85%; padding: 12px 16px; }
```

**示例问题**：

```css
.suggestion-chip { background: var(--color-bg-page); border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 16px; cursor: pointer; }
.suggestion-chip:hover { background: var(--color-primary-light); border-color: #93C5FD; }
```

**导航项**（顶栏 tab，2026-08-06 设计稿落地后导航从侧边栏移到顶栏）：

```css
.nav-tab { display: flex; align-items: center; gap: 8px; padding: 8px 18px; border-radius: 8px; font-size: 14px; cursor: pointer; }
.nav-tab.active { background: var(--color-primary); color: #FFFFFF; }
.nav-tab:not(.active) { background: #FFFFFF; color: var(--color-text-secondary); }
```

**组件样式速查表（Tailwind class 直接复制）**（来自 `前端开发-完整代码生成包.md` §11）：

| 元素 | Tailwind Class |
|------|---------------|
| 主按钮 | `bg-[var(--color-primary)] text-white h-10 px-4 rounded-[6px] font-medium hover:bg-[var(--color-primary-dark)] hover:-translate-y-px transition-all duration-[120ms] disabled:opacity-50` |
| 次按钮 | `bg-white text-[var(--color-primary)] border border-[var(--color-primary)] h-10 px-4 rounded-[6px] font-medium hover:bg-[var(--color-primary-light)] transition-all` |
| 输入框 | `h-10 border border-[var(--color-border)] rounded-[6px] px-3 text-base focus:border-[var(--color-primary)] focus:ring-[3px] focus:ring-[var(--color-primary-light)] outline-none transition-all` |
| 用户气泡 | `bg-[var(--color-primary)] text-white rounded-[16px_16px_4px_16px] max-w-[70%] px-4 py-3 ml-auto` |
| AI 气泡 | `bg-[var(--color-bg-page)] text-[var(--color-text-primary)] rounded-[16px_16px_16px_4px] max-w-[85%] px-4 py-3` |
| 结果卡片 | `bg-white border border-[#E2E8F0] border-l-4 border-l-[var(--color-primary)] rounded-[8px] p-4` |
| 示例问题 | `bg-[var(--color-bg-page)] border border-[#E2E8F0] rounded-[8px] p-3 text-sm cursor-pointer hover:bg-[var(--color-primary-light)] hover:border-[#93C5FD] transition-all` |
| 骨架屏 | `animate-pulse bg-gray-200 rounded` |
| 金额数字 | `font-mono` |
| 加载图标 | `<XxxSvg className="icon-spinning" />` |
| 导航项 | `w-full h-12 flex items-center gap-3 px-4 rounded-[6px] text-sm cursor-pointer transition-all` |
| 导航项-选中 | `bg-[var(--color-primary-light)] text-[var(--color-primary)]` |
| 错误气泡 | `border-l-4 border-l-[var(--color-error)]` |

### 2.3 布局约束

> 来源：`财务RAG-开发注意事项.md` §2.2。

| 区域 | 约束 |
|------|------|
| 顶栏 | 全宽 + `sticky top-0 z-10`，高度 64px；中部 4 功能 tab（智能问答/税率计算/申报指引/材料生成），右侧新会话按钮 |
| 左侧栏 | 默认 64px（折叠，仅 3 图标：会话/政策法规/行业基准）→ hover 扩至 **300px**（会话区 + 资料库区）；`transition: width 200ms ease; transition-delay: 50ms` |
| 主内容区 | `overflow-y: auto` |
| 输入框区域 | 底部固定，`sticky bottom-0` |

> ⚠️ **MVP 仅桌面端（≥768px）**，移动端 Phase 2。布局最小宽度 `min-width: 768px`。

补充（`前端开发-完整代码生成包.md` §10.2，2026-08-06 设计稿落地更新）：顶栏高度 48→64px；中部 4 功能 tab（导航从侧边栏移入）；**移除右侧新会话按钮/郑州标识**（新建会话已集成到左侧会话栏）。左侧栏 hover 扩至 300px（早期版本为 200px，以 300px 为准）。加载旋转动画：

```css
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.icon-spinning {
  animation: spin 1s linear infinite;
}
```

### 2.4 后端代码风格

> 来源：`后端资料库接口-AI代码生成上下文包.md` §3 代码范式（严格遵守、模仿现有风格）；`财务RAG-后端开发路线图.md` Step 1 `config.py` 常量区。以下条目综合自上述来源，并补充项目通用约定。

#### 薄路由 + 厚服务

- 路由函数在 `routers/`，纯逻辑在 `services/`（**薄路由 + 厚服务**）。
- **不要在 routers 里写大段逻辑**：路由只做参数解析/校验/组装响应，核心逻辑放 services 层纯函数。

路由层模板（参照 `backend/routers/tax.py`）：

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

服务层模板（参照 `backend/services/tax_engine.py` 的纯函数风格）：

```python
# backend/services/library_engine.py
from pathlib import Path
from functools import lru_cache
from config import DATA_DIR

TAX_LAW_DIR = DATA_DIR / "national" / "tax_law"
BENCHMARK_FILE = DATA_DIR / "national" / "rates" / "industry_benchmark.json"
```

#### 其他风格要点

| 规范 | 说明 | 依据 |
|------|------|------|
| Query + 中文 description | 参数用 `Query` + 中文 `description`（对齐 tax.py 的 Field 风格） | 后端资料库上下文包 §3 |
| 无 `any` | 禁用 `any` 类型，全部显式类型注解 | 后端资料库上下文包 §3 |
| 无 try/except 吞错 | 让异常自然抛出，不吞错 | 后端资料库上下文包 §3 / §7 / §8 |
| 中文注释 | 全项目中文注释 | 后端资料库上下文包 §3 |
| `\| None` 注解 | 可选参数用 `str \| None` 联合类型 | 后端资料库上下文包 §3 |
| `lru_cache` 懒加载 | `@lru_cache(maxsize=1)` 缓存目录扫描与 JSON 读取结果，文件小不占内存；模型用单例（`__new__` 写法）避免重复加载 | 后端资料库上下文包 §6 / §8；路线图 Step 4 |
| logger 标配 | 每个新模块入口建模块级 `logger = logging.getLogger(__name__)`，关键路径（检索耗时、工具调用、错误）记录日志 | 项目通用约定 |
| import 分组 | 分组顺序：标准库 → 第三方 → 项目内部；组间空行分隔 | 项目通用约定 |
| 常量区 | 环境变量 + 路径常量集中在 `config.py`（如 `QDRANT_URL`、`QDRANT_COLLECTION`、`BGE_MODEL_PATH`），代码内不散落魔法字符串 | 路线图 Step 1 `config.py` |
| 显式 UTF-8 | 所有 .md 为 UTF-8，`open(..., encoding='utf-8')` 必须显式指定 | 后端资料库上下文包 §8 |

#### 编码陷阱（后端，来自 `财务RAG-后端开发路线图.md`）

| 陷阱 | 现象 | 正确做法 |
|------|------|---------|
| `@tool` 函数无类型提示 | Agent 调用时参数乱传 | 每个参数必须有类型注解 + 描述（见 §6 Step 5 模板） |
| `@tool` 函数返回非 str | LangChain 要求工具返回字符串 | 复杂结果用 `json.dumps(result, ensure_ascii=False)` 包一层 |
| `temperature` 设为 > 0 | Agent 偶尔选错工具 | Tool Calling 场景 `temperature=0`，保证确定性 |
| Qdrant collection 未创建 | `search_batch` 报 404 | Step 3 必须先执行 |
| SSE 事件格式不对 | 前端收不到事件 | 格式必须是 `event: xxx\ndata: {...}\n\n`，注意两个换行 |
| `astream_events` 无 `version="v2"` | 事件格式不兼容 | 加 `version="v2"` 参数 |
| 中文 JSON 被转义 | 前端显示 `\uXXXX` | `json.dumps(..., ensure_ascii=False)` |
| Reranker 重复加载 | 每次查询重新初始化模型（巨慢） | 用单例模式（`__new__` 写法） |
| Embedder 重复加载 | 同上 | 同上 |

---

## 3. Agent 工具开发规范

### 3.1 工具调度 5 规则

> 来源：`财务RAG-开发注意事项.md` §3.3（原文）。

| 规则 | 说明 |
|------|------|
| **信息不足时反问** | 缺少计算所需字段（收入类型、金额、城市）→ 先反问 1-2 个问题，不要猜测 |
| **计算走代码** | `calculate_income_tax` 和 `query_social_insurance` 必须读取 JSON + 公式，不走 LLM 推理 |
| **申报材料走字段映射** | `fill_tax_form` 是 key-value 填表，不是 LLM 生成 |
| **对话上下文** | 工具返回时附带 `user_context`，后续调用自动复用 |
| **白名单搜索** | `search_tax_website` 仅允许 7 个 gov.cn 域名 |

### 3.2 System Prompt 约束（5 条）

> 来源：`财务RAG-开发注意事项.md` §3.4（原文，MVP 基线版）。

```
你是"财税助手"，一个面向零财务基础大众的 AI 财税顾问。

规则：
1. 信息不足时，先反问 1-2 个问题收集信息，不要猜测
2. 税率计算走代码，不要自己推算
3. 每个计算结果附带分步推导和法规引用
4. 涉及金额的回复末尾必须附加 AI 免责声明
5. 使用简洁易懂的语言，避免专业术语，或在使用术语时附加解释
```

> 演进版（`财务RAG-后端开发路线图.md` Step 6 `agent/prompts.py`，7 条，Multi-Agent 前基线）：
>
> ```
> SYSTEM_PROMPT = """你是"财税助手"，一个面向零财务基础大众的 AI 财税顾问。
>
> 规则：
> 1. 信息不足时，先反问 1-2 个问题，每次只问 1-2 个，不要猜测
> 2. 税率计算和社保计算使用提供的工具，不要自己推算
> 3. 每个计算结果附带逐步推导过程
> 4. 涉及金额的回复末尾附上 AI 免责：「⚠️ 本结果由 AI 辅助计算，仅供参考。以税务机关最终核定为准。12366」
> 5. 当用户问题涉及多个关联法条时，使用 search_relations 查询关联文档
> 6. 使用简洁易懂的语言，专业术语附带解释
> 7. 回答附带法规引用（法规名 + 文号）"""
> ```
>
> Multi-Agent 化后 prompt 拆双版本（主 Agent + 双子 Agent），实现级细节以《财务RAG-Multi-Agent 集成设计文档》v1.5 为准（见 §6 Step 6 演进说明）。

### 3.3 工具返回结构化格式

> 来源：`财务RAG-后端开发路线图.md` Step 5 工具模板 + `财务RAG-开发注意事项.md` §3.1/§3.5 + `前端开发-完整代码生成包.md` §13/§14。

工具返回统一为结构化 JSON 字符串（`json.dumps(result, ensure_ascii=False)`），核心字段四元组 **result / source / disclaimer / answer**：

| 字段 | 说明 | 典型来源 |
|------|------|---------|
| `result` | 结构化计算结果 | `calculate_income_tax` / `query_social_insurance` / `fill_tax_form` |
| `source` | RAG 来源（title + url，可选 tier/relation） | `search_knowledge` |
| `disclaimer` | AI 免责声明 | 涉及金额的回复末尾 |
| `answer` | 自然语言总结（LLM 依据工具返回组织） | Agent 最终回答 |

**工具模板（Step 5 原文）**：

```python
from langchain_core.tools import tool

@tool
def search_knowledge(query: str) -> str:
    """搜索财税知识库。query: 用户的财税问题原文"""
    from rag.retriever import hybrid_search
    from rag.reranker import Reranker
    results = hybrid_search(query)
    reranker = Reranker()
    top = reranker.rerank(query, results)
    return json.dumps([{"content": r["content"], "source": r["source_url"]} for r in top], ensure_ascii=False)

@tool
def calculate_income_tax(annual_income: float, city: str,
                          housing_rent: float = 0, children_edu: float = 0,
                          elderly_support: float = 0) -> str:
    """计算综合所得个人所得税。
    annual_income: 年收入总额（元）
    city: 所在城市，如'郑州'
    housing_rent: 租房月扣除额（默认0）"""
    from services.tax_engine import calculate_comprehensive_tax
    special_deductions = (housing_rent + children_edu + elderly_support) * 12
    result = calculate_comprehensive_tax(annual_income, 9888, special_deductions)
    result["legal_basis"] = "《个人所得税法》附表一；国发〔2023〕13号"
    return json.dumps(result, ensure_ascii=False)

# ... 其余 4 个工具类似
```

**结果字段前后端对照**（`前端开发-完整代码生成包.md` §14）：

| 后端 `calculate_income_tax` 返回 | 前端 `ResultCard` 渲染 |
|----------------------------------|------------------------|
| `{taxable_income, tax_amount, rate, level, legal_basis}` | 标题 + 金额（`font-mono`）+ 折叠推导 + 法规链接 |

| 后端 `query_social_insurance` 返回 | 前端 `ResultCard` 渲染 |
|-----------------------------------|------------------------|
| `{breakdown: {养老:{employer,employee},...}, total_personal, total_employer}` | 逐险种分行 + 个人/单位合计 |

### 3.4 工具集文件结构（7 个 @tool）

> 来源：`财务RAG-后端开发路线图.md` Step 5。

```
backend/tools/
├── base.py             # 共享工具函数（SSE yield helper 等）
├── search_knowledge.py # 工具 1：RAG 检索
├── calculate_tax.py    # 工具 2：个税计算
├── query_social.py     # 工具 3：社保查询
├── fill_form.py        # 工具 4：申报材料生成
├── filing_guide.py     # 工具 5：申报流程指引
├── search_website.py   # 工具 6：白名单搜索
```

（工具 7：`search_relations`，知识图谱关联查询，见 §6 Step 4.5/Step 6。）

---

## 4. API 与 SSE 规范

### 4.1 后端 SSE 事件格式（前后端接口契约）

> 来源：`财务RAG-开发注意事项.md` §3.1（原文表格）。

| 事件 | 触发 | JSON 数据 | 前端行为 |
|------|------|----------|---------|
| `thinking` | Agent 开始 | `{"message":"正在为您计算……"}` | 显示加载提示 |
| `step` | 计算每步 | `{"content":"月薪8000×12=年收入96000元"}` | 追加到 AI 气泡 |
| `confirm` | 需确认 | `{"question":"租房扣除按1500元?", "options":["确认","自己填"]}` | 暂停流式，显示按钮 |
| `result` | 计算完成 | `{"type":"tax_result", "data":{taxable_income, tax_amount, ...}}` | 插入结果卡片 |
| `source` | RAG 来源 | `{"title":"...", "url":"..."}` | 折叠展示来源 |
| `disclaimer` | 免责 | `{"content":"本结果由AI辅助计算……"}` | 灰色小字 |
| `error` | 失败 | `{"message":"回答失败了，请重试"}` | 错误气泡 + 重试 |
| `done` | 结束 | `{}` | 恢复输入框 |

> **演进说明**（`前端开发-完整代码生成包.md` §13）：`confirm` 事件已移除，Agent 反问用户以自然语言通过 `step` 事件承载；新增 `context` 事件（历史摘要归档提示条，前端 `Message.contextNotice`）。工具错误（非致命）不再发 `error` 事件，改为 `thinking` 事件（Agent 会自行处理并继续回答）；**只有 Agent 完全无法继续时才发 `error`**。

**生产版事件对照（`前端开发-完整代码生成包.md` §13）**：

| 事件 | 后端何时发送 | 数据 payload | 前端行为 | 涉及组件 |
|------|------------|-------------|---------|---------|
| `thinking` | Agent 开始 / 工具调用 / **工具错误（非致命）** | `{"message":"..."}` 或 `{"tool":"name"}` 或 `{"tool_error":"..."}` | 显示"正在为您处理……"/工具执行中，输入框 `disabled`。工具错误不中断流式，Agent 会自行处理并继续回答 | `ChatView` |
| `step` | LLM 逐 token | `{"content":"..."}` | 追加流式文字到 AI 气泡 content（字符串累加，非数组） | `ChatMessage` |
| `result` | 计算/填表完成 | `{"type":"tax_result\|social_result\|form_result","data":{...}}` | 插入结果卡片 | `ResultCard` |
| `source` | RAG 来源 | `{"title":"...","url":"...","tier":"...","relation":"..."}` | 折叠显示来源链接 | `ChatMessage.sources` |
| `disclaimer` | AI 免责 | `{"text":"本结果由 AI 辅助……"}` | 灰色小字追加到回复末尾 | `ChatMessage` |
| `error` | **致命**处理失败（Agent 无法继续） | `{"content":"..."}` 或 `{"message":"..."}` | 红色边框气泡 + `[🔄重试]` 按钮。**若 content 已有文本则不覆盖**（保留 Agent 已生成的回答） | `ChatMessage.isError` |
| `done` | 回复完成 | `{}` | 恢复输入框可用，停止闪烁光标 | `ChatView` |

### 4.2 FastAPI SSE 实现模板

> 来源：`财务RAG-开发注意事项.md` §3.2（模板）+ `财务RAG-后端开发路线图.md` Step 7（生产实现）。

**基础模板（模拟数据流）**：

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json, asyncio

app = FastAPI()

async def generate_sse(user_message: str):
    # 1. thinking
    yield f"event: thinking\ndata: {json.dumps({'message': '正在为您计算……'})}\n\n"

    # 2. steps — 模拟计算过程
    steps = [
        "月薪 8000 × 12 = 年收入 96,000 元",
        "起征点：60,000 元，剩余 36,000 元",
        "社保扣除：养老 640 + 医疗 160 + 失业 24 = 月扣 824，年扣 9,888 元",
        "应纳税所得额 = 96,000 - 60,000 - 9,888 - 18,000 = 8,112 元",
    ]
    for step in steps:
        yield f"event: step\ndata: {json.dumps({'content': step})}\n\n"
        await asyncio.sleep(0.3)

    # 3. result
    result = {"taxable_income": 8112, "tax_amount": 243.36, "rate": "3%"}
    yield f"event: result\ndata: {json.dumps({'type': 'tax_result', 'data': result})}\n\n"

    # 4. source
    yield f"event: source\ndata: {json.dumps({'title': '个人所得税法 附表一', 'url': '...'})}\n\n"

    # 5. disclaimer
    yield f"event: disclaimer\ndata: {json.dumps({'content': '本结果由AI辅助计算，仅供参考...'})}\n\n"

    # 6. done
    yield f"event: done\ndata: {json.dumps({})}\n\n"

@app.get("/api/chat")
async def chat(message: str):
    return StreamingResponse(
        generate_sse(message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
```

**生产实现（Agent 真实流式，`backend/routers/chat.py`）**：

```python
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from agent.engine import agent
import json

router = APIRouter(prefix="/api", tags=["chat"])

@router.post("/chat")
async def chat(request: Request):
    body = await request.json()
    message = body["message"]
    context = body.get("context", {})
    thread_id = body.get("thread_id", "default")

    async def generate():
        config = {"configurable": {"thread_id": thread_id}}
        yield f"event: thinking\ndata: {json.dumps({'message': '正在为您处理……'})}\n\n"

        async for event in agent.astream_events(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield f"event: step\ndata: {json.dumps({'content': chunk.content})}\n\n"

        yield f"event: done\ndata: {json.dumps({})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### 4.3 API 路由设计

> 来源：`财务RAG-开发注意事项.md` §3.5（权威）+ `前端开发-完整代码生成包.md` §12（更新版，对齐 LangChain v1 Agent 重构）。

**权威路由表（开发注意事项）**：

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | GET | SSE 流式对话（query 参数：message） |
| `/api/chat` | POST | 同上（body：{message, context}） |
| `/api/calculate/tax` | POST | 税率计算（非流式，返回 JSON） |
| `/api/calculate/social` | POST | 社保计算 |
| `/api/form/generate` | POST | 申报表生成 |
| `/api/form/download/{form_type}` | GET | 下载空白原表 PDF |
| `/api/cities` | GET | 城市列表（MVP 返回 ["郑州"]） |

**更新版（前端调用清单，2026-07-30）**：

| 操作 | 方法 | 路由 | 请求 | 响应 |
|------|:--:|------|------|------|
| 发送消息（Agent） | POST | `/api/chat` | `{message, thread_id}` | SSE 流（7 种事件） |
| 旧版直连问答 | POST | `/chat` | `{query}` | SSE 流（旧格式） |
| 税率计算（快捷表单） | POST | `/api/tax/calculate` | `{annual_income, income_type, social_insurance?, housing_rent?, children_edu?, elderly_support?, bonus?}` | JSON |
| 社保计算（快捷表单） | POST | `/api/social/calculate` | `{salary, employment_type, housing_fund_ratio?, flexible_base_level?}` | JSON |

> 对话上下文由 Agent 内部管理，前端不需传 `context`。申报表生成已融入 Agent 通路（`fill_tax_form` @tool）。
> 资料库只读接口（`后端资料库接口-AI代码生成上下文包.md`）：`GET /api/library/documents`、`GET /api/library/documents/{doc_id}`、`GET /api/library/benchmark`。
> 历史接口：`GET /api/chat/history?thread_id=xx`（`财务RAG-项目补充与添加实施规划.md` §5.1）。

### 4.4 前端 SSE 消费

#### 方案 A：EventSource 简版（9 种事件，`财务RAG-开发注意事项.md` §2.3）

```javascript
// 前端消费 SSE 流（9 种事件，2026-08-04 更新：+context，-confirm）
const eventSource = new EventSource('/api/chat?message=...');

eventSource.addEventListener('thinking',   (e) => { /* 加载提示 / 工具执行动画 */ });
eventSource.addEventListener('step',       (e) => { /* 追加流式文字到 AI 气泡 */ });
eventSource.addEventListener('result',     (e) => { /* 插入结果卡片 */ });
eventSource.addEventListener('source',     (e) => { /* 折叠展示来源 */ });
eventSource.addEventListener('disclaimer', (e) => { /* 灰字免责 */ });
eventSource.addEventListener('context',    (e) => { /* 📦 历史摘要归档提示条（Message.contextNotice） */ });
eventSource.addEventListener('error',      (e) => { /* 红色错误气泡 + 重试（已有内容不覆盖） */ });
eventSource.addEventListener('done',       (e) => { /* 恢复输入框 */ });
```

#### 方案 B：fetch + ReadableStream 生产版（`前端开发-完整代码生成包.md` §6，`src/lib/sse.ts`）

> EventSource 不支持 POST 和自定义 headers，因此用本函数替代。**生产必须用此方案**。

```ts
import type { SSEEvent } from '@/lib/types';

/**
 * 使用 fetch + ReadableStream 消费 SSE 流
 * EventSource 不支持 POST 和自定义 headers，因此用本函数替代
 */
export async function* streamChat(
  message: string,
  threadId: string
): AsyncGenerator<SSEEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId }),
  });

  if (!response.ok) {
    yield { type: 'error', data: { message: `请求失败: ${response.status}` } };
    return;
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEvent) {
        try {
          const data = JSON.parse(line.slice(6));
          yield { type: currentEvent as SSEEvent['type'], data };
        } catch {
          // 跳过无法解析的行
        }
        currentEvent = null;
      }
    }
  }
}
```

#### 消费 Hook（`src/hooks/useChat.ts`，`前端开发-完整代码生成包.md` §7）

```ts
import { useState, useCallback } from 'react';
import type { Message } from '@/lib/types';
import { streamChat } from '@/lib/sse';

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = useCallback(async (content: string) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
    };
    const aiMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      isStreaming: true,
    };
    setMessages(prev => [...prev, userMsg, aiMsg]);
    setIsLoading(true);

    try {
      for await (const event of streamChat(content, threadId)) {
        setMessages(prev =>
          prev.map(m => {
            if (m.id !== aiMsg.id) return m;
            switch (event.type) {
              case 'step':
                return { ...m, steps: [...(m.steps || []), event.data.content as string] };
              case 'result':
                return { ...m, resultCard: event.data as Message['resultCard'] };
              case 'source':
                return { ...m, sources: [...(m.sources || []), event.data as Message['sources'][number]] };
              case 'thinking':
                return m;
              case 'done':
                return { ...m, isStreaming: false };
              case 'error':
                return { ...m, content: event.data.message as string, isError: true, isStreaming: false };
              default:
                return m;
            }
          })
        );
      }
    } catch {
      setMessages(prev =>
        prev.map(m =>
          m.id === aiMsg.id
            ? { ...m, content: '网络请求失败，请重试', isError: true, isStreaming: false }
            : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { messages, isLoading, sendMessage };
}
```

#### 前端状态处理（`财务RAG-开发注意事项.md` §2.4 + `前端开发-完整代码生成包.md` §16）

| 状态 | 实现 |
|------|------|
| 对话加载中 | 发送按钮变旋转圈，输入框 `disabled`，聊天流底部显示"正在为您计算……" |
| 表单计算中 | 按钮变灰 + "计算中……"，结果区显示骨架屏 |
| 空态 | 居中欢迎语 + 3 个示例问题按钮（点击填入并发送） |
| API 错误 | AI 气泡红色边框 + "回答失败了，请重试" + [🔄 重试] 按钮 |
| 网络断开 | 顶部黄色横幅 "网络连接异常，请检查网络" |
| RAG 无结果 | Agent 回复"未找到相关信息，已为您搜索官方网站……" + 自动调用 `search_tax_website` |

#### SSE 事件类型定义（`src/lib/types.ts`，`前端开发-完整代码生成包.md` §4）

```ts
// ====== SSE 事件 ======
export type SSEEventType =
  | 'thinking' | 'step' | 'result'
  | 'source' | 'disclaimer' | 'error' | 'done';

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}
```

---

## 5. AI 编码上下文方法论

### 5.1 前端完整代码生成包（18 章节结构）

> 来源：`前端开发-完整代码生成包.md`。

**用法**：将文档内容（或带 ★ 的章节）复制粘贴到 AI 对话开头，AI 将遵循全部规范生成前端代码。所有文件路径均为绝对路径，AI 可直接定位。

**项目根目录约定**：`F:\lest\frontend\`；图标根目录 `F:\lest\frontend\public\icons\`；源码根目录 `F:\lest\frontend\src\`。

**关联文档**：`财务RAG-AI提示词工程文档-v1.0.md`（早期版，分章节更详细）、`前端开发-AI编程Prompt.md`（精简版，无图标规范）、`财务RAG-UI设计方案.md`（视觉与交互参考）、`财务RAG-开发注意事项.md`（CSS 样式代码片段）、`财务RAG-前后端对照表.md`（接口契约）、`frontend/public/icons/README.md`（图标接入清单，最权威）。

**18 章节结构清单**：

| # | 章节 | 内容要点 |
|---|------|---------|
| ★0 | 项目一句话定位 | 财税助手——面向零财务基础大众的 AI 财税问答 Web 应用。MVP 三个视图：智能对话 / 税率计算 / 申报材料生成。仅桌面端（≥768px）。图标：20 枚 SVG（17 功能 SVG + 3 Favicon PNG）+ 1 枚 favicon.svg |
| ★1 | 技术栈（不可偏离） | React 18+ (TS) / Vite / shadcn/ui / Tailwind CSS v4 / SVG 图标 / React Context + useReducer（不引入 Redux/Zustand）/ SSE: fetch + ReadableStream（不用 EventSource）/ vite-plugin-svgr（必需）/ react-markdown + remark-gfm |
| ★2 | 设计令牌 | 完整 CSS Variables（见本文档 §2.1）+ `@layer base` / `.app-container { min-width: 768px }` / `.icon-spinning` 旋转动画；硬约束：颜色必须用 CSS 变量 |
| ★3 | 图标资源 | 17 SVG + 3 Favicon PNG + favicon.svg 绝对路径清单；SVG stroke 统一 `#014DB2`；4 种接入方式（A 组件导入最推荐 / B img / C 背景图 / D mask）；Favicon `<link>` 配置 |
| ★4 | TypeScript 类型 | `ActiveView`（六视图：chat/calculator/form/guide/documents/benchmark）、`LibraryDocMeta`、`BenchmarkItem`、`Message`（含 resultCard/steps/sources/isStreaming/isError）、`SSEEventType`、`SSEEvent` |
| ★5 | 组件文件树 | 全部绝对路径严格按结构创建（App/main/index.css + components/layout|chat|calculator|form|guide|library|shared|ui|icons + hooks/useChat + lib/types|sse|utils + context/AppContext） |
| ★6 | SSE 工具函数 | `src/lib/sse.ts` `streamChat`（fetch + ReadableStream，完整代码见本文档 §4.4） |
| ★7 | 核心 Hook | `src/hooks/useChat.ts` `useChat()`（完整代码见本文档 §4.4） |
| ★8 | 全局上下文 | `src/context/AppContext.tsx` `AppProvider`/`useApp`（activeView + userContext {city, deductions}） |
| ★9 | 根组件结构 | `src/App.tsx` `AppContent`（Sidebar + TopBar + main 按 activeView 渲染三视图）+ `main.tsx` 入口 |
| ★10 | 关键组件规范 | Sidebar / TopBar / ChatView / ChatMessage / WelcomeScreen / ResultCard / ChatInput / TaxCalculator / FilingForm / Skeleton / ErrorBanner 逐个规范（要点见 §5.2） |
| ★11 | 组件样式速查表 | Tailwind class 直接复制（见本文档 §2.2 表格） |
| ★12 | 后端 API 接口 | 前端调用清单（见本文档 §4.3 更新版表格） |
| ★13 | SSE 事件对照 | 前后端契约（见本文档 §4.1 生产版表格）；`confirm` 已移除，工具错误走 `thinking` 不中断 |
| ★14 | 数据类型对照 | Tax Result / Social Result / User Context 双向同步图（见本文档 §3.3/§5.2） |
| ★15 | 端口与代理 | 前端 :5173 / 后端 :8000 / Qdrant :6333；`/api/*` 由 Vite 代理 |
| ★16 | 状态处理规范 | loading/error/empty/网络断开/RAG 无结果五态（见本文档 §4.4 表格） |
| ★17 | 无障碍检查清单 | 见本文档 §8.3 |
| ★18 | 给 AI 编码助手的开头 Prompt | 完整原文见 §5.1.1 |
| 附录 A | 常见问题 | SVG vs PNG / 是否必须装 svgr / shadcn 组件范围 / 后端未启动前端能否跑 / Favicon 配置 / SVG 颜色跟随主题 |

#### 5.1.1 给 AI 编码助手的开头 Prompt（§18 全文）

> 来源：`前端开发-完整代码生成包.md` ★18，原文完整保留。

```
你是一个 React + TypeScript 前端开发专家。

项目背景：财税助手 Web 应用
项目根目录：F:\lest\frontend\
图标目录：F:\lest\frontend\public\icons\（17 个 SVG + 3 Favicon PNG + favicon.svg，共 21 个文件）
权威图标清单：F:\lest\frontend\public\icons\README.md

请严格按照以下规范生成代码：
- 框架：Vite + React 18 + TypeScript
- UI 库：shadcn/ui + Tailwind CSS v4
- SVG 处理：vite-plugin-svgr（必需），用 ?react 导入
- 图标：项目自有 17 枚 SVG + 3 PNG favicon + favicon.svg，不引入额外图标库（lucide-react 可选）
- 状态管理：React Context + useReducer
- 设计令牌：见 CSS Variables（§2），写入 F:\lest\frontend\src\index.css
- 组件规范：见"关键组件规范"章节（§10）
- SSE 通信：使用 fetch + ReadableStream（不用 EventSource）
- 无障碍：WCAG AA 标准（§17）

生成代码时：
1. 每个文件写入 §5 文件树中对应的绝对路径
2. import 使用 @/ 别名（vite config 已配 @ → src/）
3. 所有颜色用 CSS 变量，不硬编码 #014DB2 等
4. 仅桌面端（≥768px），不要写移动端样式
5. 图标全部用 SVG（方式 A：`import XxxSvg from '@icons/icon-xxx.svg?react'`），Favicon 4 个按 §3.4 配置。**路径必须用 `@icons/` 别名，不能用 `/icons/`**
6. 所有组件必须实现 loading / error / empty 三种状态
7. AI 回复内容必须用 `<MarkdownRenderer />` 渲染（react-markdown + remark-gfm），不能纯文本

项目图标文件清单（已存在于 F:\lest\frontend\public\icons\）：
SVG（17）：logo.svg, icon-chat.svg, icon-calculator.svg, icon-document.svg, icon-help.svg,
        icon-warning.svg, icon-location.svg, icon-loading.svg, icon-send.svg, icon-confirm.svg,
        icon-edit.svg, icon-retry.svg, icon-save.svg, icon-generate.svg, icon-download.svg,
        icon-blank-doc.svg, favicon.svg
PNG Favicon（3）：favicon-16.png, favicon-32.png, favicon-180.png

完整规范文档：[复制粘贴 §1-§17 全部内容]
```

#### 5.1.2 关键组件规范要点（§10 摘要 + 原文关键行）

> 来源：`前端开发-完整代码生成包.md` §10。

- **Sidebar**：默认 `width: 64px`，hover 扩至 `200px`（最新布局约束为 300px，见 §2.3）；`transition: width var(--transition-base); transition-delay: 50ms`（防误触）；选中态 `background: var(--color-primary-light); color: var(--color-primary)`。
- **TopBar**（2026-08-06 更新）：全宽 + `sticky top-0 z-10; height: 64px`；左侧 logo（`h-8 w-8`）+ "lest 财税助手"（`font-bold`）；中部 4 功能 tab `flex-1` 均分（`max-w-[200px]`），激活项 `bg-[var(--color-primary)] text-white`；右侧留白。
- **ChatView**：消息列表 `flex-1 overflow-y-auto`，底部输入框 `sticky bottom-0`；消息列表容器 `role="log" aria-live="polite"`。
- **ChatMessage** 内容渲染顺序（从上到下）：
  1. 有 `steps` → 步骤列表（`font-mono text-sm`）
  2. 有 `resultCard` → `<ResultCard />`
  3. 正文 `content` → **用户消息用纯文本，AI 消息用 `<MarkdownRenderer />`**（react-markdown + remark-gfm，支持 GFM 表格/删除线/任务列表）
  4. 有 `sources` → 折叠"📎 查看信息来源"区
  5. `disclaimer` → 灰色小字
  6. `isStreaming` → 末尾闪烁光标
  7. `isError` → 红色左边框 + `[🔄重试]` 按钮
  - 所有金额数字必须用 `font-mono`。
- **WelcomeScreen**：居中布局；大标题 logo（`w-16 h-16`）+ "欢迎使用财税助手"；副标题"我是你的 AI 财税顾问，可以帮你：计算个税和社保 · 解答财税问题 · 生成申报材料"；3 个示例问题按钮：`"工资 8000 在郑州交多少税？"` / `"租房能扣多少税？"` / `"帮我生成个税申报表"`。
- **ResultCard**：白底 + `border-l-4 border-l-[var(--color-primary)] rounded-[8px] p-4`；标题行图标 + 标题；数值区 `font-mono text-3xl`；可折叠"展开计算过程"（`<details>` 默认折叠）；底部法规引用 `text-sm text-[var(--color-text-tertiary)]`。
- **ChatInput**：固定底部，`bg-white border-t`，高度约 72px；textarea 自动撑高（max-height: 120px）；发送按钮 loading 态切 `icon-spinning`；`Enter` 发送，`Shift+Enter` 换行。
- **TaxCalculator**：收入类型 Select（综合所得/经营所得/劳务报酬）+ 税前月薪 + 城市（默认"郑州"）+ 分隔线"扣除项" + 7 项扣除（租房/子女教育/赡养老人/继续教育/大病医疗/房贷利息/婴幼儿照护）；每字段 HelpSvg + Tooltip；底部主按钮"开始计算"；结果下方链接"💡 想了解更多？切换到对话模式"。
- **FilingForm**：三区（基本信息/收入信息/扣除信息）；读取 `userContext` 自动预填；底部两按钮"保存草稿"（localStorage）/"生成申报表"（Agent `fill_tax_form` @tool）；结果区 Markdown 表格预览 + "下载填好的表"/"下载空白原表"。
- **Skeleton**：`<div className="animate-pulse bg-gray-200 rounded h-4 w-3/4" />`，接受 `className` 和 `lineCount` props。
- **ErrorBanner**：黄色横幅 + WarningSvg + 错误文案 + RetrySvg 重试按钮，接受 `message` 和 `onRetry` props。

#### 5.1.3 前端关键配置文件（§1/§3 核心）

**vite.config.ts**（`前端开发-完整代码生成包.md` §1.2）：

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import svgr from 'vite-plugin-svgr';
import path from 'path';

export default defineConfig({
  plugins: [
    react(),
    svgr({ svgrOptions: { svgo: true, titleProp: true } })
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@icons': path.resolve(__dirname, './public/icons'),
    },
  },
  server: {
    proxy: { '/api': 'http://localhost:8000' }
  }
});
```

> **注意**：SVG 导入路径必须用 `@icons/xxx.svg?react`（Vite 别名），**不能用** `/icons/xxx.svg?react`（构建时解析到文件系统根目录会报 ENOENT）。

**Favicon 配置**（`index.html` 的 `<head>`）：

```html
<link rel="icon" type="image/svg+xml" href="/icons/favicon.svg" />
<link rel="icon" type="image/png" sizes="32x32" href="/icons/favicon-32.png" />
<link rel="icon" type="image/png" sizes="16x16" href="/icons/favicon-16.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/icons/favicon-180.png" />
```

### 5.2 后端上下文包范式

> 来源：`后端资料库接口-AI代码生成上下文包.md`（原文完整保留核心结构）。

**用途**：交给负责后端开发的 AI 直接使用——项目已有的代码范式、接口规格、真实数据结构、验收标准全部在此，无需翻其他文档。

**包结构（9 节）**：

| 节 | 内容 |
|---|------|
| 0. 一句话任务 | 在 FastAPI 后端新增资料库只读接口：政策法规列表 / 法规正文（Markdown→HTML）/ 行业指标基准查询。数据文件已全部就绪，只做读取、过滤、转换，不改动任何现有代码逻辑 |
| 1. 项目背景（一句话） | 财税 RAG Web 应用「lest 财税助手」：DeepSeek 负责 Agent 调度，税率/社保计算走纯代码引擎，法规知识来自税总法规库清洗后的 Markdown |
| 2. 项目结构（后端相关） | `backend/` 目录树（main.py / config.py / routers/{tax,social,chat,form}.py / services/{tax_engine,social_engine}.py / data/） |
| 3. 代码范式（严格遵守） | 薄路由厚服务、Query + 中文 description、无 any、无吞错（见本文档 §2.4） |
| 4. 接口规格（3 个端点） | `GET /api/library/documents` / `GET /api/library/documents/{doc_id}` / `GET /api/library/benchmark`（完整 JSON 响应示例见 §5.2.1） |
| 5. 真实数据文件 | 法规文件 frontmatter 示例 + 行业基准 JSON 完整示例（见 §5.2.1） |
| 6. 要创建/修改的文件 | `backend/services/library_engine.py`（新建，lru_cache 缓存 53 md + 84KB JSON）/ `backend/routers/library.py`（新建）/ `backend/main.py`（include_router）/ `requirements.txt`（如需 markdown 库） |
| 7. 验收标准（8 条） | 见 §5.2.2 |
| 8. 常见坑（6 条） | 见 §5.2.3 |

#### 5.2.1 接口规格与真实数据结构要点

**`GET /api/library/documents` 响应示例**：

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

实现要点：`id` = 文件名去 `.md`；`title` = frontmatter 的 `doc_title` 或 `title` 字段；`category` 法规分类（法律/行政法规/部门规章/规范性文件）需从 `doc_title`/文件名推断或查 mapping（frontmatter 里 `category: tax_law` 是文档类型，不是法规分类）；`updated` = frontmatter `cleaned_at` 日期部分；`source` = `source_url` 域名。

**`GET /api/library/documents/{doc_id}` 响应示例**：

```json
{
  "id": "个人所得税法",
  "title": "中华人民共和国个人所得税法",
  "category": "法律",
  "html_content": "<h1>中华人民共和国个人所得税法</h1>\n<p>（1980年…）</p>..."
}
```

实现要点：读取 .md 正文（去掉 YAML frontmatter），**Markdown 转 HTML**（`markdown.markdown(text, extensions=['tables', 'fenced_code'])`）；找不到返回 404。

**`GET /api/library/benchmark` 响应示例**：

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

**法规文件 frontmatter 示例**（`rag-data/processed/national/tax_law/个人所得税法.md`）：

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

- frontmatter 用 `---` 包裹；`doc_title` 是简称，正文 H1 是全称；共 53 个文件；部分文件名带"中华人民共和国"前缀，部分不带。

**行业基准文件**（`rag-data/processed/national/rates/industry_benchmark.json`）：`tool_usage`（说明）+ `meta`（total_industries 97 / total_categories 20 / notes：low/high 为行业平均范围，null 表示不适用）+ `industries` 数组（扁平结构 10 指标）。

#### 5.2.2 验收标准（8 条，原文完整）

- [ ] `curl "localhost:8000/api/library/documents?category=法律"` → 返回法规列表，字段完整
- [ ] `curl "localhost:8000/api/library/documents?keyword=个人"` → 模糊搜索生效
- [ ] `curl "localhost:8000/api/library/documents/个人所得税法"` → `html_content` 含 `<h1>`/`<p>` 标签
- [ ] `curl "localhost:8000/api/library/documents/不存在"` → 404
- [ ] `curl "localhost:8000/api/library/benchmark?category=制造业"` → 过滤正确，`indicators` 含全 10 项，`ar_turnover` 字段名正确
- [ ] `curl "localhost:8000/api/library/benchmark?keyword=电子"` → 细分行业模糊匹配
- [ ] 接口不依赖 LLM / Qdrant（纯文件读取，秒回）
- [ ] 无 try/except 吞错、无 `any` 类型、中文注释（对齐现有代码风格）

#### 5.2.3 常见坑（6 条，原文完整）

1. **字段名**：`ar_turnover` 不是 `receivable_turnover`；别改任何指标 key
2. **小数 vs 百分数**：JSON 里 0.02 就是 2%，后端原样返回，不 ×100
3. **frontmatter**：用 `---` 分隔，解析时注意文件首行就是 `---`，无 BOM
4. **文件编码**：所有 .md 为 UTF-8，`open(..., encoding='utf-8')` 必须显式指定
5. **不要在 routers 里写大段逻辑**：薄路由 + 厚服务（services 层）
6. **缓存**：`@lru_cache(maxsize=1)` 缓存目录扫描与 JSON 读取结果，文件小不占内存

### 5.3 文档先行原则

> 来源：`财务RAG-项目补充与添加实施规划.md` §7 工程约束（原文第 1 条）+ 执行规则。

**文档先行**：每个补充项动手前，先在本规划文档对应小节勾选 ⬜ → 拆分任务（TaskCreate），再写代码。

**完整工程约束（§7，原文）**：
1. **文档先行**：每个补充项动手前，先在本规划文档对应小节勾选 ⬜ → 拆分任务（TaskCreate），再写代码
2. **禁止覆写**：评测集等数据资产只追加不覆盖（⑨ 明确标注）；任何改动前先读原文件
3. **评测驱动**：改动后必须跑对应评测（检索层 eval.py / 工具层 agent_eval.py / 生成层 context_eval.py），不达验收标准不算完成
4. **编码规范**：遵循《财务RAG-开发注意事项.md》（CSS 令牌 / API 路由 / 无障碍）与《财务RAG-后端代码审查报告.md》列出的问题清单
5. **新增代码落点**：上下文工程模块统一放 `backend/context/`；demo 类脚本放 `scripts/` 不入运行时
6. **演示环境约束**：任何新增依赖（MCP SDK / 后期 MongoDB 迁移）不得成为运行时硬依赖，保证"启动 Qdrant + 后端即能演示"

**执行规则**：逐项落地时在文档勾选状态（🔲 → ✅）并记录实测数据；发现新需求随时追加小节（仅追加，不删除既有内容）。

---

## 6. 后端开发路线实录（7 步）

> 来源：`财务RAG-后端开发路线图.md`。技术栈：FastAPI + LangChain `create_agent` + LangGraph + DeepSeek V4 Flash。

**开发总览（7 步，按依赖顺序）**：

```
Step 1: 项目骨架     →  FastAPI 跑起来 + 依赖装好
Step 2: 数据引擎     →  JSON 税率表 + 社保/个税计算函数（纯 Python，无 LLM）
Step 3: 向量化入库   →  MD 切分 → BGE-M3 编码 → Qdrant 写入
Step 4: RAG 检索链   →  BGE-M3 检索 + BGE-Reranker 重排
Step 4.2: 检索评测 ✅ →  40 条评测集 + eval.py，Recall@5 77.5%、MRR 0.83、40/40 全部命中
Step 4.5: 知识图谱 ✅ →  relations.json（20 条关联规则 + 双向遍历 + 两跳推理）
Step 4.8: Query 改写  →  口语→术语标准化（query_rewriter.py）🆕
Step 5: 工具集       →  7 个 @tool 函数（对接 Step2 数据 + Step4 检索 + Step4.5 关联）
Step 6: Agent 大脑    →  create_agent 调度 + MemorySaver + System Prompt
Step 7: SSE 流式上线  →  StreamingResponse + astream_events → 前端可联调
```

### Step 1：项目骨架

> **状态**：前端已有 `frontend/` 目录（React + shadcn/ui），后端待搭建。

**目标**：FastAPI 启动成功 + 所有依赖导入无报错。

**操作**：见 §1.1（venv 创建 + 依赖安装）。

**文件**：

```
backend/
├── main.py           # FastAPI 入口
├── config.py         # 环境变量 + 常量
├── requirements.txt
└── .env              # DEEPSEEK_API_KEY=sk-xxx
```

**`config.py`**：见 §1.4（完整代码）。

**`main.py` 最小骨架**：

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="财税助手 API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health(): return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**✅ 通过标准**：

```bash
curl http://localhost:8000/health → {"status": "ok"}
```

### Step 2：数据引擎（纯 Python，无 LLM）

> **状态**：✅ 结构化数据已全量就绪。含 `tax_rate_tables.json`（个税+车船税+印花税+专项附加扣除+计算流程）、`industry_benchmark.json`（97行业）、`social_insurance.json`（郑州社保+公积金）。计算公式可直接引用 JSON 中的 formula 字段，无需单独编写。

**目标**：个税计算和社保计算函数就绪，输入数据 → 输出结构化结果。

**文件**：

```
backend/
├── data/
│   ├── tax_rates.json        # 税率表（7 级综合 + 5 级经营 + 预扣率）
│   ├── deductions.json       # 7 项专项附加扣除标准
│   └── cities/
│       └── zhengzhou.json    # 郑州社保比例 + 基数 + 公积金
└── services/
    └── tax_engine.py         # 计算引擎（纯函数）
```

**数据文件格式示例**：

`data/tax_rates.json`：

```json
{
  "comprehensive": [
    {"level": 1, "from": 0, "to": 36000, "rate": 0.03, "quick_deduction": 0},
    {"level": 2, "from": 36000, "to": 144000, "rate": 0.10, "quick_deduction": 2520},
    ...
  ]
}
```

`data/cities/zhengzhou.json`：

```json
{
  "city": "郑州", "effective_from": "2025-07-01",
  "social_avg_wage": 6385, "base_min": 3831, "base_max": 19155,
  "pension": {"employer": 0.16, "employee": 0.08},
  "medical": {"employer": 0.07, "employee": 0.02},
  "unemployment": {"employer": 0.007, "employee": 0.003},
  ...
}
```

**`services/tax_engine.py`**：

```python
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

def load_json(filename: str) -> dict:
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)

def calculate_comprehensive_tax(
    annual_income: float,
    social_insurance: float = 0,
    special_deductions: float = 0,
) -> dict:
    """综合所得个税计算"""
    rates = load_json("tax_rates.json")["comprehensive"]
    taxable = annual_income - 60000 - social_insurance - special_deductions
    if taxable <= 0:
        return {"taxable_income": 0, "tax_amount": 0, "rate": "0%", "level": 0}

    for bracket in rates:
        if taxable <= bracket["to"] or bracket["to"] is None:
            tax = taxable * bracket["rate"] - bracket["quick_deduction"]
            return {
                "taxable_income": round(taxable, 2),
                "tax_amount": round(max(tax, 0), 2),
                "rate": f"{bracket['rate']*100:.0f}%",
                "level": bracket["level"],
            }
```

**✅ 通过标准**：

```python
from services.tax_engine import calculate_comprehensive_tax
result = calculate_comprehensive_tax(annual_income=120000, social_insurance=9888, special_deductions=18000)
assert result["taxable_income"] == 32112
assert result["tax_amount"] == 963.36
```

### Step 3：向量化入库

> **状态**：✅ 已完成。`scripts/chunk_docs.py` + `scripts/embed_and_upsert.py`，BGE-M3 编码 2419 chunks → Qdrant collection `finance_knowledge`（dense 1024d + sparse 双向量）。

**目标**：`rag-data/processed/` → BGE-M3 编码 → Qdrant collection 创建完毕。

**前置**：资料收集完成（`rag-data/processed/` 目录就绪）；Docker Desktop 已安装 + Qdrant 镜像已拉取 → `docker compose up -d`。

**文件**：

```
backend/
├── ingestion/
│   ├── index.py            # 主摄取脚本
│   └── chunker.py          # MD 文本切分
└── rag/
    └── embedder.py         # BGE-M3 单例（稠密 + 稀疏双编码）
```

**`rag/embedder.py`**：

```python
from FlagEmbedding import BGEM3FlagModel

class Embedder:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
        return cls._instance

    def encode(self, texts: list[str]) -> tuple:
        output = self.model.encode(texts, return_dense=True, return_sparse=True)
        return output["dense_vecs"], output["lexical_weights"]
```

**`ingestion/index.py`（伪代码示意）**：

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, SparseVectorParams
from rag.embedder import Embedder
from ingestion.chunker import chunk_markdown

client = QdrantClient(url="http://localhost:6333")
embedder = Embedder()

# 创建 collection（同时支持 dense 1024d + sparse）
client.create_collection(
    collection_name="finance_knowledge",
    vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
    sparse_vectors_config={"sparse": SparseVectorParams()},
)

# 遍历 processed/ 下的 MD 文件
for md_file in Path("rag-data/processed").rglob("*.md"):
    chunks = chunk_markdown(md_file)  # 800 tokens/chunk
    dense_vecs, sparse_vecs = embedder.encode(chunks)
    # 写入 Qdrant...
```

**✅ 通过标准**：

```
curl http://localhost:6333/collections/finance_knowledge → 返回 collection 信息，点数 > 0
```

### Step 4：RAG 检索链

> **状态**：✅ 已完成。`backend/rag/retriever.py`：三层分层召回（元数据过滤 → dense+sparse RRF融合 → Reranker精排 → relevance_weight加权）。单例模式，Agent 直接 `from rag import search_knowledge` 调用。

**目标**：`query → 元数据预过滤 → BGE-M3 → Qdrant 混合检索 Top-20 → BGE-Reranker 精排 Top-5` 可复用调用。

**文件**：

```
backend/rag/
├── embedder.py    # Step 3 已建
├── retriever.py   # 混合检索
└── reranker.py    # 精排
```

**`rag/retriever.py`**：

```python
from qdrant_client import QdrantClient
from qdrant_client.models import SearchRequest
from rag.embedder import Embedder
from config import QDRANT_URL, QDRANT_COLLECTION

client = QdrantClient(url=QDRANT_URL)
embedder = Embedder()

def hybrid_search(query: str, top_k: int = 20) -> list[dict]:
    dense, sparse = embedder.encode([query])
    results = client.search_batch(
        collection_name=QDRANT_COLLECTION,
        requests=[
            SearchRequest(vector={"name": "dense", "vector": dense[0].tolist()}, limit=top_k),
            SearchRequest(vector={"name": "sparse", "vector": sparse[0]}, limit=top_k),
        ],
    )
    # RRF 融合两个排序结果
    return rrf_fusion(results, top_k)
```

**`rag/reranker.py`**：

```python
from FlagEmbedding import FlagReranker

class Reranker:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.model = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True)
        return cls._instance

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        pairs = [[query, c["content"]] for c in candidates]
        scores = self.model.compute_score(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [c for c, _ in ranked[:top_k]]
```

**✅ 通过标准**：

```python
results = hybrid_search("租房扣除标准")
assert len(results) == 20
reranked = reranker.rerank("租房扣除标准", results)
assert len(reranked) == 5
assert reranked[0]["score"] > 0.5
```

### Step 4.2：检索评测（✅ 已完成）

**评测基线（优化前）**：

| 指标 | 数值 |
|---|---|
| Recall@5 | 67.5% |
| Recall@3 | 56.25% |
| MRR | 0.7379 |
| NDCG@5 | 0.6186 |
| 失败数 | 4 条（#13 #16 #33 #36） |

**优化过程**：

| 轮次 | 失败 query | 根因 | 修复 | 效果 |
|:--:|------|------|------|------|
| 1 | #36 电子发票 | 向量被吸到增值税发票 | Query 改写：电子发票→法律效力+电子商务法 | ✅ |
| 2 | #33 企税税率 | 企税/个税向量混淆 | DOC_KEYWORDS：企业所得税法+法人企业 | ✅ |
| 3 | #16 个税APP | 操作流程语言与政策问答语义鸿沟 | DOC_KEYWORDS + Query改写 + DOC_KEYWORDS存入内容让Reranker可见 | ✅ |
| 4 | #13 股权激励 | QA结构缺陷+法规条文Reranker低分 | QA ##修复 + weight=12 | ✅ |
| 5 | #25 社保不交 | "企业→企业所得税法"盲匹配 | Query改写：去税词+加社会保险法/劳动合同法 | ✅ |
| 6 | #11 年终奖 | 操作指南weight过高误伤 | weight精准化+DOC_KEYWORDS去通用词 | ✅ |
| 7 | #17 汇算截止 | 个税法weight=12过度泛化 | 回调weight→10 | ✅ |

**最终评测**：

| 指标 | 优化前 | 优化后 | 提升 |
|---|---|---|---|
| Recall@5 | 67.5% | **77.5%** | +10pp |
| Recall@3 | 56.25% | **66.25%** | +10pp |
| MRR | 0.7379 | **0.8329** | +0.095 |
| NDCG@5 | 0.6186 | **0.7115** | +0.093 |
| 失败数 | 4 条 | **0 条（40/40 全部命中）** | 🎉 |
| 分类通过率 | 8/12 | **12/12 (100%)** | 🎉 |

**可复用机制**：

| 机制 | 文件 | 部署注意 |
|---|---|---|
| Query 改写 | `backend/rag/query_rewriter.py` | 无需重嵌，重启后端即生效 |
| DOC_KEYWORDS | `scripts/embed_and_upsert.py` | 需重嵌生效 |
| WEIGHT_OVERRIDES | `scripts/embed_and_upsert.py` | 重嵌时自动应用 |
| QA 结构修复 | `scripts/fix_qa_headings.py` | 一次性脚本，需重新切分+重嵌 |
| 轻量知识图谱 | `rag-data/relations.json` + `backend/rag/retriever.py` | 20条规则，部署时放 rag-data/ 下，Retriever 启动加载 |

### Step 4.5：轻量知识图谱（✅ 已实现）

**目标**：用 `relations.json` 记录法律条文间的交叉引用关系，Agent 检索时自动发现关联文档，实现多跳知识增强——无需 Neo4j、无需图数据库。

**实现**：

文件结构：

```
rag-data/
└── relations.json                # 20 条精选关联规则

backend/rag/
└── retriever.py                  # _expand_relations() 方法
    └── Layer 4: 知识图谱扩展      # 集成在 retrieve() 末尾
```

索引格式（`rag-data/relations.json`）：

```json
[
  {
    "id": 1,
    "source": "个人所得税法",
    "relation": "implemented_by",
    "target": "中华人民共和国个人所得税法实施条例",
    "trigger_keywords": ["个税", "个人所得税", "起征点"],
    "description": "个税法第6-13条规定的计算规则，具体执行细节由实施条例明确"
  }
]
```

核心能力：
- **正向遍历**：source → target（个税法 → 实施条例）
- **逆向遍历**：target → source（实施条例反推个税法）
- **两跳推理**：A → B → C（汇算办法 → 个税法 → 操作指南 + 实施条例）
- **触发词过滤**：每条规则含 trigger_keywords 避免过度触发
- **关系语义**：每条边含 description 供前端展示

检索链路（Layer 4 集成在 `retriever.retrieve()` 末尾）：

```
Layer 1-3: 元数据过滤 → 混合检索 → Reranker 精排 → Top-5
Layer 4: 知识图谱扩展
  ├─ 正向: 主结果文档作为 source → 拉 target
  ├─ 逆向: 主结果文档作为 target → 反推 source
  └─ 两跳: 一阶 target 再作为 source → 拉二阶关联
```

实测示例：

```
输入: "个税汇算清缴怎么操作"
├─ #1-5: 汇算清缴管理办法 + 年度汇算公告
├─ #6-7: 个人所得税法 🔗 知识图谱（1跳·逆向）
├─ #8-9: 实施条例 🔗 知识图谱（2跳）
└─ #10-11: APP操作指南 🔗 知识图谱（2跳）
```

**✅ 通过标准**：

```python
retriever = Retriever()
results = retriever.retrieve("个税起征点")
# 应有 #6+ 的关联法规结果，含 "实施条例"
assert any("relation_source" in r for r in results)
```

### Step 4.8：Query 改写

**目标**：口语→术语标准化（`query_rewriter.py`）。

**实现要点**：50+ 条口语→术语映射表 + Key 长度降序匹配，弥合用户口语与法律文本的语义鸿沟。无需重嵌，重启后端即生效。

### Step 5：工具集（7 个 @tool）

**目标**：7 个 LangChain Tool 就绪，可被 Agent 调用，返回结构化结果。

**文件**：见 §3.4（`backend/tools/` 结构）。

**工具模板**：见 §3.3（`search_knowledge` / `calculate_income_tax` 完整模板代码）。

**✅ 通过标准**：

```python
tool_result = search_knowledge.invoke({"query": "租房扣除标准"})
assert "1500" in tool_result or "1100" in tool_result
```

### Step 6：Agent 大脑

**目标**：LLM + 6 个工具 + 对话记忆 = 能自主选择工具、能引导式追问、能流式输出。

**文件**：

```
backend/agent/
├── engine.py      # create_agent 调度
└── prompts.py     # System Prompt
```

**`agent/prompts.py`**：见 §3.2（演进版 7 条完整代码）。

**`agent/engine.py`**：

```python
from langchain_deepseek import ChatDeepSeek
from langchain import create_agent
from langgraph.checkpoint.memory import MemorySaver

from agent.prompts import SYSTEM_PROMPT
from tools import ALL_TOOLS

llm = ChatDeepSeek(model="deepseek-v4-flash", temperature=0)
checkpointer = MemorySaver()

agent = create_agent(
    model=llm,
    tools=ALL_TOOLS,          # [search_knowledge, calculate_income_tax, ..., search_relations]
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
)
```

**✅ 通过标准**：

```python
config = {"configurable": {"thread_id": "test-1"}}
result = agent.invoke(
    {"messages": [{"role": "user", "content": "郑州工资8000租房，一个月交多少税？"}]},
    config=config
)
# Agent 应该自动调用 calculate_income_tax 工具
assert "税" in result["messages"][-1].content
```

> **2026-08-05 演进：Multi-Agent 化（P1 ✅ 已完成）**——Step 6 的单 Agent 基础上，计税/社保已升级为双子 Agent（Tool-as-Subagent，`AGENT_MODE` 模式开关回退，prompt 双版本 + 失败降级 + 绕过检测）。三层评测全绿：主 Agent 路由 26/26、主层对拍 8/8、子层 10/10。实现级设计见 **《财务RAG-Multi-Agent 集成设计文档》（v1.5）**；实施记录见《财务RAG-项目补充与添加实施规划》§4.1。

### Step 7：SSE 流式上线

> **状态**：✅ 已完成。`backend/services/generator.py` + `backend/routers/chat.py`。POST /chat → SSE 流式返回，POST /chat/with-search → 先返回检索来源再流式回答。验证通过。

**目标**：前端可以通过 `/api/chat` 拿到 SSE 流式响应，8 种事件类型完整。

**`routers/chat.py`**：见 §4.2（生产实现完整代码）。

**✅ 通过标准**：

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"房租能抵多少税？"}' 
# 应该看到 event: thinking → event: step → event: done 等流式输出
```

### 6.1 关键陷阱表

> 来源：`财务RAG-后端开发路线图.md` 开发注意事项。

#### 🔴 Critical — API 弃用警告

| 不要用 | 原因 | 用这个 |
|--------|------|--------|
| `create_react_agent` | 已弃用，v1.0 后移除 | `langchain.create_agent()` |
| `model="deepseek-chat"` | **2026-07-24 起弃用** | `model="deepseek-v4-flash"` |
| `model="deepseek-reasoner"` | **同日弃用**，且不支持 Tool Calling | `model="deepseek-v4-flash"` |
| `langgraph.savers.memory.MemorySaver` | v0.2 起路径已变 | `langgraph.checkpoint.memory.MemorySaver` |
| `state["messages"] += [...]` | v0.2+ 强制 reducer | `Annotated[list, operator.add]` |

#### 🟡 环境与资源

| 事项 | 说明 |
|------|------|
| **Qdrant Docker 启动顺序** | 必须在 Step 3 之前 `docker-compose up -d`。演示时提前 5 分钟启动，关掉微信/Chrome 等重应用释放内存 |
| **BGE-M3 首次加载** | 首次 `BGEM3FlagModel("BAAI/bge-m3")` 会从 HuggingFace 下载约 2.2GB 模型文件到 `~/.cache/huggingface/`，需联网。之后秒加载 |
| **BGE-Reranker 同样** | 首次下载约 1.5GB。两个模型总计约 3.7GB |
| **GPU 显存** | BGE-M3 fp16 占用约 2GB，Reranker 约 1.5GB，DeepSeek 走 API 不占显存。RTX 4060 8GB 绰绰有余 |
| **Python 版本** | ≥ 3.10（LangChain 要求）。你已有的 3.13.12 没问题 |
| **.env 文件** | 放在 `backend/.env`，包含 `DEEPSEEK_API_KEY=sk-xxx`。**不要提交到 Git** |

#### 🟡 编码陷阱

| 陷阱 | 现象 | 正确做法 |
|------|------|---------|
| `@tool` 函数无类型提示 | Agent 调用时参数乱传 | 每个参数必须有类型注解 + 描述（见 Step 5 模板） |
| `@tool` 函数返回非 str | LangChain 要求工具返回字符串 | 复杂结果用 `json.dumps(result, ensure_ascii=False)` 包一层 |
| `temperature` 设为 > 0 | Agent 偶尔选错工具 | Tool Calling 场景 `temperature=0`，保证确定性 |
| Qdrant collection 未创建 | `search_batch` 报 404 | Step 3 必须先执行 |
| SSE 事件格式不对 | 前端收不到事件 | 格式必须是 `event: xxx\ndata: {...}\n\n`，注意两个换行 |
| `astream_events` 无 `version="v2"` | 事件格式不兼容 | 加 `version="v2"` 参数 |
| 中文 JSON 被转义 | 前端显示 `\uXXXX` | `json.dumps(..., ensure_ascii=False)` |
| Reranker 重复加载 | 每次查询重新初始化模型（巨慢） | 用单例模式（Step 4 的 `__new__` 写法） |
| Embedder 重复加载 | 同上 | 同上 |

### 6.2 演示武器库（逐 Step 话术）

| Step | 演示能说的点 |
|------|------------|
| 1 | "FastAPI + Async 架构，非阻塞 I/O，SSE 长连接" |
| 2 | "税率计算不走 LLM，用 Pydantic 模型 + JSON 驱动，零幻觉" |
| 3 | "BGE-M3 双向量（稠密 1024d + 稀疏 BM25），Qdrant 原生混合检索" |
| 4 | "三层分层召回：元数据过滤 → Qdrant RRF 融合粗排 20 → BGE-Reranker Cross-encoder 精排 5" |
| 4.5 | "轻量知识图谱：20条关联规则 JSON + 双向遍历 + 两跳推理，替代 Neo4j 实现法条多跳交叉引用，零数据库依赖" |
| 4.2 | "40 条评测数据集 + 自动化评测脚本，Recall@5 从 67.5% 优化至 77.5%（+10pp），MRR 0.74→0.83，40/40 全部命中" |
| 4.8 | "Query 改写层：50+ 条口语→术语映射表 + Key 长度降序匹配，弥合用户口语与法律文本的语义鸿沟" |
| 5 | "LangChain @tool 装饰器 + Pydantic 自动生成 JSON Schema，LLM 理解入参" |
| 6 | "create_agent + MemorySaver 实现有状态多轮对话，支持工具自动路由" |
| 7 | "astream_events 实时事件流 → SSE → 前端逐字渲染，端到端延迟 < 500ms" |

---

## 7. 实施规划方法论

> 来源：`财务RAG-项目补充与添加实施规划.md`。定位：接下来所有对 lest 的**补充/添加**的实施蓝图，承接《财务RAG-展示技术补强-概念梳理》§9 的三模块设计，扩展至 Agent 工程化、数据与存储、打磨收尾三个方向。性质：规划文档，每项含「目标 / 为什么现在补 / 改动文件 / 实施步骤 / 验收标准 / 工作量」，可直接转成开发任务逐项落地。

### 7.1 补充项总览（10 项规划结构）

**规划结构范式**：每个补充项按「目标 / 为什么现在补 / 改动文件 / 实施步骤 / 验收标准 / 工作量」六要素组织；总览用统一表格；每项含状态勾选（🔲 → ✅）与实测数据记录。

**总览表（10 项，原文完整）**：

| # | 补充项 | 方向 | 优先级 | 工作量 | 状态 |
|---|---|---|---|---|---|
| 1 | **历史摘要器**（含保障压缩） | 上下文工程 | 🥇 P0 | 1.5-2 天 | ✅ 已完成（集成测试通过） |
| 2 | **TokenBudget** 预算参数 | 上下文工程 | 🥇 P0 | 0.5 天 | ✅ 已简化（参数固化于摘要器） |
| 3 | **ContextEvaluator** 历史摘要评测 | 上下文工程 | 🥇 P0 | 1 天 | ✅ 已完成（judge 100% / 事件 100% / probe 92%） |
| 4 | **Multi-Agent 化**（工具升级子 Agent） | Agent 工程化 | 🥈 P1 | 1-2 天 | ✅ 已完成（双层评测全绿） |
| 5 | **MCP Server 封装**（个税计算工具） | Agent 工程化 | 🥈 P1 | 1-2 天 | ✅ 已完成（tax-calc 3 工具，WorkBuddy 宿主实测通过） |
| 6 | **对话历史摘要裁剪** | Agent 工程化 | 🥈 P1 | 0.5 天 | ✅ 已完成（已被 history_summarizer 覆盖） |
| 7 | **用户上下文持久化**（grill 定案：SQLite + 自建消息表 + 历史回显） | 数据/存储 | 🥉 P2 | 1.5-2 天 | ✅ 已实施（2026-08-06，冒烟全绿） |
| 8 | **LlamaIndex 对比 demo** | 数据/存储 | 🥉 P2 | 半天 | 🔲 可选 |
| 9 | **评测集扩展 + 评测自动化** | 打磨收尾 | 🥉 P2 | 1 天 | ✅ 已完成（60 条，Recall@5 = 85%，run_all.py 落地） |
| 10 | **设计稿落地**（顶栏 tab / 侧边栏重构 / 折叠态图标 / 资料库接口） | 前端+数据 | 🥈 P1 | 前端 2.5-4 天 + 后端 0.5-1 天 | 🔲 蓝图已定稿（《设计稿落地实施规划》），待实施 |

**依赖关系**：**P0-0 基线采集**✅ 已完成（keep=20 / trigger=40K 已回填）；① 的 guard 部分 ✅ 已实现（`backend/context/guard.py`，替换 `content[:800]`），摘要器部分待做；② 并入 ① 实现（参数直接用基线定值）；③ 验证 ① 效果（闭环）；⑥ 依赖 ② 的阈值设计；⑨ 与 ③ 共用长对话场景集。

> 决策逻辑：**P0 三件套是"低成本、高叙事价值"的核心补强**——§9 已给出接口级设计，且直击现有代码两处硬伤（见 §7.2）；P1 是展示差异化；P2 按时间余量取舍。

### 7.2 现状盘点：三处"硬伤"驱动本次补充

| 现状代码 | 问题 | 本次补充项 |
|---|---|---|
| `tools/search_knowledge.py:45` — `content[:800]` | **硬截断**：无差别砍尾部，可能丢掉高价值后半段（法条条款后半段常含关键数字），且 5 条 × 800 字仍会撑爆窗口 | ① ContextCompressor（提取式替换硬截断） |
| `agent/engine.py` — `InMemorySaver()` 只增不减 | 长对话历史无限膨胀，无任何额度管理 | ② TokenBudget + ⑥ 历史摘要裁剪 |
| `eval/` 双层评测（eval.py 检索层 + agent_eval.py 工具层） | 只验证"检索对不对/工具选得对不对"，**未验证送入 LLM 后产出是否忠实** | ③ ContextEvaluator（生成层） |

> **grill 审查修订（2026-08-04）**：压缩主战场从"单轮 chunk"改为"多轮历史摘要"——实测 2937 个 chunk 中位数仅 181 字，单轮压缩无意义。P0 三项按 v2 架构重排（详细设计见《Context Engineering 集成设计文档》v2.0）。

### 7.3 §n 设计细节范式（P0 三件套示例）

**每项含：目标 / 改动文件 / 实施步骤 / 验收标准。**

#### ① 历史摘要器 + 工具返回瘦身（核心）

- **目标**：继承官方 `SummarizationMiddleware`（langchain 1.3.14 已查证 API），扩展**两级压缩**（提取式过滤低价值轮 → LLM 摘要）、**画像字段自动校验**、**SSE context 用户提示**。
- **改动文件**：✅ `backend/context/guard.py`（提取式瘦身，软上限 400 字，自检通过）、`backend/tools/search_knowledge.py`（替换 `content[:800]`）；待做 `backend/context/history_summarizer.py`、`backend/agent/engine.py`（middleware 链）、`backend/routers/chat.py`（context 事件）、前端 `types.ts` / `useChat.ts` / `ChatMessage.tsx`（提示条）。
- **实施步骤**：① ✅ 基线采集（**keep=20 / trigger=40K**）→ ② 继承 SummarizationMiddleware：`model=DeepSeek`、`trigger=("tokens", 40_000)`、`keep=("messages", 20)`、自定义 `summary_prompt`（画像字段必保）→ ③ 扩展提取式预过滤 + 摘要标志 → ④ ✅ guard.py 已实现 → ⑤ SSE context 事件（后端新增事件 + 前端提示条）。
- **验收标准**：① 画像字段完整率 100%（自动校验）；② 摘要忠实度 ≥90%（judge 抽查）；③ 历史 token 降幅 ≥70%；④ 事件触发率 100%；⑤ agent_eval 20 条回归 ≥90%。

#### ② TokenBudget — 预算参数决策源

- **目标**：五区预算分配（system 6K / 检索 20K / 历史 12K / query 18K / 输出预留 4K），动态让渡 + 历史裁剪。
- **改动文件**：新增 `backend/context/budget.py`（dataclass `BudgetAllocation`）；修改 `backend/tools/search_knowledge.py`（`budget_chars` 由 `TokenBudget.allocate(has_retrieval=True).retrieval_chars` 换算得出）。
- **实施步骤**：① token 估算（中文 1 字 ≈ 1.5~2 token，可选 tiktoken cl100k_base 校准）→ ② `allocate()` 五区分配 + 无检索轮让渡 → ③ `trim_history()`（先裁最旧轮次）→ ④ 单测极端输入。
- **验收标准**：① 任意输入下 `sum(alloc) ≤ 窗口 - 预留`；② 检索预算换算成字符数后与压缩率联动正确。

#### ③ ContextEvaluator — 历史摘要质量评测

- **目标**：补齐三层评测的生成层——faithfulness / 引用正确率 / 上下文利用率 / token 效率，用 LLM-as-judge 验证 ①② 效果。
- **改动文件**：新增 `backend/eval/context_eval.py`（judge 复用 DeepSeek，temperature=0）+ `backend/eval/eval_set_v2.json`（20 条：10 知识问答 + 10 计算类，含 `expected_facts` + `golden_answer`）。
- **实施步骤**：① 设计 eval_set_v2 结构 → ② 评测流程：rewrite → retrieve → **Compressor 开/关两组** → 生成 → judge 判定 → ③ 四项指标计算与对比报告 → ④ 跑通 20 条输出基线报告。
- **验收标准**：① faithfulness ≥ 90%；② 引用正确率 ≥ 85%；③ 压缩后 token 用量下降 ≥ 40% 且 faithfulness 下降 ≤ 2pp；④ 报告含压缩开/关对比。

### 7.4 实施记录范式

> **范式**：每项完成后在规划文档对应小节追加「✅ 实施记录」区块，含：改动文件清单（新增/修改逐项列出）、关键实现决策（编号列出，含原因）、实测结果（py_compile / 回归 / 前端 tsc 等）、待验收事项（用户自跑项）。

**§5.1 用户上下文持久化实施记录（2026-08-06，原文完整）**：

> ✅ **实施记录（2026-08-06）**：全部代码落地，冒烟全绿。
> - 改动文件：新增 `backend/storage/{__init__,sqlite_store}.py`（MemoryStore + SQLiteStore，三表 threads/messages/user_contexts，单连接+写锁）；修改 `backend/config.py`（SQLITE_DB_PATH，默认 `backend/data/chat.db`）、`backend/tools/user_context.py`（dict → MemoryStore，工具签名与返回格式不变）、`backend/routers/chat.py`（历史注入只取正文 + 流结束写回完整 Message JSON + `GET /api/chat/history`）、`backend/agent/engine.py`（`get_llm()` 配置源 TODO 位 + InMemorySaver 角色注释）、前端 `sse.ts`（getHistory）/ `useChat.ts`（localStorage 固定 thread_id + 挂载回显 + isHydrating）/ `App.tsx`（加载占位）。
> - 关键实现决策：① 内部 thread_id = `{业务tid}#{uuid8}` 每请求独立 → InMemorySaver 永不跨轮累积；② 注入历史仅 role+content，附件不喂 LLM；③ 摘要中间件调用内压缩、结果不回写（写回只写本轮新增 → 无消息双份膨胀）；④ 异常/错误回复不写回（用户重试自然落库）。
> - 实测：py_compile 全过；SQLiteStore 读写往返/隔离/幂等通过；user_context 工具行为回归一致（含非法 key 分支）；前端 `tsc --noEmit` 零错误。
> - 待验收（用户自跑）：`agent_eval.py` 回归 ≥90% + 手动端到端（重启恢复/刷新回显/串号隔离/长对话摘要触发）。

**Multi-Agent 化评测记录（§4.1，2026-08-05）**：

| 评测 | 分数 | 验收指标 |
|---|---|---|
| `agent_eval` 主 Agent 路由 | **26/26 (100%)** | ≥90% ✅ |
| — search_knowledge | 6/6 | 100% |
| — tax_subagent | 8/8 | 100% |
| — social_subagent | 5/5 | 100% |
| — fill_tax_form | 5/5 | 100% |
| — filing_guide | 4/4 | 100% |
| 一致性硬校验 | 0 "not registered" | ✅ |
| `multi_agent_eval` 主层对拍 | **8/8 (100%)** | 数值完全一致 |
| `multi_agent_eval` 子层工具选择 | **6/6 (100%)** | ≥90% ✅ |
| `multi_agent_eval` 子层拒答 | **2/2 (100%)** | ✅ |
| `multi_agent_eval` 子层绕过检测 | **2/2 (100%)** | ✅ |

**踩坑记录（Multi-Agent）**：
1. langgraph-prebuilt 1.1.0 ToolNode sync 路径只走 `_execute_tool_sync`，不检测 async 工具 → 4 个 `async def @tool` 全部改为 sync `def` + 内部 `asyncio.run()`
2. 评测用例 `direct_args` 参数名必须与工具 `args_schema` 字段严格对齐
3. `fill_tax_form` 需在 SYSTEM_PROMPT_MULTI 中加示例 + B 表两步流程结构化，否则 LLM 倾向先查画像再放弃

### 7.5 决策记录范式

> **范式**：重大方案变更先经 grill-me 压力审查，记录「原方案 → 推翻原因（编号列出关键发现）→ 新定案 + 理由」。示例见 §7.5.1。

#### 7.5.1 用户上下文持久化决策记录（grill 定案 2026-08-05，原文完整）

> ⚠️ **grill 审查修订（2026-08-05）**：原方案「in-memory dict → MongoDB」被推翻，重新定案为 **SQLite + 自建消息表 + 历史回显**。三个关键发现驱动修订：
> 1. 前端 `useChat.ts:8` thread_id 每次 `crypto.randomUUID()` 刷新即变 → 后端无论存什么都取不回，**必须先前端 localStorage 固定 thread_id**，持久化才有意义（这也是"重启不丢"验收成立的前提）；
> 2. 对话历史天然由 langgraph `InMemorySaver`（engine.py:112）管理，但**不换 Saver，改自建消息表**——消息可读可控、可迁移、可配合评测，且不依赖 langgraph 二进制序列化格式；
> 3. 存储介质选 **SQLite**（标准库零依赖，演示零风险），MongoDB 降级为"后期迁移"目标——靠 `MemoryStore` 抽象层 + 一次性迁移脚本实现，结构固定可平滑迁移。不引入 Redis（单进程单用户无缓存需求）。

**定案核心设计**：
- 前端 thread_id 存 localStorage（**单会话模型**：一浏览器 = 一会话，MVP 语义；登录后扩展为 user_id + 多会话）
- 对话历史自建消息表，**恢复注入复用 SummarizationMiddleware 调用内压缩**（trigger=40K / keep=20，不重写摘要逻辑）
- `MemoryStore` 接口 + `SQLiteStore` 实现 → 后期换 MongoDB 仅换实现类，业务零改动
- 画像/消息表**预留 user_id 列**（当前 user_id = thread_id 占位，登录后零返工）
- `get_llm()` 预留"配置源"接口位（TODO），支持后期切换 DeepSeek key（管理员切换=改配置源；BYOK=登录体系后加密入库）

**验收标准**：① 重启后端后同一 thread_id 画像+历史完整恢复；② 刷新页面历史回显 + Agent 接得上话；③ 新浏览器 = 新 thread_id，不串号；④ 工具接口不变；⑤ `agent_eval` 回归 ≥90% 不降；⑥ 20+ 轮长对话摘要正常触发、无消息双份膨胀。

### 7.6 实施顺序与排期

```
P0-0 基线采集 ──→ P0-1 历史摘要器 ──→ P0-2 TokenBudget(参数校准并入)
（0.5-1天）        （1-1.5天）         （0.5天）
                         │
                         └──→ P0-3 ContextEvaluator ──→ P1-4 Multi-Agent
                                （1天）                   （1-2天）
                                                          │
                                                          └──→ P1-5 MCP ──→ P1-6 事件完善 ──→ P2 按余量取舍
                                                                 （1-2天）     （0.5天）
```

| 阶段 | 内容 | 累计工作量 | 交付物 |
|---|---|---|---|
| 第 1 周 | P0-0 基线采集 → P0 三件套（摘要器/预算/评测）+ ⑨ 评测扩展 | ~4-5 天 | context/ 模块 + context 事件 + 四指标评测报告 |
| 第 2 周 | P1 三件套 | ~3-4 天 | 子 Agent demo + MCP Server + 事件完善 |
| 余量 | P2 按演示时间取舍 | ~2 天 | 用户上下文持久化（§7.5.1）/ LlamaIndex / 自动化 |

> 建议原则：**每个 P0 项完成即跑一遍评测留下数据**（压缩率、faithfulness、token 用量），这些数字就是演示和演示的实证素材。

---

## 8. 前后端协作检查清单

### 8.1 前后端协作检查清单（开发注意事项 §四）

> 来源：`财务RAG-开发注意事项.md` 四、前后端协作检查清单（原文完整）。

- [ ] 前端 CSS 变量与设计令牌一致
- [ ] SSE 事件类型前后端命名一致
- [ ] `confirm` 事件的 `options` 数组与前端的交互按钮一一对应
- [ ] `result` 事件的 `data` 字段结构前端能正确渲染为结果卡片
- [ ] 前端 `EventSource` 正确处理重连（后端断线后自动重连）
- [ ] 对话上下文（城市/工资/扣除项）在切回对话模式后自动恢复
- [ ] 表单数据与对话上下文双向同步（表单填的 → 对话能用；对话说的 → 表单预填）

### 8.2 开发联调检查清单（路线图 🟢 开发联调）

> 来源：`财务RAG-后端开发路线图.md` 开发注意事项（🟢 开发联调）。

| 事项 | 说明 |
|------|------|
| **前端联调端口** | 后端 `localhost:8000`，前端 `localhost:5173`（Vite 默认）。前端 `vite.config.ts` 中配置 proxy 到 8000 避免 CORS |
| **测试对话** | 每个 Step 的"通过标准"即为单元测试，建议写完一个 Step 跑一次 |
| **Qdrant Dashboard** | `http://localhost:6333/dashboard` — 可视化查看向量分布，演示时打开这个页面展示 |
| **DeepSeek 余额** | 提前充值 10 元足够整个开源。每 100 次对话约花 ¥0.02-0.05 |
| **流式调试** | 前端未就绪时用 `curl -N` 直接看原始 SSE 事件（Step 7 的通过标准） |

### 8.3 无障碍检查清单

> 来源：`财务RAG-开发注意事项.md` §2.5 + `前端开发-完整代码生成包.md` §17（两个版本合并去重，保留完整条目）。

- [ ] 所有可点击元素 ≥ 44×44px
- [ ] 全部交互元素支持 Tab + Enter
- [ ] `:focus-visible` 时 2px 深藏蓝 outline（`outline: 2px solid var(--color-primary); outline-offset: 2px`）
- [ ] 结果卡片 `role="region"` + `aria-label`
- [ ] 输入框关联 `<label>` 或 `aria-label`
- [ ] 错误消息 `role="alert"`
- [ ] 动效尊重 `prefers-reduced-motion`（`@media (prefers-reduced-motion: no-preference)` 包裹）
- [ ] 消息列表：`role="log" aria-live="polite"`
- [ ] 计算步骤：`<ol>` 语义化

### 8.4 数据与状态类型对照

**User Context 双向同步图**（`前端开发-完整代码生成包.md` §14）：

```
[对话模式]  ←──────────────────→  [税率计算器]  ←──────────────────→  [申报表单]
     │                                  │                                  │
     │  Agent 提取并存入 context         │  表单填入存入 context              │  复用 context 预填
     └────────── AppContext.userContext ─────────────────────────────────────┘
                       {city, salary, incomeType, deductions}
```

**前端 Message 类型（`src/lib/types.ts`）**：

```ts
export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  resultCard?: {
    type: 'tax_result' | 'social_result' | 'form_result';
    data: TaxResult | SocialResult | FormResult;
  } | null;
  steps?: string[];
  sources?: Source[];
  isStreaming?: boolean;
  isError?: boolean;
}
```

---

## 附录：文档来源与使用指引

| 主题 | 权威来源 | 在本文档的位置 |
|------|---------|---------------|
| CSS 令牌 / 组件样式 / 布局 / SSE 事件契约 | `财务RAG-开发注意事项.md` | §2.1-§2.3、§4 |
| 工具调度 5 规则 / System Prompt | `财务RAG-开发注意事项.md` | §3.1-§3.2 |
| 7 步开发路线 / 陷阱表 / 演示话术 | `财务RAG-后端开发路线图.md` | §6 |
| 前端代码生成包用法 / 18 章节 / 开头 Prompt | `前端开发-完整代码生成包.md` | §5.1 |
| 后端上下文包范式 / 验收 8 条 / 坑 6 条 | `后端资料库接口-AI代码生成上下文包.md` | §5.2 |
| 实施规划方法论 / 硬伤 / 决策记录 | `财务RAG-项目补充与添加实施规划.md` | §7 |

**使用顺序建议**：编码前读 §1-§2 → 写 Agent 前读 §3 → 联调前读 §4 → 用 AI 生成代码时读 §5 → 回顾进度与演示时读 §6 → 新增功能时读 §7 → 交付前跑 §8 全部清单。
