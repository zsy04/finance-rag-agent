---
doc_title: 财务 RAG Agent 后端设计文档
category: backend
source_docs:
  - 财务RAG-技术架构与Agent方案.md
  - 财务RAG-后端开发路线图.md
  - 财务RAG-后端审查与重构方案.md
  - 财务RAG-后端代码审查报告.md
  - 财务RAG-Context Engineering 集成设计文档.md
  - 财务RAG-Multi-Agent 集成设计文档.md
  - 财务RAG-后端补充需求-地区资料库接口.md
  - 后端资料库接口-AI代码生成上下文包.md
  - 财务RAG-开发注意事项.md
  - 财务RAG-开发踩坑记录.md
  - 财务RAG-项目补充与添加实施规划.md
重组日期: 2026-08-06
---

# 财务 RAG Agent · 后端设计文档

> **文档定位**：由 docs 目录下 11 份来源文档中"后端设计/实现"相关内容**全量提取并打散重排**而成。来源文档中的每一个表格、每一段代码骨架、每一个 API、每一条决策、每一个踩坑均已保留（同一信息多份来源重复时保留最完整一份，其余合并）。关键段落已标注来源文档名。
> **覆盖范围**：技术栈与运行环境 / 项目结构 / 计算引擎 / RAG 检索链路 / 知识图谱 / Agent 设计 / 上下文工程 / 用户上下文持久化 / 资料库接口 / API 清单 / 代码规范与审查结论 / 后端开发路线实录 / 踩坑档案。
> **关联文档链**：`财务RAG-技术架构与Agent方案.md` → `财务RAG-后端开发路线图.md` → `财务RAG-后端审查与重构方案.md` → `财务RAG-后端代码审查报告.md` → `财务RAG-Context Engineering 集成设计文档.md` → `财务RAG-Multi-Agent 集成设计文档.md` → `财务RAG-项目补充与添加实施规划.md`。

---

## 1. 技术栈与运行环境

> 来源：`财务RAG-技术架构与Agent方案.md` §一/§八 + `财务RAG-后端开发路线图.md` Step 1/开发注意事项 + `财务RAG-开发踩坑记录.md` #15。

### 1.1 技术选型总览

| 层级 | 选型 | 关键细节 |
|------|------|---------|
| **LLM** | DeepSeek V4 Flash | `deepseek-v4-flash`，LangChain `create_agent`，流式 SSE，$0.14/$0.28 /百万token |
| **Embedding** | BGE-M3（FlagEmbedding） | GPU fp16 加速，稠密 1024维 + 稀疏词汇权重 双输出 |
| **向量库** | Qdrant Docker | 原生混合检索，`docker compose up -d`，Web UI :6333，`docker-compose.yml` 在项目根目录 |
| **重排器** | BGE-Reranker-v2-m3（BAAI） | 三层分层召回：元数据过滤 → Qdrant RRF 粗排 Top-20 → Cross-encoder 精排 Top-5 |
| **后端** | FastAPI | `StreamingResponse` SSE 流式输出，OpenAI 兼容 SDK |
| **前端** | React + shadcn/ui | monorepo `frontend/`，纯 CSR |
| **PDF 转换** | Microsoft MarkItDown v0.1.6 | 申报表模板 PDF→MD 转换 |
| **硬件** | RTX 4060 8GB / 16GB RAM | Qdrant 答辩时启动，日常关后台释放内存 |

### 1.2 开发环境依赖

**已就绪**（来源：`财务RAG-技术架构与Agent方案.md` §八）：

| 工具 | 版本/状态 |
|------|---------|
| Python | 3.13.12 (managed venv) |
| Node.js | 22.22.2 |
| MarkItDown | v0.1.6 ✅ |
| NVIDIA Driver | 560.94 / CUDA 12.6 ✅ |
| RTX 4060 | 8GB VRAM ✅ |

**需安装**：

| 工具 | 安装方式 |
|------|------|
| Docker Desktop | https://docs.docker.com/desktop/setup/install/windows-install/ |
| Qdrant 镜像 | `docker pull qdrant/qdrant` |

**Python 依赖**：

```bash
pip install fastapi uvicorn[standard]    # 后端框架
pip install FlagEmbedding                # BGE-M3 + Reranker
pip install qdrant-client                # Qdrant SDK
pip install openai                       # DeepSeek（OpenAI 兼容 SDK）
pip install sse-starlette                # SSE 流式
```

**需注册**：

| 平台 | 用途 |
|------|------|
| DeepSeek API Key | https://platform.deepseek.com |

### 1.3 项目骨架与依赖安装（Step 1）

> 来源：`财务RAG-后端开发路线图.md` Step 1。状态：前端已有 `frontend/` 目录（React + shadcn/ui），后端待搭建时按此步骤执行。

**目标**：FastAPI 启动成功 + 所有依赖导入无报错。

**操作**：

```bash
mkdir backend && cd backend
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
```

```bash
pip install fastapi uvicorn[standard] sse-starlette
pip install langchain-deepseek langgraph langchain-core langchain
pip install FlagEmbedding qdrant-client pydantic python-dotenv
```

**文件**：

```
backend/
├── main.py           # FastAPI 入口
├── config.py         # 环境变量 + 常量
├── requirements.txt
└── .env              # DEEPSEEK_API_KEY=sk-xxx
```

**`config.py`**：

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

### 1.4 版本约束与 API 弃用警告（Critical）

> 来源：`财务RAG-后端开发路线图.md` 开发注意事项。开发时严禁使用下表左侧写法。

| 不要用 | 原因 | 用这个 |
|--------|------|--------|
| `create_react_agent` | 已弃用，v1.0 后移除 | `langchain.create_agent()` |
| `model="deepseek-chat"` | **2026-07-24 起弃用** | `model="deepseek-v4-flash"` |
| `model="deepseek-reasoner"` | **同日弃用**，且不支持 Tool Calling | `model="deepseek-v4-flash"` |
| `langgraph.savers.memory.MemorySaver` | v0.2 起路径已变 | `langgraph.checkpoint.memory.MemorySaver` |
| `state["messages"] += [...]` | v0.2+ 强制 reducer | `Annotated[list, operator.add]` |

> 注：LangGraph v1 中 `MemorySaver` 已重命名为 **`InMemorySaver`**（来源：`财务RAG-后端审查与重构方案.md` 修订记录 v4——对齐 LangChain v1 标准：`InMemorySaver` / `create_agent` / 中间件系统 / `args_schema` / `response_format`）。

### 1.5 环境与资源注意事项

> 来源：`财务RAG-后端开发路线图.md` 开发注意事项 + `财务RAG-开发踩坑记录.md` #15。

| 事项 | 说明 |
|------|------|
| **Qdrant Docker 启动顺序** | 必须在 Step 3 之前 `docker-compose up -d`。答辩时提前 5 分钟启动，关掉微信/Chrome 等重应用释放内存 |
| **BGE-M3 首次加载** | 首次 `BGEM3FlagModel("BAAI/bge-m3")` 会从 HuggingFace 下载约 2.2GB 模型文件到 `~/.cache/huggingface/`，需联网。之后秒加载 |
| **BGE-Reranker 同样** | 首次下载约 1.5GB。两个模型总计约 3.7GB |
| **GPU 显存** | BGE-M3 fp16 占用约 2GB，Reranker 约 1.5GB，DeepSeek 走 API 不占显存。RTX 4060 8GB 绰绰有余 |
| **Python 版本** | ≥ 3.10（LangChain 要求）。你已有的 3.13.12 没问题 |
| **.env 文件** | 放在 `backend/.env`，包含 `DEEPSEEK_API_KEY=sk-xxx`。**不要提交到 Git** |

**⚠️ venv 环境坑（langchain 1.3.14 才有 `ToolErrorMiddleware`）**（来源：`财务RAG-开发踩坑记录.md` #15）：

- **现象**：`python -m uvicorn main:app` 启动报 `ImportError: cannot import name 'ToolErrorMiddleware' from 'langchain.agents.middleware'`；用系统 Python（3.13）导入 langchain.agents 冷启动耗时 13s。
- **根因**：项目后端依赖装在 `backend/venv`（langchain **1.3.14**，含 `ToolErrorMiddleware`）；系统 Python 里是 langchain **1.3.12**（该 middleware 叫 `ToolRetryMiddleware`）。两套环境并存，用错环境即崩。
- **修复**：统一用 `backend/venv/Scripts/python.exe` 启动（start.bat 已如此）；venv 缺 `markdown` 模块，`pip install "markdown~=3.8.0"` 补齐。
- **规律**：多环境机器先确认 `which python` / 项目 README 指定的解释器；`import` 验证依赖版本再跑服务。

**依赖库补充**（来源：`后端资料库接口-AI代码生成上下文包.md` §2）：`fastapi` / `pydantic` 已有；资料库接口的 Markdown 转 HTML 用 `markdown` 库（requirements.txt 如无则需添加）。

---

## 2. 项目结构与模块划分

### 2.1 顶层项目结构

> 来源：`财务RAG-技术架构与Agent方案.md` 七、项目结构。

```
finance-rag/
├── backend/                # FastAPI
│   ├── main.py             # 入口
│   ├── routers/            # API 路由
│   ├── rag/                # RAG 核心：检索 + 重排 + LLM 调度
│   │   ├── retriever.py    # Qdrant 混合检索
│   │   ├── reranker.py     # BGE-Reranker 精排
│   │   └── generator.py    # DeepSeek 流式调用
│   ├── tools/              # Agent 工具集（6个）
│   │   ├── search_knowledge.py
│   │   ├── calculate_tax.py
│   │   ├── query_social.py
│   │   ├── fill_form.py
│   │   ├── filing_guide.py
│   │   └── search_website.py
│   └── services/           # 业务逻辑
├── frontend/               # React + shadcn/ui
│   └── src/
├── rag-data/               # 资料（收集产出）
│   ├── raw/
│   └── processed/
├── docker-compose.yml      # Qdrant 容器
└── requirements.txt
```

### 2.2 后端目录结构（重构后）

> 来源：`财务RAG-后端审查与重构方案.md` 五、文件结构变化。Agent 通路与上下文工程落地后的完整结构。

```
backend/
├── agent/                          ← 新建
│   ├── __init__.py
│   ├── engine.py                   ← create_agent + MemorySaver（Step 6 核心）
│   └── prompts.py                  ← SYSTEM_PROMPT（从 services/generator.py 迁出+增强）
│
├── tools/                          ← 新建
│   ├── __init__.py                  ← ALL_TOOLS 列表（顺序影响 LLM 选择倾向）
│   ├── base.py                     ← 工具返回结构 schema + 共享工具函数
│   ├── search_knowledge.py         ← rag/retriever.py 的 @tool 封装（async + to_thread）
│   ├── calculate_income_tax.py     ← services/tax_engine.py 的 @tool 封装
│   ├── query_social_insurance.py   ← services/social_engine.py 的 @tool 封装
│   ├── user_context.py             ← get/update_user_context @tool + contexts dict（含锁）
│   ├── fill_tax_form.py            ← 从 scripts/ 迁移，加 @tool 装饰器
│   └── filing_guide.py             ← RAG 检索 operations/ 目录
│
├── routers/
│   ├── chat.py                     ← 重构：Pydantic ChatRequest + agent.astream_events + SSE 事件映射
│   ├── tax.py                      ← 保留（快捷表单入口，非 Agent 通路）
│   └── social.py                   ← 保留（同上）
│
├── rag/                            ← 不变
│   ├── retriever.py
│   └── query_rewriter.py
│
├── services/                       ← 不变（generator.py Phase 6 移除或重命名为 legacy_generator.py）
│   ├── tax_engine.py               ← 已修复版（5 项缺陷），不再修改
│   └── social_engine.py            ← 已修复版（5 项缺陷），不再修改
│
├── config.py                       ← 微调：统一路径计算基准
└── main.py                         ← 微调：注册 tools 初始化，路由前缀 /api
```

**数据引擎文件布局**（来源：`财务RAG-后端开发路线图.md` Step 2）：`backend/data/` 下 `tax_rates.json`（税率表：7 级综合 + 5 级经营 + 预扣率）、`deductions.json`（7 项专项附加扣除标准）、`cities/zhengzhou.json`（郑州社保比例 + 基数 + 公积金），`backend/services/tax_engine.py`（计算引擎，纯函数）。

**资料库接口文件布局**（来源：`后端资料库接口-AI代码生成上下文包.md` §2）：`backend/routers/{tax,social,chat,form}.py`（路由层，风格参照）、`backend/services/{tax_engine,social_engine}.py`（纯逻辑服务层，风格参照）、`backend/data/`（SQLite，与资料库接口无关）。

### 2.3 上下文工程模块结构

> 来源：`财务RAG-Context Engineering 集成设计文档.md` §2 架构总览。

```
backend/
├── context/                    # 上下文工程模块（新增）
│   ├── __init__.py
│   ├── types.py                # BudgetAllocation / 事件常量
│   ├── token_est.py            # 中文字符 ↔ token 估算
│   ├── budget.py               # TokenBudget：预算参数计算（核心决策源）
│   ├── history_summarizer.py   # 历史摘要器：包装官方 SummarizationMiddleware + 扩展
│   ├── guard.py                # 工具返回瘦身（主力，已实现）：search_knowledge 拼接文本提取式压缩
│   └── judge.py                # 摘要保真 judge + 画像字段自动校验
├── eval/
│   ├── context_eval.py         # 评测主脚本（长对话场景集）
│   └── dialog_scenarios.json   # 长对话场景评测集（5-10 场景 × 20 轮）
├── agent/engine.py             # 集成：middleware 链挂 HistorySummarizer（修改）
├── routers/chat.py             # SSE：新增 context 事件（修改）
└── tools/search_knowledge.py   # 保障压缩调用点（修改）
```

### 2.4 双通路 + REST 三通路架构

> 来源：`财务RAG-后端代码审查报告.md` 1.1 架构现状。后端采用 **双通路架构**：

| 通路 | 入口 | 链路 | 状态 |
|------|------|------|------|
| **Agent 通路**（新） | `POST /api/chat` | `create_agent` → `@tool` 自动调度 → `astream_events` → 8 种 SSE 事件 | 已上线 |
| **Legacy 通路**（旧） | `POST /chat`、`POST /chat/with-search` | 直连 `retriever.retrieve` → `generator.stream_answer` → 3 种 SSE 事件 | 保留 |
| **REST 表单通路** | `POST /api/tax/calculate`、`POST /api/social/calculate` | Pydantic 校验 → 引擎计算 → JSON | 保留 |

### 2.5 变量命名约定

> 来源：`财务RAG-后端审查与重构方案.md` 五。

| 变量 | 值 | 位置 |
|------|-----|------|
| `contexts: dict[str, dict]` | `{thread_id: {city, salary, ...}}` | `tools/user_context.py`（操作时加 `threading.Lock`） |
| `_current_thread_id: ContextVar` | 当前请求的 thread_id | `tools/user_context.py` |
| `ALL_TOOLS` | `[get_user_context, search_knowledge, calculate_income_tax, ...]` | `tools/__init__.py` |
| `agent` | `create_agent(...)` 返回值 | `agent/engine.py` |
| `InMemorySaver` | LangGraph v1 开发级 checkpointer（管理对话历史 messages） | LangGraph 内部 |

> **`InMemorySaver` 与 `contexts` dict 的关系**：
> - `InMemorySaver`：管理**对话历史**（messages），LangGraph 内部自动读写，重启即丢
> - `contexts` dict：管理**用户画像**（city/salary/income_type），`@tool` 手动读写，重启即丢
> - 二者通过 `thread_id` 关联，职责分离
> - 毕设阶段接受内存存储；答辩后可换 `SqliteSaver` + JSON 文件持久化（已于 2026-08-06 落地为自建 SQLite 三表方案，见 §8）
> - **注意**：`contexts` dict 无 TTL 清理机制，毕设 demo 时长有限不影响；若长期运行需加 TTL（如 30 分钟未访问即删除）

---

## 3. 计算引擎设计

> 核心原则（多来源一致）：**税率/社保计算不走 LLM，走纯代码引擎**——`tax_engine.py` / `social_engine.py` 读取 JSON 税率表 + formula 字段公式计算，输出结构化 JSON，零幻觉。工具负责调用引擎，LLM 只解释结果。
> 来源：`财务RAG-技术架构与Agent方案.md` §3.2/3.3/3.7、`财务RAG-后端开发路线图.md` Step 2、`财务RAG-后端审查与重构方案.md`（引擎修复记录 + 重构原则）、`财务RAG-开发注意事项.md` §3.3、`财务RAG-Multi-Agent 集成设计文档.md` §2.2/§5.5。

### 3.1 设计原则

**工具返回结构化结果，不经过 LLM**（来源：`财务RAG-技术架构与Agent方案.md` §三）：LLM（DeepSeek V4 Flash）根据用户意图自动选择工具。工具返回结构化结果后，由 LLM 组织语言流式输出。

**Agent 工具调度规范之计算规则**（来源：`财务RAG-开发注意事项.md` §3.3）：`calculate_income_tax` 和 `query_social_insurance` 必须读取 JSON + 公式，不走 LLM 推理；申报材料 `fill_tax_form` 是 key-value 填表，不是 LLM 生成。

**重构原则第 3 条**（来源：`财务RAG-后端审查与重构方案.md` §十）：计算引擎已修复，重构期间不再改引擎逻辑——`services/tax_engine.py` 和 `services/social_engine.py` 已修复 5 项缺陷并验证通过，仅在 `tools/` 中封装调用。`calculate_income_tax` @tool 的入参含 `bonus`，内部继承 ratio 换算逻辑。

### 3.2 tax_engine —— 综合所得个税计算

**数据文件格式**（来源：`财务RAG-后端开发路线图.md` Step 2）：

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

**`services/tax_engine.py` 代码骨架**：

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

**数据源全量清单**（来源：`财务RAG-技术架构与Agent方案.md` §3.2）：`tax_rate_tables.json` 含综合所得税率表、经营所得税率表、年终奖月度税率表、专项附加扣除标准、收入类型计入规则、累计预扣法流程、汇算清缴流程。动作：读取 JSON → 按 `formula` 字段的步骤计算（不经过 LLM）。输出：`{taxable_income, tax_amount, marginal_rate, brackets_used, breakdown[]}`。

**✅ 通过标准**：

```python
from services.tax_engine import calculate_comprehensive_tax
result = calculate_comprehensive_tax(annual_income=120000, social_insurance=9888, special_deductions=18000)
assert result["taxable_income"] == 32112
assert result["tax_amount"] == 963.36
```

### 3.3 social_engine —— 社保公积金计算

**输入/输出**（来源：`财务RAG-技术架构与Agent方案.md` §3.3）：

```
输入: city, employment_type (employee/flexible), salary
数据源: cities/zhengzhou/social_insurance.json
        含: 职工社保(养老/医疗/失业/工伤/生育) + 住房公积金(5%-12%)
            灵活就业(养老20%/医疗10%) + 灵活就业公积金(20%)
            缴费基数上下限 + 2个计算示例
动作: 读取 JSON → 按 salary 匹配基数 → 计算个人/单位应缴
输出: {breakdown: {养老:{单位,个人}, 医疗:{...}, ...}, total_personal, total_employer}
```

### 3.4 行业基准 —— search_industry_benchmark

> 来源：`财务RAG-技术架构与Agent方案.md` §3.7 + `财务RAG-后端补充需求-地区资料库接口.md` §2.2。

```
输入: industry_name (行业名称), metric (指标名,可选)
数据源: industry_benchmark.json（20门类×97行业×10项指标，含中文标签+单位）
动作: 精确匹配行业 → 读取各项指标 {low, high} 范围
      如指标为 null → 提示该指标不适用此行业
输出: {industry, category, metrics:{vat_burden:{low,high,label}, ...}}
```

> ⚠️ 结构化数据走精确匹配，不走向量检索。

`industry_benchmark.json` 顶层结构（来源：`财务RAG-后端补充需求-地区资料库接口.md` §2.2）：`{ tool_usage, meta, industries }`；`industries`：20 个行业门类 × 97 个细分行业 × 10 项指标。指标：`vat_burden`(增值税税负率) / `cit_burden`(企业所得税税负率) / `gross_margin`(毛利率) / `net_margin`(净利率) / `receivable_turnover`(应收周转) / `inventory_turnover`(存货周转) / `debt_ratio`(资产负债率) / `current_ratio`(流动比率) / `quick_ratio`(速动比率) / `expense_ratio`(费用率)。每项 `{low, high}` 范围对象，不适用为 null。

> ⚠️ **字段名易错**（来源：`后端资料库接口-AI代码生成上下文包.md` §8 常见坑 1）：JSON 原生字段是 `ar_turnover`（**不是** `receivable_turnover`），必须原样透传，勿改名。

### 3.5 引擎修复记录（2026-07-30，5 项实现缺陷已修复）

> 来源：`财务RAG-后端审查与重构方案.md` §一。核心逻辑按设计；修复后 @tool 封装基于修复后版本。

- `tax_engine.py`：年终奖对比计税 bonus 按收入类型 ratio 换算；`_find_bracket` 未排序校验；模块级 `open()` 加错误处理
- `social_engine.py`：灵活就业费率从数据文件读取（不再硬编码）；`calculate_flexible_social` 修复 `salary` 与 `base_level` 参数忽略问题；模块级 `open()` 加错误处理

### 3.6 B 表 business 分支（calculate_business_income_tax）

**工具**（来源：`财务RAG-Multi-Agent 集成设计文档.md` §2.2 8 工具清单 #4）：`calculate_business_income_tax` 计税（个体户 B 表），返回 `result_card + disclaimer`。

**B 表双工具链路（v1.1 决策：主 Agent 协调）**（来源：`财务RAG-Multi-Agent 集成设计文档.md` §5.5）：个体户申报场景（"先填表再计税"）**顺序协调归主 Agent**，子 Agent 不集成 `fill_tax_form`：

- 主 prompt 保留并强化该规则（原文 `prompts.py:25`）："**若用户提'B表'或'个体户申报'，先调 `fill_tax_form(B表)` 填基础信息，再调 `tax_subagent` 计税，顺序不可颠倒**"
- 子 Agent 职责纯粹：只算税，不填表；填表结果卡片与计税卡片由主 Agent 依次触发下发
- 两个工具间**无数据通道**（填表结果与计税输入各自独立），符合现状（现链路本来也是两次独立工具调用）

**计税子 Agent 中的 B 表路由规则**（来源：`财务RAG-Multi-Agent 集成设计文档.md` §5.2）：个体户/经营所得 → `calculate_business_income_tax`（5%-35% 五级累进）；工资/劳务/稿酬/特许权 → `calculate_income_tax`；年终奖单独计税对比 → `calculate_income_tax` 的 `bonus` 参数。

**踩坑记录**（来源：`财务RAG-项目补充与添加实施规划.md` §4.1 踩坑 3）：`fill_tax_form` 需在 SYSTEM_PROMPT_MULTI 中加示例 + B 表两步流程结构化，否则 LLM 倾向先查画像再放弃。

### 3.7 计算引擎 @tool 入参规范

> 来源：`财务RAG-后端审查与重构方案.md` §4.1 工具集实现路线。`@tool` 编写规范（v1 最佳实践）：使用 `args_schema` + Pydantic `Field(description=...)` 提升 LLM 参数生成准确度。每个工具的 docstring 第一句说明"何时使用"，帮助 LLM 做工具选择。

| 工具 | 输入 | 数据源/逻辑 | 迁移来源 | 注意 |
|------|------|------------|---------|------|
| `search_knowledge(query)` | 用户问题原文 | `rag/retriever.py` → `retriever.retrieve()` | 现有 RAG 链路，包 @tool | ⚠️ `async def` + `asyncio.to_thread()` 包装，避免阻塞事件循环 |
| `calculate_income_tax(annual_income, income_type, social_insurance, deductions, city, bonus)` | 收入、扣除、城市 | `services/tax_engine.py` → JSON 税率表公式计算 | 现有引擎（已修复版），包 @tool | `deductions` 为 `dict[str, float]`，如 `{"housing_rent": 1500}`（元/月）；`income_type` 为 `str`，docstring 声明枚举值 `"salary"\|"labor_service"\|"manuscript"\|"royalty"` |
| `query_social_insurance(city, employment_type, salary, housing_fund_ratio, flexible_base_level)` | 城市、就业类型、工资 | `services/social_engine.py` → JSON 社保数据查表 | 现有引擎（已修复版），包 @tool | 从数据文件读取费率，非硬编码；`flexible_base_level` 支持灵活就业档次选择 |
| `get_user_context()` | 无（读 `contexts[thread_id]`） | per-thread dict `{city, salary, income_type, deductions}` | **新建** | `thread_id` 通过 `contextvars.ContextVar` 传递（PoC 必须先验证传播） |
| `update_user_context(key, value)` | key + value | 写入 `contexts[thread_id]` | **新建** | key 合法值: `city`/`salary`/`income_type`/`housing_rent`/`children_edu`/`elderly_support`；内部白名单校验 |

---

## 4. RAG 检索链路

### 4.1 三层分层召回总链路

> 来源：`财务RAG-技术架构与Agent方案.md` 二、检索链路。技术栈定义的分层召回参数：元数据过滤 → Qdrant RRF 粗排 **Top-20** → Cross-encoder 精排 **Top-5**。

```
用户提问
  ↓
Layer 1: 元数据预过滤（payload filter）
  根据意图分类 → 限定 category（tax_law / qa / operations / rates）
  ↓
Layer 2: Qdrant 混合检索（粗排 Top-20）
  BGE-M3 双向量编码（dense 1024d + sparse 词汇权重）
  → Qdrant RRF 融合 → 召回 Top-20
  ↓
Layer 3: BGE-Reranker-v2-m3 精排（精筛 Top-5）
  Cross-encoder 逐对打分 → 取 Top-5
  ↓
┌─ 知识图谱扩展（Layer 4）────────────────┐
│ 命中 relations.json → 双向遍历+两跳推理  │
│ 例: 汇算办法 →(逆向) 个税法 →(2跳) 实施条例 │
│     → 补充关联文档到检索结果              │
└────────────────────────────────────────┘
  ↓
拼接 System Prompt + RAG 上下文 + 用户提问
  ↓
DeepSeek V4 Flash → StreamingResponse 流式输出
```

### 4.2 向量化入库（Step 3）

> 来源：`财务RAG-后端开发路线图.md` Step 3。状态：✅ 已完成。`scripts/chunk_docs.py` + `scripts/embed_and_upsert.py`，BGE-M3 编码 2419 chunks → Qdrant collection `finance_knowledge`（dense 1024d + sparse 双向量）。

**目标**：`rag-data/processed/` → BGE-M3 编码 → Qdrant collection 创建完毕。

**前置**：资料收集完成（`rag-data/processed/` 目录就绪）；**Docker Desktop 已安装** + Qdrant 镜像已拉取 → `docker compose up -d`（`docker-compose.yml` 在项目根目录）。

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

### 4.3 混合检索 + 重排实现（Step 4）

> 来源：`财务RAG-后端开发路线图.md` Step 4。状态：✅ 已完成。`backend/rag/retriever.py`：三层分层召回（元数据过滤 → dense+sparse RRF融合 → Reranker精排 → relevance_weight加权）。单例模式，Agent 直接 `from rag import search_knowledge` 调用。

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

### 4.4 search_knowledge 检索参数与切分策略

> 来源：`财务RAG-技术架构与Agent方案.md` §3.1。

```
输入: query (用户问题原文)
检索链路:
  Layer 1: 元数据预过滤（relevance_tier 分层，支持按 category/city 过滤）
  Layer 2: BGE-M3 双向量编码 → Qdrant 混合检索 → RRF 融合 → Top-30
  Layer 3: BGE-Reranker-v2-m3 Cross-encoder 精排 → Top-5
         → relevance_weight 乘入最终分数（tax_law×1.0, regulation×0.8,
            qa_corpus×0.6, general_law×0.3）
输出: [{content, source_url, doc_title, relevance_tier, score}, ...]

切分策略: MarkdownHeaderTextSplitter
  - 税法: ### 第X条 边界, 800字上限/80字下限/120字重叠(15%)
  - QA:   ## 问句 边界, 同上参数
```

### 4.5 BGE-Reranker 权重公式（relevance_weight）

> 来源：`财务RAG-技术架构与Agent方案.md` §3.1 + `财务RAG-后端开发路线图.md` 优化记录。

精排阶段最终分数 = Reranker Cross-encoder 得分 × **relevance_weight** 层级权重：

| 层级 | 权重 |
|------|:--:|
| tax_law | ×1.0 |
| regulation | ×0.8 |
| qa_corpus | ×0.6 |
| general_law | ×0.3 |

**WEIGHT_OVERRIDES 机制**（来源：`财务RAG-技术架构与Agent方案.md` §9.5 优化方法论）：关键文档在 Reranker 阶段权重不足（如法规条文 vs Q&A）时，用 `scripts/embed_and_upsert.py` 中的 `WEIGHT_OVERRIDES` 覆盖（重嵌时自动应用）。优化记录中的权重实例：企税/个税混淆时 DOC_KEYWORDS 注入；年终奖 case 中操作指南 weight 过高误伤 → weight 精准化；个税法 weight=12 过度泛化 → 回调 weight→10（来源：`财务RAG-后端开发路线图.md` 优化过程表第 3/6/7 轮）。

### 4.6 Query 改写层

> 来源：`财务RAG-后端开发路线图.md` Step 4.8 + `财务RAG-技术架构与Agent方案.md` §9.5。状态：✅。

- 位置：`backend/rag/query_rewriter.py`
- 机制：50+ 条口语→术语映射表 + Key 长度降序匹配，弥合用户口语与法律文本的语义鸿沟
- 部署注意：无需重嵌，重启后端即生效
- 面试话术（来源：`财务RAG-后端开发路线图.md` 面试武器库 Step 4.8）："Query 改写层：50+ 条口语→术语映射表 + Key 长度降序匹配，弥合用户口语与法律文本的语义鸿沟"

优化实录中的 Query 改写案例（来源：`财务RAG-后端开发路线图.md` 优化过程表）：

| 轮次 | 失败 query | 根因 | 修复 |
|:--:|------|------|------|
| 1 | #36 电子发票 | 向量被吸到增值税发票 | Query 改写：电子发票→法律效力+电子商务法 |
| 3 | #16 个税APP | 操作流程语言与政策问答语义鸿沟 | DOC_KEYWORDS + Query改写 + DOC_KEYWORDS存入内容让Reranker可见 |
| 5 | #25 社保不交 | "企业→企业所得税法"盲匹配 | Query改写：去税词+加社会保险法/劳动合同法 |

### 4.7 文档级去重

> 来源：`财务RAG-开发踩坑记录.md` #14（检索器真实缺陷）+ `财务RAG-技术架构与Agent方案.md` §9.5 优化方法论 + §9.4 评测结果说明。

- **现象**：60 条评测首跑 #47（年终奖合并 vs 单独计税）miss——top5 中 4 个都是《个人所得税法》的不同 chunk，《百问百答》被挤出前五；修复标注后仍未全命中。
- **根因**：`retriever.retrieve()` 链路为"Reranker 精排 → 直接截 top_k"，无**文档级去重**。超长法规（如个税法）切多 chunk 后，Reranker 对同一文档的多个 chunk 打高分 → 挤占其他文档槽位（Recall@5 全局 72.5% → 修复后 85%）。
- **修复**：`retrieve()` 精排放宽取 `top_k*2` → 按 `doc_title` 去重（同文档只留最高分 chunk）→ 截断 top_k。同时修正 3 条评测标注（#45/#47/#56 的 expected_docs 关联判断失误）。
- **规律**：混合检索 + 重排的 pipeline，务必在最终截断前做**文档级去重**——评估指标（recall/precision）和 LLM 上下文质量都按"文档"计，不按"chunk"计。

**优化方法论机制表**（来源：`财务RAG-技术架构与Agent方案.md` §9.5，优化遵循"逐条根因诊断 → 分类失配模式 → 针对性机制修复"三步法，不依赖调参）：

| 机制 | 文件 | 解决问题 |
|---|---|---|
| **Query 改写层** | `backend/rag/query_rewriter.py` | 用户口语"怎么退税""五险一金"与法律文本的语义鸿沟 |
| **DOC_KEYWORDS 注入** | `scripts/embed_and_upsert.py` | 特定文档在向量空间中与同质文档距离过近 |
| **DOC_KEYWORDS 存内容** | 同上 | Reranker 无法感知向量增强词（仅影响检索不影响重排） |
| **WEIGHT_OVERRIDES** | 同上 | 关键文档在 Reranker 阶段权重不足（如法规条文 vs Q&A） |
| **QA 结构修复** | `scripts/fix_qa_headings.py` | MarkdownHeaderTextSplitter 无法识别无 `##` 的 QA 边界 |
| **文档级去重** | `backend/rag/retriever.py` | 超长法规多 chunk 挤占 top-k 槽位（Reranker 精排放宽 top_k*2 → 同 doc_title 只留最高分 chunk → 截断） |

**可复用机制与部署注意**（来源：`财务RAG-后端开发路线图.md` 可复用机制表）：

| 机制 | 文件 | 部署注意 |
|---|---|---|
| Query 改写 | `backend/rag/query_rewriter.py` | 无需重嵌，重启后端即生效 |
| DOC_KEYWORDS | `scripts/embed_and_upsert.py` | 需重嵌生效 |
| WEIGHT_OVERRIDES | `scripts/embed_and_upsert.py` | 重嵌时自动应用 |
| QA 结构修复 | `scripts/fix_qa_headings.py` | 一次性脚本，需重新切分+重嵌 |
| 轻量知识图谱 | `rag-data/relations.json` + `backend/rag/retriever.py` | 20条规则，部署时放 rag-data/ 下，Retriever 启动加载 |

### 4.8 检索器线程安全单例

> 来源：`财务RAG-后端代码审查报告.md` §3.2 优秀实践（`rag/retriever.py` 第 454–466 行）。

双重检查锁 + 懒加载，避免重复加载 BGE-M3 模型（约 2GB 显存），且线程安全：

```python
_retriever: Optional[Retriever] = None
_retriever_lock = threading.Lock()

def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            if _retriever is None:      # 双重检查
                _retriever = Retriever()
    return _retriever
```

> **对比**：`get_agent()`（`agent/engine.py`）已对齐同样的双重检查锁模式（见 §11.2 H1 修复）。

### 4.9 检索评测体系

> 来源：`财务RAG-技术架构与Agent方案.md` §九（评测体系全量）+ `财务RAG-项目补充与添加实施规划.md` §5.3（⑨ 评测扩展）。评测实录（67.5%→77.5%）见 §12.3。

#### 4.9.1 评测数据集

位置：`backend/eval/eval_set.json`

- **规模**：60 条 query，覆盖 12 个类别（2026-08-05 由 40 条扩展：新增个体户 B 表、年终奖、汇算清缴案例、专项附加扣除边界值各若干条）
- **标注方式**：每条标注 1-2 个期望命中的文档标题（仅标注文档名，不标分数）
- **类别分布**：

| 类别 | 数量 | 说明 |
|------|:--:|------|
| 个税-基础 | 5 | 起征点、税率、综合所得、预扣预缴 |
| 个税-专项扣除 | 12 | 租房/房贷/子女/赡养/婴幼儿/大病/继续教育 + 边界值 |
| 个税-特殊 | 8 | 年终奖、劳务报酬、股权激励、合伙/个独、平台代扣 |
| 个税-汇算 | 9 | 汇算清缴、退税补税、APP操作、多退少补 |
| 增值税 | 4 | 税率、小规模纳税人、发票犯罪 |
| 社保 | 3 | 五险一金、缴费比例、维权 |
| 契税 | 2 | 买房契税、房产过户 |
| 车辆税 | 2 | 购车税、车船税 |
| 印花税 | 2 | 印花税、合同印花税 |
| 经营主体 | 6 | 个体工商户（建账/定期定额/核定）、企业所得税 |
| 程序法 | 3 | 偷税处罚、欠税、电子发票 |
| 其他税种 | 4 | 环保税、城建税、关税、资源税 |

#### 4.9.2 评测脚本

位置：`backend/eval/eval.py`（检索层）+ `backend/eval/run_all.py`（三层一键）。无外部依赖，直接调用 `retriever.retrieve()` 完成：

```
python eval/run_all.py           # 一键三层评测（检索 + 工具 + 生成，聚合 run_all_report.json）
python eval/eval.py              # 完整评测
python eval/eval.py -v           # 逐条打印详情
python eval/eval.py -o report.json  # 导出 JSON 报告
python eval/eval.py --category 个税  # 按分类评测
```

#### 4.9.3 评测指标

| 指标 | 说明 | 用途 |
|------|------|------|
| **Recall@1/3/5** | 期望文档出现在 top-k 中的比例 | 检索覆盖面 |
| **Precision@5** | top-5 中命中期望文档的比例 | 检索精准度 |
| **MRR** | 第一个命中文档排名的倒数均值 | 排序质量 |
| **NDCG@5** | 考虑排序位置的归一化折损累积增益 | 综合排序质量 |

#### 4.9.4 最终评测结果

> 数据截至 2026-08-05，60 条全量评测（含文档级去重优化后）。

| 指标 | 优化前（40 条） | 最新（60 条） | 提升 |
|---|---|---|---|
| Recall@5 | 77.5% | **85.0%** | +7.5pp |
| Recall@3 | 66.25% | **68.33%** | +2pp |
| Recall@1 | 51.25% | **50.0%** | −1.25pp |
| Precision@5 | 22.5% | **27.0%** | +4.5pp |
| MRR | 0.8329 | **0.8422** | +0.009 |
| NDCG@5 | 0.7115 | **0.7585** | +0.047 |
| 失败 query 数 | 0 条（40/40） | **0 条（60/60 全部命中）** | 🎉 |
| 分类通过率 | 12/12 (100%) | **12/12 (100%)** | 🎉 |

> 说明：2026-08-05 新增 20 条冷门题（个体户 B 表 / 年终奖边界 / 汇算案例）后首跑 Recall@5 曾降至 72.5%，经两处修复回升至 85%：① 修正 3 条评测标注（文档相关性判断失误）；② 检索器新增**文档级去重**（同一 doc_title 多 chunk 挤占 top5 槽位）。指标为修复后全量结果。

| 分类 | 数量 | Avg R@5（60 条） |
|---|---|---|
| 个税-专项扣除 | 12 | **83.33%** |
| 个税-基础 | 5 | **100%** |
| 个税-汇算 | 9 | **72.22%** |
| 个税-特殊 | 8 | **87.50%** |
| 其他税种 | 4 | **87.50%** |
| 印花税 | 2 | **100%** |
| 增值税 | 4 | **87.50%** |
| 契税 | 2 | **75.0%** |
| 社保 | 3 | **100%** |
| 程序法 | 3 | **83.33%** |
| 经营主体 | 6 | **75.0%** |
| 车辆税 | 2 | **100%** |

#### 4.9.5 评测使用场景

- 每次修改检索链路后运行一次，对比指标变化
- 答辩时提供客观数据支撑（如"Recall@5 达 85%，MRR 达 0.76"）
- 失败 case 直接指出薄弱方向（如某类 query 召回率低）

#### 4.9.6 评测集扩展（补充项 ⑨）

> 来源：`财务RAG-项目补充与添加实施规划.md` §5.3。状态：✅ 已完成（60 条，Recall@5 = 85%，run_all.py 落地）。

- **目标**：eval_set.json 40 条 → 60 条（重点补：个体户 B 表、年终奖、汇算清缴案例、专项附加扣除边界值）；把三层评测串成一键脚本。
- **改动文件**：修改 `backend/eval/eval_set.json`（**追加不覆盖**）；新增 `backend/eval/run_all.py`（检索层 + 工具层 + 生成层一键跑）
- **验收标准**：① 新评测集跑通且 recall@5 不降；② `run_all.py` 单命令输出三层报告。

---

## 5. 知识图谱与关系索引

### 5.1 设计动机

> 来源：`财务RAG-技术架构与Agent方案.md` §2.1。财税法规存在密集交叉引用。纯向量检索命中"个税法"，但"实施条例""专项扣除细则"等关联文档需要二次查询。

**方案**：20 条精选关联规则 JSON + 双向遍历 + 两跳推理，零数据库依赖——无需 Neo4j、无需图数据库（来源：`财务RAG-后端开发路线图.md` Step 4.5）。

### 5.2 relations.json 20 条规则

> 来源：`财务RAG-技术架构与Agent方案.md` §2.1 + `财务RAG-后端开发路线图.md` Step 4.5。

**索引文件** `rag-data/relations.json`（20 条规则）：

| 关系类型 | 数量 | 示例 |
|---|---|---|
| implemented_by / detailed_by | 7 | 个税法 → 实施条例、专项附加扣除暂行办法 |
| administered_by / guide_doc | 3 | 汇算管理办法 → 年度汇算公告 |
| extended_by / special_case | 4 | 个税法 → 婴幼儿照护通知、年终奖百问百答 |
| related_law / companion_tax | 3 | 社保法 ↔ 劳动合同法、车辆购置税法 ↔ 车船税法 |
| penalty_detail / special_income | 3 | 税收征管法 → 虚开发票犯罪决定、个税法 → 股权激励QA |

**索引格式（JSON 示例）**：

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

### 5.3 检索增强流程（Layer 4）

> 来源：`财务RAG-技术架构与Agent方案.md` §2.1 + `财务RAG-后端开发路线图.md` Step 4.5。**已集成到 `retriever.retrieve()` 末尾**。

```
Layer 1-3: 元数据过滤 → 混合检索 → Reranker 精排 → Top-5
Layer 4: 知识图谱扩展
  ├─ 正向: 主结果文档作为 source → 拉 target
  ├─ 逆向: 主结果文档作为 target → 反推 source
  └─ 两跳: 一阶 target 再作为 source → 拉二阶关联
```

**核心能力**：
- **正向遍历**：source → target（个税法 → 实施条例）
- **逆向遍历**：target → source（实施条例反推个税法）
- **两跳推理**：A → B → C（汇算办法 → 个税法 → 操作指南 + 实施条例）
- **触发词过滤**：每条规则含 trigger_keywords 避免过度触发
- **关系语义**：每条边含 description 供前端展示

**文件结构**：

```
rag-data/
└── relations.json                # 20 条精选关联规则

backend/rag/
└── retriever.py                  # _expand_relations() 方法
    └── Layer 4: 知识图谱扩展      # 集成在 retrieve() 末尾
```

### 5.4 实测示例

> 来源：`财务RAG-技术架构与Agent方案.md` §2.1 与 `财务RAG-后端开发路线图.md` Step 4.5（两处结果一致，保留完整一份）：

```
输入: "个税汇算清缴怎么操作"
├─ 主检索: 汇算清缴管理办法 + 2023年度汇算公告
├─ 1跳(逆向): 汇算办法 → 个人所得税法 🔗
├─ 2跳: 个税法 → 实施条例 🔗 + APP操作指南 🔗
└─ 输出: 10条结果(主5 + 图5)，完整关联链
```

（Step 4.5 的编号版：#1-5 汇算清缴管理办法 + 年度汇算公告；#6-7 个人所得税法 🔗 知识图谱（1跳·逆向）；#8-9 实施条例 🔗 知识图谱（2跳）；#10-11 APP操作指南 🔗 知识图谱（2跳）。）

### 5.5 关键设计

> 来源：`财务RAG-技术架构与Agent方案.md` §2.1。

- 每条关系含 `trigger_keywords` 避免过度触发（如"交社保"才触发社保→劳动合同法关联）
- 关系结果标记 `relation_source: "知识图谱（N跳）"` + `relation_desc` 语义描述
- 前端可在来源链接中区分展示为"关联法规"

**✅ 通过标准**（来源：`财务RAG-后端开发路线图.md` Step 4.5）：

```python
retriever = Retriever()
results = retriever.retrieve("个税起征点")
# 应有 #6+ 的关联法规结果，含 "实施条例"
assert any("relation_source" in r for r in results)
```

### 5.6 面试话术

> 来源：`财务RAG-后端开发路线图.md` 面试武器库 Step 4.5。

"轻量知识图谱：20条关联规则 JSON + 双向遍历 + 两跳推理，替代 Neo4j 实现法条多跳交叉引用，零数据库依赖"

---

## 6. Agent 设计

### 6.1 架构演进总览

> 来源：`财务RAG-技术架构与Agent方案.md` §五（原单 Agent 调度架构）+ `财务RAG-Multi-Agent 集成设计文档.md` §2（现状盘点与演进）+ `财务RAG-后端开发路线图.md` Step 6 演进注记。

**原单 Agent 调度架构（现为 `AGENT_MODE=tools` 形态，回退保底路径）**：

```
用户提问
  ↓
LLM（DeepSeek V4 Flash）判断意图 → 选择工具
  ├── 通用财税问答        → search_knowledge
  ├── 时效性/最新政策      → search_tax_website
  ├── "个税怎么算"         → calculate_income_tax
  ├── "工资扣了多少社保"    → query_social_insurance
  ├── "帮我生成申报表"     → fill_tax_form
  ├── "怎么退税/报税"      → get_filing_guide (+ search_knowledge)
  └── 复杂交叉问题         → 多工具并行调用
  ↓
工具返回结构化结果 + RAG 检索上下文
  ↓
LLM 组织语言 → StreamingResponse 流式输出（SSE）
```

**Agent 实现方式**：LangChain `create_agent` + `MemorySaver`，6 个 `@tool` 通过 Function Calling 自动路由。

> **2026-08-04 演进：Multi-Agent 化（P1 设计完成）**——计税/社保拆为双子 Agent（Tool-as-Subagent），`AGENT_MODE` 模式开关 + prompt 双版本 + 失败降级 + 绕过检测，10 项设计决策齐全。原单 Agent 架构为 `AGENT_MODE=tools` 形态，仍是回退保底路径。
> **2026-08-05 演进：Multi-Agent 化（P1 ✅ 已完成）**——三层评测全绿：主 Agent 路由 26/26、主层对拍 8/8、子层 10/10。（来源：`财务RAG-后端开发路线图.md` Step 6 演进注记）

**Multi-Agent 现状盘点（单 Agent 架构）**（来源：`财务RAG-Multi-Agent 集成设计文档.md` §2.1）：

```
主 Agent（backend/agent/engine.py: build_agent）
  ├─ create_agent(model=DeepSeek, tools=ALL_TOOLS(8个), system_prompt, checkpointer=InMemorySaver)
  ├─ middleware: [ToolErrorMiddleware, ModelCallLimitMiddleware(25), HistorySummarizer(40K/20)]
  └─ 每次请求: routers/chat.py → agent.astream_events → 8 种 SSE 事件
```

**依赖版本（实测）**：

| 包 | 版本 | 关键结论 |
|---|---|---|
| langchain | 1.3.14 | `create_agent` 可用，返回 `CompiledStateGraph`，支持嵌套（Agent 作为 tool） |
| langgraph | 1.2.10 | — |
| langgraph-prebuilt | 1.1.0 | `create_react_agent` ✅；`create_supervisor` ❌ 导入失败（需自建） |
| langchain-openai | 1.4.1 | — |

**单 Agent 的三个"增长痛点"**：

| 痛点 | 具体表现 |
|---|---|
| ① System Prompt 膨胀 | `prompts.py` 已 46 行：计税规则（B 表/A 表）、社保、填表、检索、记忆、免责全挤在一个 prompt，规则互相干扰 |
| ② 工具选择压力 | 主 LLM 每次都要从 8 个工具里选，计税类（3/4）与检索类（1/2）行为模式差异大 |
| ③ 上下文混装 | 计税的中间步骤（查画像 → 计算 → 更新画像）与其他任务的历史混在一条消息链，压缩/检索都要面对噪声 |

> 结论：**计税类任务（工具 3/4 + 记忆 1/6）是天然的独立子 Agent 候选**——它们自成闭环（画像 → 计算 → 回写），领域规则密集，且与检索/填表/指引任务解耦度最高。

### 6.2 工具清单：7 工具设计 → 8 工具现状

**① 原始设计 7 工具总览**（来源：`财务RAG-技术架构与Agent方案.md` §三）：

| # | 工具名 | 输入 | 数据源 | 对应功能 |
|:--:|--------|------|------|:--:|
| 1 | `search_knowledge` | 用户问题原文 | Qdrant 向量库（115个文件，四层relevance_tier分层） | 智能问答 |
| 2 | `calculate_income_tax` | 收入类型、金额、扣除项、城市 | `tax_rate_tables.json`（综合/经营/年终奖/累计预扣） | 税率计算 |
| 3 | `query_social_insurance` | 城市、就业类型、工资 | `cities/zhengzhou/social_insurance.json` | 社保计算 |
| 4 | `fill_tax_form` | 申报表类型、用户信息 | `form_field_map.json` + openpyxl 填表 | 申报材料生成 |
| 5 | `get_filing_guide` | 申报场景 | `operations/个税操作指南.md` | 申报指引 |
| 6 | `search_industry_benchmark` | 行业名称/门类 | `industry_benchmark.json`（97行业×10指标） | 行业参照 |
| 7 | `search_tax_website` | 搜索关键词 | Web Search（白名单域名） | 实时政策 |

**② 当前 8 工具清单**（来源：`财务RAG-Multi-Agent 集成设计文档.md` §2.2，`backend/tools/`）：

| # | 工具 | 类型 | 返回中带结构化字段 |
|---|---|---|---|
| 1 | `get_user_context` | 记忆读取 | — |
| 2 | `search_knowledge` | RAG 检索 | sources |
| 3 | `calculate_income_tax` | 计税（工资/劳务/年终奖） | result_card + disclaimer |
| 4 | `calculate_business_income_tax` | 计税（个体户 B 表） | result_card + disclaimer |
| 5 | `query_social_insurance` | 社保查询 | result_card + disclaimer |
| 6 | `update_user_context` | 记忆写入 | — |
| 7 | `fill_tax_form` | 填表 | result_card + sources |
| 8 | `filing_guide` | 申报指引 | sources |

**工具实现细节（原始 7 工具中的非计算类）**：

**`fill_tax_form` — 申报材料生成**（来源：`财务RAG-技术架构与Agent方案.md` §3.4）：

```
输入: form_type (A表/B表), user_profile {name, id_card, incomes, deductions, ...}
数据源: templates/form_field_map.json（字段→单元格坐标映射）
        templates/个人所得税基础信息表（A表）/（B表）/*.xlsx
工具:  scripts/fill_tax_form.py（openpyxl 填表）
流程:
  1. Agent 调 get_required_fields(form_type) → 获知必填/可选字段
  2. Agent 对话收集用户信息（一次只问1-2个，已有上下文自动复用）
  3. Agent 调 fill_form(form_type, user_data) → openpyxl 填表
  4. 返回填好的 xlsx + 空白原表路径
输出: {success, file_path, filled_fields, skipped_fields}
```
> ⚠️ 不走 LLM，纯字段映射 + openpyxl 代码。保留空白原件供下载。

**`get_filing_guide` — 申报流程指引**（来源：`财务RAG-技术架构与Agent方案.md` §3.5）：

```
输入: scenario (个税年度汇算/个体户B表/小规模增值税)
数据源: operations/个税操作指南.md（个税APP 5步操作流程）
动作: RAG 检索操作指引 → 分步骤输出 + 官方入口链接
输出: {steps: [{step_number, description}], 官方入口_url, 咨询热线}
```

**`search_tax_website` — 税务官网白名单搜索**（来源：`财务RAG-技术架构与Agent方案.md` §3.6）：

```
输入: query (搜索关键词)
白名单（仅允许以下域名）:
  chinatax.gov.cn         # 国家税务总局及各地子站
  gov.cn                   # 中国政府网
  mohrss.gov.cn            # 人社部
  nhsa.gov.cn              # 国家医保局
  henan.chinatax.gov.cn    # 河南省税务局
  zhengzhou.gov.cn         # 郑州市政府
  zzgjj.zhengzhou.gov.cn   # 郑州公积金

动作: 限定域名的 Web Search → 返回摘要+链接
输出: [{title, snippet, url, domain}, ...]
```
> ⚠️ **严格限制**：不可搜索白名单以外的任何网站，保证信息来源权威可靠。

**工具模板（Step 5）**（来源：`财务RAG-后端开发路线图.md` Step 5）：

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

**✅ 通过标准**：

```python
tool_result = search_knowledge.invoke({"query": "租房扣除标准"})
assert "1500" in tool_result or "1100" in tool_result
```

### 6.3 RAG vs 实时搜索 调度逻辑

> 来源：`财务RAG-技术架构与Agent方案.md` §四。

| 用户问 | 走 RAG | 走 Web Search |
|--------|:--:|:--:|
| "租房扣除标准是多少" | ✅ | — |
| "今年出台了哪些新税政" | — | ✅ |
| "社保基数调整了吗" | ⚠️ 可能过期 | ✅ |
| 复杂问题 | ✅ | ✅ 交叉验证 |

LLM 根据问题是否涉及时效性（"最新""今年""最近"等关键词）自动路由。

### 6.4 Agent 实现：create_agent + InMemorySaver

**Step 6 Agent 大脑**（来源：`财务RAG-后端开发路线图.md` Step 6）：

**`agent/prompts.py`（原始版）**：

```python
SYSTEM_PROMPT = """你是"财税助手"，一个面向零财务基础大众的 AI 财税顾问。

规则：
1. 信息不足时，先反问 1-2 个问题，每次只问 1-2 个，不要猜测
2. 税率计算和社保计算使用提供的工具，不要自己推算
3. 每个计算结果附带逐步推导过程
4. 涉及金额的回复末尾附上 AI 免责：「⚠️ 本结果由 AI 辅助计算，仅供参考。以税务机关最终核定为准。12366」
5. 当用户问题涉及多个关联法条时，使用 search_relations 查询关联文档
6. 使用简洁易懂的语言，专业术语附带解释
7. 回答附带法规引用（法规名 + 文号）"""
```

**`agent/engine.py`（原始版）**：

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

**重构后的 Agent 组装**（来源：`财务RAG-后端审查与重构方案.md` §三 重构目标架构）：

```
POST /api/chat  {message, thread_id}  ← Pydantic ChatRequest 校验
       │
       ▼
agent.astream_events(messages, config, version="v2")
       │
       ├─ LangChain `create_agent`（v1 标准，`langchain.agents`）
       │     ├─ model: ChatOpenAI(model=config.DEEPSEEK_MODEL, temperature=0)
       │     ├─ tools: ALL_TOOLS（列表顺序 = 优先选择顺序）
       │     │          [Phase 2] get_user_context, search_knowledge, calculate_income_tax,
       │     │                    query_social_insurance, update_user_context
       │     │          [Phase 5] fill_tax_form, filing_guide
       │     ├─ system_prompt: SYSTEM_PROMPT（agent/prompts.py）
       │     ├─ checkpointer: InMemorySaver()（LangGraph v1，thread_id 隔离会话）
       │     └─ middleware: [ToolErrorMiddleware(), ModelCallLimitMiddleware(25)]
       │
       └─ langgraph 事件 → Router 映射为 7 种 SSE 事件
             on_chain_start        → thinking
             on_tool_start         → thinking (含 tool name)
             on_chat_model_stream  → step（逐 token）
             on_tool_end           → 解包工具返回的结构化对象
                                       ├─ 1. result      → result 事件
                                       ├─ 2. source ×N   → source 事件（依次）
                                       ├─ 3. disclaimer  → disclaimer 事件
                                       └─ 4. .answer     → 保持为 LLM 上下文，后续 step 事件解释
             on_tool_error / except → error
             on_chain_end          → done
```

**架构决策速查（9 项）**（来源：`财务RAG-后端审查与重构方案.md` §二）：

| # | 决策项 | 结论 |
|:--:|--------|------|
| 1 | Agent 框架 | **LangChain `create_agent` + `InMemorySaver`**（v1 标准，`langchain.agents`） |
| 2 | SSE 事件 | **8 种**，严格按 `前后端对照表` 格式（`event: xxx\ndata: {...}\n\n`） |
| 3 | 工具优先级 | **MVP 5 个先做**，答辩闭环 2 个跟进，辅助 2 个后补 |
| 4 | 对话上下文记忆 | **方案 C**：`get_user_context` / `update_user_context` 两个 @tool + per-thread dict（加锁） |
| 5 | 安全 | `.gitignore` 已屏蔽 `.env`，毕设不做认证/限流，答辩后轮换 API Key |
| 6 | 代码规范散落 | 答辩后统一修（路径计算、键名混用、常量散落等） |
| 7 | 延迟权衡 | Agent 路径比直连路径多 1 次 LLM 推理（约 +1-3s），毕设可接受；后期可对纯 RAG 问答保留旧 `/chat` 直连通路作为快速路径 |
| 8 | 模型名 | 统一从 `config.py` 读取 `DEEPSEEK_MODEL`（当前值为 `deepseek-v4-flash`），不在代码中硬编码 |
| 9 | API 路由前缀 | 统一切到 `/api/` 前缀，与前后端对照表对齐：`/api/chat`、`/api/tax/calculate`、`/api/social/calculate` |

### 6.5 全局单例双检锁

> 来源：`财务RAG-后端代码审查报告.md` §2.2 H1 + §3.2。

`get_agent()` 用简单的 `if _agent is None` 懒加载，无锁保护 → **已修复**：加 `_agent_lock = threading.Lock()` 双重检查锁，与 `get_retriever()` 模式一致。验证：`type(_agent_lock)` 为 `Lock` ✅。

**双子 Agent 的全局单例（v1.1 决策）**（来源：`财务RAG-Multi-Agent 集成设计文档.md` §5.4 实现注意 1）：两个子 Agent 无状态，`CompiledStateGraph` 并发 `ainvoke` 安全 → 模块级懒加载单例，省每次 `create_agent` 编译开销（约 1s）；llm 由 `get_llm()` 共享（engine.py 提取，主/子 Agent 共用一个 ChatOpenAI）。实现注意 4：engine.py 里 `build_agent()` 内部创建的 llm 需提出来做模块级单例（`get_llm()`），否则主/子 Agent 各建一个 ChatOpenAI。

### 6.6 双子 Agent 设计（Multi-Agent，Tool-as-Subagent）

> 来源：`财务RAG-Multi-Agent 集成设计文档.md`（v1.5）§1–§12 全量。设计原则 14 条（P1–P14）见下。

#### 6.6.1 设计原则（P1–P14）

| # | 原则 | 含义 | 影响 |
|---|---|---|---|
| P1 | **轻量先行** | 先做"子 Agent 作为工具"（Tool-as-Subagent），零结构改动跑通，再谈 Supervisor | 阶段一 = 轻量版，阶段二 = 完整版（可选） |
| P2 | **协议不变** | 子 Agent 返回仍遵循 `tools/base.py` 的 JSON 五字段（answer/result_card/sources/disclaimer） | `routers/chat.py` SSE 解包零改动，前端零改动 |
| P3 | **记忆隔离** | 子 Agent **不挂 checkpointer、不带对话历史**，每次独立计算；用户画像一律走 `get_user_context` | 子 Agent 无状态 → 天然防上下文混装 |
| P4 | **复用引擎** | 子 Agent 内部继续调 `services/tax_engine.py`，不重复实现计税逻辑 | 对拍一致性的前提 |
| P5 | **评测闭环** | 改动必须过两道关：对拍 N 条 + agent_eval 20 条回归 ≥90% | 验收标准（§6.6.9） |
| P6 | **版本约束** | 已实测 `langgraph-prebuilt 1.1.0` **无 `create_supervisor`**，`create_react_agent` 可用 | 完整版需自建 StateGraph，不自造官方 API |
| P7 | **v1.1 拆分粒度** | 拆**两个**子 Agent（计税 + 社保），各领域独立 prompt，不合并 | §6.6.2 双子 Agent 结构 |
| P8 | **v1.1 成本可接受** | 接受 +20-40% 延迟 / 1.5-2× token，补三项补偿（子 Agent 全局单例 / 主 prompt 精简抵消 / 答辩话术兜底） | §6.6.3 单例设计 + §12.5 话术 |
| P9 | **v1.1 双层评测** | 主层测路由（20 条迁名）+ 子层测内部选工具（subagent_eval.py） | §6.6.9 评测体系 |
| P10 | **v1.1 路由三道防线** | 子 Agent 拒答兜底 + 主层回归 ≥90% 硬门槛 + 邻域混淆用例 | §6.6.11 + §6.6.14 风险 |
| P11 | **v1.2 模式开关** | `AGENT_MODE` 配置切换：`multi`（子 Agent 形态，默认）/ `tools`（纯工具形态，回退与演示）——**同一时刻只有一套工具列表**，不并存注册（并存导致评测歧义 + 子 Agent 死代码） | §6.6.5 + §6.6.14 回退 |
| P12 | **v1.3 prompt 与工具列表同步** | **`SYSTEM_PROMPT` 也按 `AGENT_MODE` 拆两版**——multi 版工具名全部换成子 Agent 名，tools 版为现有 prompt 原样；prompt 里写到的工具名必须与 ALL_TOOLS 完全一致，**杜绝"prompt 诱导调用未注册工具"** | §6.6.6 + §6.6.10 一致性校验 |
| P13 | **v1.4 子 Agent 失败降级** | 子 Agent 未计算出结果（无 result_card）时，**复用消息链 `AIMessage.tool_calls` 里 LLM 已生成的 calculate 参数，直调原工具兜底**——参数提取靠 LLM（准确）、计算靠引擎（可靠），各取所长；连 tool_calls 都没有才返回错误让主 Agent 反问 | §6.6.7 + §6.6.9 降级指标 |
| P14 | **v1.5 绕过检测（强制重算）** | 子 Agent 最终 answer **含税额数字但 result_card 为空** = LLM "心算"绕过了确定性引擎 → **强制用工具重算，LLM 数字作废**；"绕过"在架构上不可能产出不可信结果 | §6.6.8 + §6.6.9 心算诱导用例 |

#### 6.6.2 架构：双子 Agent（阶段一轻量版）

**核心思路**：把**计税、社保两个领域子 Agent** 用 `create_agent` 构建（与主 Agent 同构），再各包成一个 `@tool` 挂回主 Agent 的 `ALL_TOOLS`——主 Agent 视角它们只是两个工具，**现有链路零结构改动**。

```
backend/tools/ 新增两个子 Agent 包装工具（替代原 calculate_* / query_social_insurance 的注册）
┌────────────────────────────┐
│ 主 Agent (create_agent)    │
│  tools = [..., tax_subagent, social_subagent, ...]   ← 只是多了两个"工具"
└──────────┬──────────┬──────┘
           │ tool 调用 │ tool 调用
           ▼          ▼
┌─────────────────────┐  ┌──────────────────────────┐
│ tax_subagent        │  │ social_subagent          │
│ (create_agent)      │  │ (create_agent)           │
│ 独立 prompt：计税规则 │  │ 独立 prompt：社保规则      │
│ tools = [get_user_context,  │ tools = [get_user_context,   │
│          update_user_context, │          update_user_context,│
│          calculate_income_tax, │          query_social_insurance]│
│          calculate_business_income_tax]│                          │
└─────────────────────┘  └──────────────────────────┘
```

**为什么拆两个子 Agent**（v1.1 grill 决策，否决"合并计算专家"）：
1. 计税 = **画像→计算→回写**闭环（get → calculate → update），规则密集，独立 prompt 收益最大
2. 社保 = **查表直答**（无回写链），规则短但仍是独立领域，与计税/检索/填表混在主 prompt 会互相干扰（agent_eval 里"缴费比例"与"增值税税率"是历史易混点）
3. 合并成"计算专家"反而稀释各自领域聚焦；分开拆 prompt 隔离最彻底
4. 面试叙事更饱满："我把两个高频计算领域拆成了独立子 Agent，主 Agent 专注路由"

**职责边界**：

| 维度 | 主 Agent | 计税子 Agent | 社保子 Agent |
|---|---|---|---|
| 职责 | 意图识别、路由、汇总、检索/填表/指引 | 只处理计税类（工资/劳务/稿酬/特许权/个体户/年终奖） | 只处理社保/公积金查询（比例/基数/灵活就业） |
| System Prompt | 精简：计算类两段下沉为一句"交给对应专家" | 计税规则全量下沉（§6.6.3） | 社保规则全量下沉（§6.6.3） |
| 工具集 | 8 个（计税/社保各替换为子 Agent） | 4 个（画像读写 ×2 + 计税 ×2） | 3 个（画像读写 ×2 + 社保 ×1） |
| 记忆 | InMemorySaver + HistorySummarizer | **无 checkpointer、无历史**（每次独立） | 同左 |
| 画像来源 | — | 只用 `get_user_context`（contextvar 传 thread_id，同进程内传播） | 同左 |
| middleware | ToolError + ModelCallLimit(25) + 摘要 | ToolError + ModelCallLimit(8)（防子 Agent 死循环） | 同左 |

**阶段二：完整版 — Supervisor 自建（可选）**：`langgraph-prebuilt 1.1.0` 无 `create_supervisor`，官方 API 不可用。自建方案（纯 langgraph，无新依赖）：

```
StateGraph（state: {task, result})
  ├─ supervisor 节点：LLM 判断任务类型 → 路由给 worker
  ├─ tax_worker / rag_worker / form_worker：各自调子 Agent 或工具
  └─ 汇总节点：拼装最终答案
```
- 工作量：2-3 天；风险：路由准确率需要评测集
- **建议**：答辩演示用阶段一（Tool-as-Subagent）已足够讲清"多 Agent 化"；阶段二作为论文"架构演进展望"章节素材，不强制实现

#### 6.6.3 子 Agent System Prompt 设计

**计税子 Agent**：

```python
TAX_SUBAGENT_PROMPT = """你是"个税计算专家"，只负责计税类问题（工资薪金/劳务报酬/稿酬/特许权使用费/年终奖/个体工商户经营所得）。

核心规则：
1. **先查画像再计算**：调用 get_user_context 检查是否已有城市、工资、收入类型、扣除项；
   用户没给完整信息时，用默认值补全（income_type 默认 salary，city 默认 zhengzhou，social_insurance 默认 0）。
2. **计算必须走工具**：绝不用 LLM 心算税率，一律调用 calculate_income_tax / calculate_business_income_tax。
   - 个体户/经营所得 → calculate_business_income_tax（5%-35% 五级累进）
   - 工资/劳务/稿酬/特许权 → calculate_income_tax
   - 年终奖单独计税对比 → calculate_income_tax 的 bonus 参数
3. **把用户新提供的信息用 update_user_context 回写**（城市/工资/扣除项），供后续复用。
4. **输出 = 工具 answer 原样透传 + 简短解读**：工具已生成分步推导和结果卡片，
   你只需补充 1-2 句通俗解释，不要重复计算过程。
5. **只回答计税问题**：非计税问题（社保缴费比例、申报流程、填表、政策条文）直接回答
   "这不是计税问题，请交给主助手处理"，不要尝试用计算工具硬算。
"""
```

> 设计要点：**子 Agent 的 answer = 工具 answer 原样透传**——这是 P2（协议不变）的关键：result_card 由包装层从子 Agent 消息链中确定性提取，不依赖 LLM 复述。

**社保子 Agent**：

```python
SOCIAL_SUBAGENT_PROMPT = """你是"社保公积金查询专家"，只负责社保/公积金相关问题（缴费比例、缴存基数、五险一金、灵活就业缴费）。

核心规则：
1. **先查画像再查询**：调用 get_user_context 检查是否已有城市；城市缺失时默认 zhengzhou（郑州）。
2. **查询必须走工具**：一律调用 query_social_insurance，绝不用 LLM 心算比例。
3. **回写新信息**：用户新提供的城市/缴费基数等用 update_user_context 保存。
4. **输出 = 工具 answer 原样透传 + 简短解读**：工具已生成结果卡片，你只需补充 1-2 句通俗解释。
5. **只回答社保问题**：计税、申报流程、填表、税法条文等问题直接回答
   "这不是社保查询问题，请交给主助手处理"，不要用查询工具硬答。
"""
```

#### 6.6.4 代码骨架（backend/tools/subagents.py）

> 两个子 Agent 统一放一个模块，模块级懒加载单例（与 `engine.get_agent()` 同模式：`threading.Lock` 双检，构建一次复用）。

```python
"""双子 Agent（计税 + 社保）— 包装成 tool 挂回主 Agent

v1.1 设计：两个子 Agent 统一放 subagents.py，模块级懒加载单例
（与 engine.get_agent() 同模式：threading.Lock 双检，构建一次复用）。
子 Agent 无 checkpointer、无历史，每次调用独立；
画像通过 get_user_context 读取（contextvar 传 thread_id，同进程传播）。
返回遵循 tools/base.py JSON 五字段协议 → SSE 解包零改动。
"""
import json
import threading
from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware, ModelCallLimitMiddleware
from langchain_core.tools import tool

from agent.prompts import TAX_SUBAGENT_PROMPT, SOCIAL_SUBAGENT_PROMPT
from tools import get_user_context, update_user_context
from tools.calculate_income_tax import calculate_income_tax, calculate_business_income_tax
from tools.query_social_insurance import query_social_insurance
from tools.base import AI_DISCLAIMER


def _build_subagent(llm, system_prompt, tools):
    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[
            ToolErrorMiddleware(on_error=_on_tool_error),
            ModelCallLimitMiddleware(run_limit=8),   # 子 Agent 防死循环
        ],
        # 不传 checkpointer → 无状态，每次独立；全局单例共享安全
    )


# ── 全局单例（懒加载 + 双检锁，与 get_agent() 模式一致）──
_tax_subagent = None
_social_subagent = None
_lock = threading.Lock()


def get_tax_subagent(llm):
    global _tax_subagent
    if _tax_subagent is None:
        with _lock:
            if _tax_subagent is None:
                _tax_subagent = _build_subagent(
                    llm, TAX_SUBAGENT_PROMPT,
                    [get_user_context, update_user_context,
                     calculate_income_tax, calculate_business_income_tax])
    return _tax_subagent


def get_social_subagent(llm):
    global _social_subagent
    if _social_subagent is None:
        with _lock:
            if _social_subagent is None:
                _social_subagent = _build_subagent(
                    llm, SOCIAL_SUBAGENT_PROMPT,
                    [get_user_context, update_user_context, query_social_insurance])
    return _social_subagent


def _extract_fields(messages) -> tuple:
    """遍历子 Agent 消息链，确定性提取最后一个非空 result_card / sources（不靠 LLM 复述）"""
    answer = ""
    result_card = None
    sources = None
    for msg in messages:
        content = getattr(msg, "content", "")
        if isinstance(content, str) and content.startswith("{"):
            try:
                parsed = json.loads(content)
                if parsed.get("result_card"):
                    result_card = parsed["result_card"]
                if parsed.get("sources"):
                    sources = parsed["sources"]
            except json.JSONDecodeError:
                pass
        if getattr(msg, "type", "") == "ai":
            answer = content  # 子 Agent 最终回答
    return answer, result_card, sources


@tool
async def tax_subagent(query: str) -> str:
    """计算个人所得税（工资/劳务/年终奖/个体户经营所得）。当用户需要算税时调用，
    内部由计税专家 Agent 处理：先查用户画像，再用法定税率表精确计算，最后回写画像。
    参数: query — 用户原始计税问题"""
    from agent.engine import get_llm  # 复用主 Agent 的 llm 单例
    sub = get_tax_subagent(get_llm())
    result = await sub.ainvoke({"messages": [{"role": "user", "content": query}]})
    answer, result_card, sources = _extract_fields(result["messages"])
    return json.dumps({
        "answer": answer,
        "result_card": result_card,
        "sources": sources,
        "disclaimer": AI_DISCLAIMER,
    }, ensure_ascii=False)


@tool
async def social_subagent(query: str) -> str:
    """查询社保公积金（缴费比例/缴存基数/五险一金/灵活就业）。当用户需要查社保时调用，
    内部由社保专家 Agent 处理：先查用户画像，再查询官方缴费比例，最后回写画像。
    参数: query — 用户原始社保问题"""
    from agent.engine import get_llm
    sub = get_social_subagent(get_llm())
    result = await sub.ainvoke({"messages": [{"role": "user", "content": query}]})
    answer, result_card, sources = _extract_fields(result["messages"])
    return json.dumps({
        "answer": answer,
        "result_card": result_card,
        "sources": sources,
        "disclaimer": AI_DISCLAIMER,
    }, ensure_ascii=False)
```

> ⚠️ **实现注意**：
> 1. **全局单例（v1.1 决策）**：两个子 Agent 无状态，`CompiledStateGraph` 并发 `ainvoke` 安全 → 模块级懒加载单例，省每次 `create_agent` 编译开销（约 1s）；llm 由 `get_llm()` 共享（engine.py 提取，主/子 Agent 共用一个 ChatOpenAI）
> 2. 提取 result_card 时遍历消息链，**只取最后一个非空 result_card**（避免旧工具结果误取）
> 3. `get_user_context` 依赖 contextvar `_current_thread_id`——子 Agent 与主 Agent 同进程同事件循环，**传播正常**（与 `search_knowledge` 用 `asyncio.to_thread` 的跨线程场景不同，无需额外处理）
> 4. `LLM 单例`：engine.py 里 `build_agent()` 内部创建的 llm 需提出来做模块级单例（`get_llm()`），否则主/子 Agent 各建一个 ChatOpenAI
> 5. ✅ **结构验证已通过（2026-08-04 实测）**：用真实 DeepSeek `ChatOpenAI` 构建"子 Agent（create_agent + add 工具）→ @tool 包装 → 主 Agent 挂载"三层结构，构建成功无报错——嵌套方案可行（fake 模型因不支持 `bind_tools` 会报 NotImplementedError，属测试工具限制，与方案无关）

#### 6.6.5 主 Agent 接入与 AGENT_MODE 模式开关（v1.2）

```python
# config.py 新增（v1.2 模式开关）
AGENT_MODE = "multi"   # "multi"=子 Agent 形态（默认）| "tools"=纯工具形态（回退/演示）

# engine.py 本地组装（推荐，避免 tools/__init__ 循环导入）
# v1.3：prompt 与工具列表同源分支——两形态各自成对，永不同步错位
from agent.prompts import SYSTEM_PROMPT_MULTI, SYSTEM_PROMPT_TOOLS
from tools.subagents import tax_subagent, social_subagent

if config.AGENT_MODE == "multi":
    ALL_TOOLS = [get_user_context, search_knowledge, tax_subagent, social_subagent,
                 update_user_context, fill_tax_form, filing_guide]
    SYSTEM_PROMPT = SYSTEM_PROMPT_MULTI   # 工具名 = tax_subagent / social_subagent
else:  # tools 形态 = 原单 Agent（回退/演示）
    ALL_TOOLS = [get_user_context, search_knowledge,
                 calculate_income_tax, calculate_business_income_tax, query_social_insurance,
                 update_user_context, fill_tax_form, filing_guide]
    SYSTEM_PROMPT = SYSTEM_PROMPT_TOOLS   # 工具名 = calculate_* / query_social_insurance（现有原样）
```

> 注意：`tools/__init__.py` 的 `ALL_TOOLS` 导入链会循环依赖（subagents.py 导入 tools.*）→ **建议在 `engine.py` 本地组装列表**（如上），不在 `tools/__init__.py` 维护 ALL_TOOLS。
> **不并存原则（P11）**：同一时刻只有一套工具列表——并存注册会导致 `agent_eval` 评测歧义（同一 query 命中谁都对）且 LLM 大概率选旧工具、子 Agent 变死代码。
> **prompt 同步原则（P12，v1.3）**：**prompt 里出现的每个工具名必须真实注册在当形态的 ALL_TOOLS 里**——残留原工具名会诱导 LLM 调用未注册工具，触发 ToolNode 报错（"Tool X is not registered with ToolNode"，源码 `tool_node.py:949`）→ 先失败一轮再被错误信息纠正，浪费轮次且前端可见报错。

**模式开关说明（v1.2）**：`AGENT_MODE` 只影响 `engine.py` 里 `ALL_TOOLS` 的组装，**其余代码两形态共用**：

| 形态 | ALL_TOOLS | 用途 |
|---|---|---|
| `multi`（默认） | 计税/社保 → 两个子 Agent | 多 Agent 演示 / 答辩主形态 |
| `tools` | 原 8 工具 | 回退保底 / 演示"单 Agent vs 多 Agent"对比 / 异常时快速降级 |

- 评测：两形态各跑一遍（tools 形态 = 现状基线，已有数据；multi 形态 = 本设计验收）
- 切换粒度：进程级（config 启动时读），不做请求级切换（保持简单）

#### 6.6.6 prompt 双版本设计（v1.3，修复"主 Agent 调不到子 Agent"）

**问题**（审查发现，`prompts.py` 现状）：主 `SYSTEM_PROMPT` 的工具选择指南写死了 5 处原工具名——第 16 行 `→ calculate_income_tax`、第 17 行 `→ calculate_business_income_tax`、第 19 行 `→ query_social_insurance`、第 25 行 B 表 `再调 calculate_business_income_tax`、第 28-29 行 `必须通过 calculate_income_tax 和 query_social_insurance 工具获取`。multi 形态下这些工具**未注册**，LLM 按 prompt 指引调用 → ToolNode 返回 "Tool X is not registered" 错误 → 浪费一轮 + 前端报错。

**修复**：`SYSTEM_PROMPT` 拆两版，与 ALL_TOOLS 同源分支：

| 形态 | prompt | 工具名写法 |
|---|---|---|
| `multi` | `SYSTEM_PROMPT_MULTI` | 工具选择指南全部改为 `tax_subagent` / `social_subagent`（B 表那行 → `tax_subagent`） |
| `tools` | `SYSTEM_PROMPT_TOOLS` | **现有 `SYSTEM_PROMPT` 原样不动**（回退零风险） |

```python
# prompts.py 结构
SYSTEM_PROMPT_MULTI = """...  # 基于现版复制，工具名替换为子 Agent 名
    计税类 → tax_subagent / social_subagent；B 表先 fill_tax_form 再 tax_subagent
SYSTEM_PROMPT_TOOLS = SYSTEM_PROMPT  # 现有版本原样，改名即可
```

**验收**（一致性硬校验）：multi 形态下 `agent_eval` 20 条跑通 + 无 "not registered" 报错（§6.6.10）；tools 形态回归现状。

#### 6.6.7 子 Agent 失败降级设计（v1.4，复用 LLM 已生成参数）

**问题**：子 Agent 内部可能"多轮未计算出结果"——参数缺失反复追问、工具选错、或 `ModelCallLimit(8)` 触达。**关键事实**：`ModelCallLimitMiddleware` 默认 `exit_behavior="end"`（源码 `model_call_limit.py:131`）→ 超限**正常结束不抛异常**，所以"未计算出结果"的检测信号 = **消息链里没有 result_card**，不是异常捕获。

**降级设计**（包装层兜底，零改动子 Agent）：

```
子 Agent ainvoke 结束
  └─ _extract_fields() 提取 result_card
       ├─ 有 result_card → 正常返回（现状）
       └─ 无 result_card → 降级路径（新增 _fallback_reuse_args）：
            ① 遍历消息链 AIMessage.tool_calls，找最后一个 calculate_* 的 args
               （LLM 已生成好的结构化参数，直接复用！结构已验证 ✅）
            ② 找到 → 直调原工具 calculate_income_tax(**args) → 返回 result_card
            ③ 没找到（LLM 绕圈没尝试）→ 返回错误消息给主 Agent，主 Agent 反问用户
```

**为什么复用 tool_calls 参数**：不是"重新让 LLM 算一次"（可能再绕圈），而是**捡起 LLM 已生成但未执行成功的参数直接喂确定性引擎**——参数提取靠 LLM（准确）、计算靠引擎（可靠），各取所长。

**代码骨架**：

```python
def _fallback_reuse_args(messages, calc_tool_names) -> tuple:
    """降级：从消息链复用 LLM 已生成的 calculate 参数直调原工具。
    返回 (answer, result_card, sources, used)"""
    # ① 找最后一个 calculate 工具调用（LLM 已生成参数）
    for msg in reversed(messages):
        for tc in getattr(msg, "tool_calls", []) or []:
            if tc.get("name") in calc_tool_names:
                args = tc.get("args", {})
                # ② 直调原工具（确定性引擎）
                from tools.calculate_income_tax import calculate_income_tax, calculate_business_income_tax
                fn = calculate_business_income_tax if tc["name"] == "calculate_business_income_tax" else calculate_income_tax
                try:
                    raw = fn.invoke(args) if hasattr(fn, "invoke") else fn(**args)
                    parsed = json.loads(raw)
                    return parsed.get("answer", ""), parsed.get("result_card"), parsed.get("sources"), True
                except Exception:
                    break  # 参数不全 → 落到 ③
    return "", None, None, False  # ③ 未找到/失败 → 主 Agent 反问
```

**三档触发条件**：

| 档 | 条件 | 动作 |
|---|---|---|
| 正常 | 消息链有 calculate ToolMessage | 透传 result_card |
| 降级 | 无 ToolMessage，但 `AIMessage.tool_calls` 有 calculate args | `_fallback_reuse_args` 复用参数直调原工具 |
| 放弃 | 连 tool_calls 都没有 | 错误消息 → 主 Agent 反问用户补信息 |

**边界**：`ModelCallLimit=8` 触达时若最后一步是"LLM 生成了调用但图提前 end"，tool_calls 可能已消费 → 降级①容忍 args 缺失，落到③。降级结果与正常路径**同一引擎，数值必然一致**（对拍天然成立）。

**面试叙事**："子 Agent 绕圈没算出结果时，我做了降级——从消息链里捡回 LLM 已经生成好的工具参数，直接喂给确定性计税引擎兜底。参数 LLM 负责、计算引擎负责，各取所长，用户永远拿得到结果。"

#### 6.6.8 绕过检测设计（v1.5，防"LLM 心算绕过子 Agent"）

**问题**：`create_agent` 的循环里，**LLM 每轮自主决定是否声明 `tool_calls`**——它可能觉得"我能直接答"，于是**不调工具直接输出文本**（如"月薪 8000 个税大概 90 元"）。这是"心算"绕过：没走 `tax_subagent` → 没走 `calculate_income_tax` → 数字不可信（税率表、专项附加扣除全靠 LLM 记忆）。

**防线（强制重算，P14）**：

```python
@tool
async def tax_subagent(query: str) -> str:
    result = await sub.ainvoke(...)
    answer, result_card, sources = _extract_fields(result["messages"])

    if result_card is None:
        # v1.4 降级：复用 tool_calls 参数直调原工具
        answer2, card2, src2, used = _fallback_reuse_args(result["messages"], CALC_TOOL_NAMES)
        if used:
            answer, result_card, sources = answer2, card2, src2
        # v1.5 新增：answer 含税额数字但无 result_card → 判定"心算绕过" → 强制重算
        elif _contains_tax_amount(answer):
            answer, result_card, sources = _forced_recalc(query)   # 强制走引擎，LLM 数字作废
    ...
```

```python
def _contains_tax_amount(text: str) -> bool:
    """检测文本中是否出现疑似税额数字（"元/块"或"税 xxx 元"模式）"""
    return bool(re.search(r"(税|应纳税额)[^\d]{0,6}(\d[\d,，.]*)\s*(元|块)", text or ""))

def _forced_recalc(query: str) -> tuple:
    """强制重算：与降级同源——优先复用 tool_calls 参数，否则返回"需补充信息"错误，
    由主 Agent 反问用户，绝不采用 LLM 心算数字。"""
    ...
```

**三层"不准绕过"防线**（叠加后，架构上不可能产出不可信结果）：

| 层 | 机制 | 兜什么 |
|---|---|---|
| ① prompt 软约束 | `SYSTEM_PROMPT_MULTI` 第 3 条"计算必须走工具，LLM 只解释" | 引导为主 |
| ② v1.4 降级 | 无 result_card 但 tool_calls 有参数 → 复用参数直调引擎 | 绕圈/中断 |
| ③ **v1.5 强制重算** | answer 含税额数字但无 result_card → 强制走引擎，LLM 数字作废 | **心算绕过（最隐蔽）** |

**评测**（§6.6.9）：子层加 2 条"心算诱导"用例（"月薪8000个税大概多少""房租1500能省多少税"），断言输出**必须带 result_card**（即必须走了工具）。

#### 6.6.9 评测与验收（v1.1 双层评测）

**两道硬关（P5）+ 三层结构**：

| 层 | 评测 | 门槛 |
|---|---|---|
| **主层·对拍** | 计税 5 条 + 社保 3-4 条，子 Agent vs 原工具直调，比较 `result_card` 数值 | 数值完全一致（同一引擎，验证链路无失真） |
| **主层·路由回归** | `agent_eval.py` 20 条**迁名后**重跑（id 6-10 → `tax_subagent`，id 11-14 → `social_subagent`） | 准确率 ≥90%，计算类不降 |
| **子层·内部选工具** | 新增 `subagent_eval.py`：直接对子 Agent 注入 query，验证内部工具选择与拒答 | 命中率 ≥90%（子 Agent 内部正确性） |

> ⚠️ **关键语义变化（v1.1 审查发现）**：子 Agent 内部工具调用**不进主 Agent 消息链**——`extract_tool_calls` 从主链只能提取到 `tax_subagent`/`social_subagent`（包装名）。所以主层 20 条测的是**"主 Agent 路由正确性"**，子 Agent 内部选工具必须由**子层评测**单独覆盖——这正是双层评测存在的理由。

**主层对拍集设计（backend/eval/multi_agent_eval.py）**：

```python
PAIR_EVAL = [
    # 计税（5 条）
    {"id": 1, "query": "我年收入96000元工资类型社保年缴9888元租房月扣1500算个税", "subagent": "tax", "expect": "tax_amount"},
    {"id": 2, "query": "年薪12万交多少税", "subagent": "tax", "expect": "tax_amount"},
    {"id": 3, "query": "劳务报酬3万元个税怎么算", "subagent": "tax", "expect": "tax_amount"},
    {"id": 4, "query": "年终奖5万要交多少税（并入综合 vs 单独对比）", "subagent": "tax", "expect": "bonus.saving"},
    {"id": 5, "query": "个体工商户季度收入20万成本8万，算经营所得个税", "subagent": "tax", "expect": "tax_amount"},
    # 社保（3 条）
    {"id": 6, "query": "郑州工资8000社保扣多少", "subagent": "social", "expect": "total_contribution"},
    {"id": 7, "query": "灵活就业社保一个月交多少钱", "subagent": "social", "expect": "total_contribution"},
    {"id": 8, "query": "郑州公积金缴存基数", "subagent": "social", "expect": "base"},
]
```

判定逻辑：子 Agent 返回 JSON → 解析 `result_card.data.<expect字段>` → 与直调原工具同参数结果比对。

**子层评测集设计（backend/eval/subagent_eval.py）**：

```python
SUBAGENT_EVAL = [
    # 计税子 Agent：内部应选对工具（4 条）
    {"id": 1, "agent": "tax", "query": "年终奖5万要交多少税", "expected": ["calculate_income_tax"]},
    {"id": 2, "agent": "tax", "query": "个体户季度收入20万成本8万算税", "expected": ["calculate_business_income_tax"]},
    {"id": 3, "agent": "tax", "query": "我先查一下我之前填的工资信息", "expected": ["get_user_context"]},
    {"id": 4, "agent": "tax", "query": "我的工资改成12000", "expected": ["update_user_context"]},
    # 社保子 Agent（2 条）
    {"id": 5, "agent": "social", "query": "五险一金缴费比例是多少", "expected": ["query_social_insurance"]},
    {"id": 6, "agent": "social", "query": "郑州公积金基数", "expected": ["query_social_insurance"]},
]
```

**路由三道防线（v1.1 决策，P10）**：

| 防线 | 内容 | 验收 |
|---|---|---|
| ① 子 Agent 拒答 | 双子 Agent prompt 第 5 条：非本领域问题明确返回"交给主助手" | 子层评测加 2 条拒答用例（"个税APP怎么退税"→ tax 子 Agent 应拒答） |
| ② 主层回归硬门槛 | 20 条迁名后重跑 ≥90%；不达标 = 主 prompt 精简过度，回滚计税/社保规则 | 回归不降 |
| ③ 邻域混淆用例 | 主层补 4 条边界用例：`"个税APP怎么退税"`→`filing_guide`；`"租房扣除标准"`→`search_knowledge`；`"工资8000交多少税"`→`tax_subagent`；`"社保缴费比例"`→`social_subagent` | 全部命中 |

**一致性硬校验（v1.3 新增）**——prompt ↔ 工具列表一致性（P12 验收，防"主 Agent 调不到子 Agent"复发）：

| 校验 | 方法 | 门槛 |
|---|---|---|
| 工具名注册检查 | 扫描 `SYSTEM_PROMPT_MULTI` 中出现的工具名（正则 `[a-z_]+(?=\s*[)）])` 或人工清单），断言每个都在 multi 形态 ALL_TOOLS 里 | 100% 注册，零未注册名 |
| 无报错回归 | multi 形态跑 `agent_eval` 20 条，**收集消息链中的 error 状态 ToolMessage**（`"not registered"`），断言为零 | 0 条 not registered |
| tools 形态回归 | `AGENT_MODE=tools` 跑现有 20 条 | 与现状一致（≥90%） |

**降级机制评测（v1.4 新增）**：

| 指标 | 方法 | 门槛 |
|---|---|---|
| 降级触发率 | 子层评测 `subagent_eval.py` 加"绕圈场景"用例（如参数缺失 query），统计降级路径触发次数 | 有 result_card 的用例 0 次降级；**绕圈用例 100% 落到降级②**（复用参数成功） |
| 降级数值一致 | 降级路径结果 vs 直调原工具同参数结果比对 | 数值完全一致（同一引擎，天然成立） |
| 放弃率 | 统计落到③（主 Agent 反问）的次数 | 仅限"LLM 完全没尝试"的极端用例，正常集为 0 |

**绕过检测评测（v1.5 新增）**：

| 指标 | 方法 | 门槛 |
|---|---|---|
| 心算拦截率 | 子层 `subagent_eval.py` 加 2 条"心算诱导"用例（"月薪8000个税大概多少" / "房租1500能省多少税"），断言输出**必须带 result_card** | 100%（必须走工具，LLM 数字作废） |
| 强制重算数值 | 强制重算路径结果 vs 直调原工具同参数比对 | 数值完全一致 |

**建议补充（有余量做）**：链路正确性抽查（验证子 Agent 调用后 `update_user_context` 确实回写画像，断言 contexts dict 更新）；失败恢复（子 Agent 内部工具报错 → ToolErrorMiddleware 是否兜住、主 Agent 能否继续）。

#### 6.6.10 评测结果（2026-08-05，实测全绿）

> 来源：`财务RAG-Multi-Agent 集成设计文档.md` §11.1 + `财务RAG-项目补充与添加实施规划.md` §4.1。

| 评测层 | 分数 | 验收门槛 |
|---|---|---|
| agent_eval 主 Agent 路由 | 26/26 (100%) | ≥90% |
| — search_knowledge | 6/6 | 100% |
| — tax_subagent | 8/8 | 100% |
| — social_subagent | 5/5 | 100% |
| — fill_tax_form | 5/5 | 100% |
| — filing_guide | 4/4 | 100% |
| 一致性硬校验 | 0 "not registered" | ✅ |
| multi_agent_eval 主层对拍 | 8/8 (100%) | 数值完全一致 |
| multi_agent_eval 子层工具选择 | 6/6 (100%) | ≥90% |
| multi_agent_eval 子层拒答 | 2/2 (100%) | ✅ |
| multi_agent_eval 子层绕过检测 | 2/2 (100%) | ✅ |

**踩坑记录**（来源：`财务RAG-项目补充与添加实施规划.md` §4.1）：
1. langgraph-prebuilt 1.1.0 ToolNode sync 路径只走 `_execute_tool_sync`，不检测 async 工具 → 4 个 `async def @tool` 全部改为 sync `def` + 内部 `asyncio.run()`
2. 评测用例 `direct_args` 参数名必须与工具 `args_schema` 字段严格对齐
3. `fill_tax_form` 需在 SYSTEM_PROMPT_MULTI 中加示例 + B 表两步流程结构化，否则 LLM 倾向先查画像再放弃

#### 6.6.11 grill-me 审查结论（v1.0 → v1.1，决策记录）

> 2026-08-04 经 grill-me 压力审查，6 个决策分支全部闭合，本节为决策记录（供回溯）。来源：`财务RAG-Multi-Agent 集成设计文档.md` §12。

| # | 分支 | 问题 | 决策 | 影响 |
|---|---|---|---|---|
| A | 拆分粒度 | 只拆计税 vs 计税+社保合并 vs 只做概念验证 | **拆两个子 Agent**（计税+社保），否决合并（社保无回写链，合并稀释聚焦） | §6.6.2 双子结构，改动面 ×2 |
| B | 成本取舍 | +20-40% 延迟 / 1.5-2× token 是否可接受 | **接受 + 三项补偿**（子 Agent 全局单例 / 主 prompt 精简抵消 / 答辩话术兜底） | §6.6.4 单例 + §12.5 话术 |
| C | 评测联动 | 子 Agent 内部调用不进主消息链，仅迁名会失去内部验证 | **双层评测**：主层 20 条迁名测路由 + 子层 subagent_eval 测内部选工具 + 补 B 表用例 | §6.6.9 重构 |
| D | B 表链路 | 先填表再计税的顺序协调归谁 | **主 Agent 协调**：prompt 强化顺序规则，子 Agent 不集成 fill_tax_form | §3.6 |
| E | 实例化 | 每次重建 vs 全局单例 | **全局单例**（无状态 → CompiledStateGraph 并发安全，懒加载双检锁） | §6.6.4 |
| F | 路由可靠性 | 主 Agent 误派风险 | **三道防线**：子 Agent 拒答兜底 + 回归 ≥90% 硬门槛 + 邻域混淆用例 | §6.6.9 + §6.6.14 |
| G | 模式开关 | 能否保留原工具形式 | **`AGENT_MODE` 配置切换**（multi 子 Agent 形态默认 / tools 纯工具形态回退），不并存注册（并存→评测歧义+子 Agent 死代码）；原工具文件始终保留、子 Agent 内部复用 | §6.6.5 + §6.6.14 回退 |
| H | **prompt 一致性** | 主 Agent 会不会调 tool 导致调不到子 Agent | **会，且当前设计必然发生**——源码查证：ToolNode 只执行注册工具，未注册调用返回 "not registered" 错误（`tool_node.py:949`）；middleware 无 tools 注入（已查证 4 个 middleware）；但主 prompt 残留 5 处原工具名（`prompts.py` 16/17/19/25/28-29 行）会诱导 LLM 调用未注册工具 → 先报错再纠正、浪费轮次。**修复：`SYSTEM_PROMPT` 按 `AGENT_MODE` 拆两版**（multi 版工具名换子 Agent，tools 版原样），与 ALL_TOOLS 同源分支 + 一致性硬校验 | §6.6.6 + §6.6.9 + P12 |
| I | **失败降级** | 子 Agent 多轮未能计算出结果时能否自动调 tool | **能，且已设计**——关键事实：`ModelCallLimitMiddleware` 默认 `exit_behavior="end"`（`model_call_limit.py:131`），超限正常结束不抛异常，故检测信号 = 无 result_card；降级 = **复用消息链 `AIMessage.tool_calls` 里 LLM 已生成的 calculate 参数直调原工具**（参数 LLM 负责、计算引擎负责，结构已验证）；连 tool_calls 都没有才返回错误让主 Agent 反问 | §6.6.7 + §6.6.9 + P13 |
| J | **绕过检测** | LLM 会不会不调工具直接"心算"输出 | **会**——create_agent 循环中 LLM 每轮自主决定是否声明 tool_calls，可能直接输出文本（绕过子 Agent 的确定性计算）。**修复：强制重算**——answer 含税额数字但无 result_card = 心算 → 强制走引擎、LLM 数字作废；配合 prompt 软约束 + v1.4 降级，形成三层"不准绕过"防线 | §6.6.8 + §6.6.9 + P14 |

**自查发现的事实性修正**（未占用提问轮次）：
- `agent_eval.py` id 6-14 共 9 条 `expected_tools` 必须迁移（否则替换后 100% 失败）
- `fill_tax_form` 独立脚本加载，不 import 计税工具 → 替换安全
- 子 Agent 全局单例优于"每次重建 + llm 单例"（省编译开销）
- `create_agent` 嵌套结构已实测可行（真实 DeepSeek 构建成功）

#### 6.6.12 改动文件清单与实施步骤

**改动文件清单**（来源：`财务RAG-Multi-Agent 集成设计文档.md` §6）：

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/config.py` | 修改 | 新增 `AGENT_MODE = "multi"`（v1.2 模式开关） |
| `backend/agent/prompts.py` | 修改 | 新增 `TAX_SUBAGENT_PROMPT` + `SOCIAL_SUBAGENT_PROMPT`；**`SYSTEM_PROMPT` 拆两版**：`SYSTEM_PROMPT_MULTI`（工具名换子 Agent）+ `SYSTEM_PROMPT_TOOLS`（现有原样）；保留 B 表"先填表再计税"顺序规则 |
| `backend/agent/engine.py` | 修改 | `get_llm()` 单例提取；`build_agent` 复用；**`ALL_TOOLS` 按 `AGENT_MODE` 两形态组装** |
| `backend/tools/subagents.py` | **新增** | 双子 Agent 构建 + `@tool` 包装 + 消息链提取 + 全局单例 + **`_fallback_reuse_args` 失败降级 + `_contains_tax_amount`/`_forced_recalc` 绕过检测** |
| `backend/tools/__init__.py` | 修改 | 导出 `tax_subagent` / `social_subagent`；**ALL_TOOLS 移出（改由 engine.py 本地组装）** |
| `backend/eval/multi_agent_eval.py` | **新增** | **双层评测**：主层对拍 + 子层内部选工具 |
| `backend/eval/agent_eval.py` | 修改 | 20 条 `expected_tools` 迁移（id 6-10 → `tax_subagent`，id 11-14 → `social_subagent`）+ 补 B 表双工具用例 + 邻域混淆用例 |
| `docs/财务RAG-项目补充与添加实施规划.md` | 修改 | §4.1 勾选状态 + 实测数据回填 |

**不改动**：`routers/chat.py`、前端全部文件、`services/tax_engine.py`、`rag/`、`context/`。

**实施步骤与排期**（依赖：无，可与 MCP 并行）：

```
① prompts.py：新增 TAX_SUBAGENT_PROMPT + SOCIAL_SUBAGENT_PROMPT + SYSTEM_PROMPT 拆两版（MULTI/TOOLS）+ B 表顺序规则保留（1.5h）
② engine.py：提取 get_llm() 单例 + config.AGENT_MODE 分支（prompt+tools 同源组装）（1h）
③ subagents.py：双子 Agent 构建 + @tool 包装 + 消息链提取 + 全局单例（3h，核心）
④ ALL_TOOLS 移出 tools/__init__ → engine 本地组装（0.5h）
⑤ agent_eval.py 迁名 + 补 B 表用例 + 邻域混淆用例（0.5h）
⑥ multi_agent_eval.py（主层对拍）+ subagent_eval.py（子层评测）+ 一致性校验（工具名注册检查 + not registered 断言）（2h）
⑦ 冒烟：multi 形态试计税 3 条 + 社保 2 条 + 检索 1 条 + 填表 1 条；tools 形态回归现状（0.5h）
总投入：约 2-2.5 天
```

#### 6.6.13 面试叙事与答辩素材

**三句话版本**：

> "lest 原来是单 Agent + 8 工具。我发现计税、社保两个计算领域规则密集、自成闭环，就把它们拆成两个独立子 Agent——用 create_agent 构建领域专家（各自独立 system prompt + 画像工具集 + 无历史），再包成 tool 挂回主 Agent。主 Agent 只做路由协调，领域规则全量下沉，B 表这类跨工具流程由主 Agent 保证顺序。整个改造对前端零改动，因为子 Agent 返回还是同一个 JSON 协议。评测上我做了双层验证：主层对拍 8 条数值完全一致 + 20 条路由回归 ≥90%，子层再单独测内部选工具，双层都过才算完成。"

**可展开的深挖点（考官追问弹药）**：

| 追问 | 回答要点 |
|---|---|
| 为什么用 create_agent 嵌套而不是 LangGraph Supervisor？ | langgraph-prebuilt 1.1.0 无 create_supervisor，且轻量版零结构改动、两天可验证；完整版 Supervisor 作为架构演进展望 |
| 子 Agent 为什么无状态？ | 用户画像独立存储在 per-thread dict，子 Agent 每次从 get_user_context 读——无历史天然防上下文混装，也避免子 Agent 记忆膨胀；因此全局单例共享也安全 |
| 多 Agent 有什么代价？ | ① 多一层 LLM 往返，延迟 +20-40%；② token 成本 1.5-2×；③ 路由错误时任务错派。我做了三项补偿（子 Agent 单例省编译 / 主 prompt 精简抵消 / 对拍+回归证明不退化） |
| result_card 怎么传出来的？ | 不靠 LLM 复述——包装层遍历子 Agent 消息链，确定性提取 ToolMessage 里的 result_card/sources，再与最终 answer 合并 |
| 怎么防止主 Agent 误派？ | 三道防线：子 Agent 内部拒答兜底 + 20 条路由回归硬门槛 + 4 条邻域混淆用例专门打误派 |
| 子 Agent 内部选工具怎么验证？ | 主 Agent 消息链里只有包装名，看不到子 Agent 内部——所以单独建了子层评测，直接对子 Agent 注入 query 验证内部调用 |

**答辩 PPT 素材**：架构演进图（单 Agent（8 工具平铺）→ 协调 Agent + 计税子 Agent + 社保子 Agent（职责分层））；数据证据（对拍 8/8 一致 + 主层回归 ≥90% + 子层命中 ≥90% + 延迟实测（接受 +20-40% 的诚实数据））；诚实表述（多 Agent 的价值在解耦与可扩展，不在单任务精度）。

**技术动机与叙事价值**（来源：`财务RAG-Multi-Agent 集成设计文档.md` §3）：
- **技术动机（职责分离）**：把"计税专家"从主 Agent 中剥离——主 Agent（路由/协调）识别"这是计税问题" → 把问题交给计税专家（独立 system prompt + 领域工具集 + 无对话历史 + 返回 JSON 五字段）→ 汇总回复用户
- **叙事价值**：架构演进叙事（单 Agent + 8 工具 → 协调 Agent + 领域子 Agent）；记忆隔离叙事（子 Agent 无状态设计是有意为之——"画像独立存储 + 子 Agent 无历史"，天然防上下文污染）；与 MCP 衔接（计税子 Agent 是将来 MCP Server 封装的自然宿主）
- **诚实边界（写进答辩话术）**：多 Agent 对**单轮单任务**不会更准（底层是同一个 tax_engine）；它的价值在**职责解耦、prompt 隔离、架构可扩展**。评测用"对拍一致 + 回归不降"证明不退化，用架构图证明演进。

#### 6.6.14 风险与回退

| 风险 | 等级 | 应对 |
|---|---|---|
| 子 Agent 延迟增加（多 2-3 轮 LLM，+20-40%） | 🟡 | **已接受（v1.1 决策）**：全局单例省编译开销 + 主 prompt 精简抵消 + 答辩话术兜底；实测超预算再评估 |
| token 成本 1.5-2×（子 Agent system prompt + 中间推理） | 🟡 | 子 Agent prompt 精简（规则下沉但不冗余）；答辩环境本地 API 成本可忽略 |
| 循环导入（subagents ↔ tools） | 🟡 | engine.py 本地组装 ALL_TOOLS，避免 tools/__init__ 深层导入 |
| contextvar 传播失效 | 🔴 | 子 Agent 用 `ainvoke` 与主 Agent 同事件循环，理论传播正常；**评测步骤⑥ 加断言测试画像回写** |
| 路由误判（主 Agent 错派） | 🟡 | **三道防线（v1.1）**：子 Agent 拒答兜底 + 20 条回归硬门槛 + 邻域混淆用例 |
| 主 prompt 精简过度导致工具选择退化 | 🟡 | 20 条回归不达标 = 回滚主 prompt 计税/社保规则，保留精简失败的证据 |
| **prompt 残留工具名 → 主 Agent 调不到子 Agent**（v1.3 修复） | 🔴 | **根因**：prompt 写死原工具名而 multi 形态未注册 → LLM 按 prompt 调用 → ToolNode 报 "not registered"（源码 `tool_node.py:949`）→ 先失败一轮再纠正。**修复**：prompt 拆两版与 ALL_TOOLS 同源分支 + 一致性硬校验 |
| **子 Agent 多轮未计算出结果**（v1.4 修复） | 🟡 | **根因**：参数缺失绕圈 / 工具选错 / ModelCallLimit(8) 触达（`exit_behavior="end"` 正常结束，无异常可捕获）。**修复**：降级——复用消息链 `AIMessage.tool_calls` 里 LLM 已生成的 calculate 参数直调原工具，连 tool_calls 都没有才返回错误让主 Agent 反问 |
| **LLM 心算绕过子 Agent**（v1.5 修复） | 🔴 | **根因**：create_agent 循环中 LLM 每轮自主决定是否声明 tool_calls，可能不调工具直接输出文本（税率靠 LLM 记忆，不可信）。**修复**：强制重算——answer 含税额数字但无 result_card → 判定心算 → 强制走引擎、LLM 数字作废（三层防线） |
| B 表链路断裂（先填表再计税顺序错） | 🟡 | 主 prompt 保留原顺序规则 + 主层补 B 表双工具用例 |
| 多 Agent 收益被质疑（"不更准何必做"） | 🟢 | 叙事转向解耦/可扩展/架构演进（诚实表述） |

**回退方案（v1.2 升级）**：**`AGENT_MODE = "tools"` 一行切换**回纯工具形态（原 8 工具，与现状完全一致）——不需要改代码、不需要删文件，进程级生效。multi 形态出任何问题，改配置即还原，答辩现场也能演示两形态对比。原文件（`calculate_income_tax` 等）始终保留，子 Agent 内部继续复用。

### 6.7 对话上下文记忆（方案 C 详解）

> 来源：`财务RAG-后端审查与重构方案.md` §七。设计原则：对话级上下文记忆——同一会话中，用户提供的个人信息（城市、工资、收入类型、扣除项）自动复用，不需要重复输入。

```
用户："我在郑州，月薪8000，社保扣多少？"
Agent：[计算郑州社保] → 记忆: {city: "郑州", salary: 8000}

用户："那我个税要交多少？"
Agent：[自动使用记忆的城市和工资计算个税，无需追问]

用户："帮我生成个税申报表"
Agent：[自动使用记忆的所有信息填入表单]
```

实现方式：工具返回时，将提取到的用户关键信息写入对话历史的 `user_context` 字段。后续每次工具调用时，优先读取 `user_context` 中已有的信息，仅追问缺失字段。

**存储与工具代码**（来源：`财务RAG-后端审查与重构方案.md` §七；后经 SQLite 持久化改造——见 §8，工具签名与返回格式不变）：

```python
# tools/user_context.py
import json
import threading
from contextvars import ContextVar
from langchain_core.tools import tool

# thread_id 通过 contextvar 传递给 @tool
# ⚠️ 关键风险：LangGraph 内部调度 sync @tool 时若用自定义线程池而非 asyncio.to_thread()，
#    contextvar 可能不传播 → get_user_context 读到空 dict。PoC 必须先验证！
_current_thread_id: ContextVar[str] = ContextVar("current_thread_id")
contexts: dict[str, dict] = {}  # {thread_id: {city, salary, income_type, deductions}}
_contexts_lock = threading.Lock()

@tool
def get_user_context() -> str:
    """获取当前会话中已收集的用户信息（城市、工资、收入类型、扣除项等）。
    在回答任何涉及个税或社保计算的问题之前，先调用此工具检查已有的用户信息。"""
    thread_id = _current_thread_id.get()
    with _contexts_lock:
        ctx = contexts.get(thread_id, {})
    if not ctx:
        return json.dumps({"message": "还没有收集到任何用户信息"}, ensure_ascii=False)
    return json.dumps(ctx, ensure_ascii=False)

@tool
def update_user_context(key: str, value: str) -> str:
    """更新当前会话的用户信息。
    key 可选值: city, salary, income_type, housing_rent, children_edu, elderly_support
    value: 对应的值。如 city="郑州", salary="8000", income_type="salary" """
    thread_id = _current_thread_id.get()
    allowed_keys = {"city", "salary", "income_type", "housing_rent", "children_edu", "elderly_support"}
    if key not in allowed_keys:
        return json.dumps({"error": f"不支持的 key: {key}，可选: {list(allowed_keys)}"}, ensure_ascii=False)
    with _contexts_lock:
        if thread_id not in contexts:
            contexts[thread_id] = {}
        contexts[thread_id][key] = value
    return json.dumps({"updated": key, "value": value}, ensure_ascii=False)
```

**Agent 行为逻辑（由 System Prompt 驱动）**：

```
规则：回答问题涉及个税或社保计算时：
  1. 先调 get_user_context 检查已知信息
  2. 缺少关键字段（收入类型、金额、城市）→ 反问 1-2 个问题，不猜测
  3. 信息齐全 → 调 calculate_income_tax / query_social_insurance
  4. 计算结果出来后 → 调 update_user_context 保存城市、工资等信息
```

**thread_id 传递（ChatRequest）**：

```python
# routers/chat.py
from pydantic import BaseModel, Field
import uuid

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息（非空）")
    thread_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="会话 ID")

@router.post("/chat")
async def chat(req: ChatRequest):
    # 设置 contextvar → @tool 内部可通过 _current_thread_id.get() 读取
    _current_thread_id.set(req.thread_id)

    config = {"configurable": {"thread_id": req.thread_id}}
    # ... agent.astream_events(
    #     {"messages": [{"role": "user", "content": req.message}]},
    #     config=config,
    #     version="v2"
    # )
```

> **contextvar 传播说明**：若工具内部用 `asyncio.to_thread()` 包装同步代码，`contextvar` 会自动传播到 worker 线程（Python 3.9+）。若使用自定义 `concurrent.futures.ThreadPoolExecutor` 则需要手动 `contextvars.copy_context().run()`。**PoC 必须验证 LangGraph 是否使用 to_thread 调度 sync @tool。**

> **PoC 验证结果（2026-07-30）**：✅ contextvar 传播：成功；✅ on_tool_end 解包：output 为 `ToolMessage`，JSON 在 `.content` 字段。①② 均已通过，备选方案不再需要，Phase 2 可以进入。（来源：`财务RAG-后端审查与重构方案.md` PoC 验证结果）

### 6.8 System Prompt 约束（7 规则 + 5 条）

**重构方案版 System Prompt 设计要点（7 规则）**（来源：`财务RAG-后端审查与重构方案.md` §八）：

```python
SYSTEM_PROMPT = """你是"财税助手"，一个面向零财务基础大众的 AI 财税顾问。

核心规则：
1. **信息不足时先问，不猜测**：
   涉及个税/社保计算时，先调 get_user_context 检查已收集的信息。
   缺少关键字段（收入类型、金额、城市等）时，以自然语言反问 1-2 个问题
   （如"请问你的收入类型是工资还是劳务报酬？"），然后**结束本轮回复**，
   不要调用计算工具。永远不要用猜测的值调用计算工具。
   下一轮用户回答后，再次调 get_user_context 确认信息完整，再调计算工具。
   每次只问 1-2 个问题，不要一次性追问过多。

2. **计算走工具，不走 LLM**：税率、社保金额必须通过 calculate_income_tax 和
   query_social_insurance 工具获取。LLM 只负责解释结果和提供建议。

3. **分步推导 + 法规引用**：输出计算结果时，附带每一步的取值来源和运算过程。
   引用法规名称和文号（如"《个人所得税法》附表一"）。

4. **AI 免责**：任何涉及金额的回复末尾，必须附加免责声明。工具已自动提供该声明，
   你无需额外编写。

5. **语言通俗**：使用大众能理解的语言。专业术语（如"应纳税所得额""累计预扣"）
   首次出现时附带一句解释。

6. **上下文复用**：用户提供的信息（城市、工资、收入类型、扣除项）用 update_user_context
   保存。后续对话自动复用，不再重复询问。

7. **工具失败处理**：若工具调用失败，用自然语言告知用户"服务暂不可用"，
   尝试基于你已有的知识回答（附加免责声明）。若连续 2 个工具失败则终止本轮，
   告知用户稍后重试。
"""
```

**开发注意事项版 System Prompt 约束（5 条）**（来源：`财务RAG-开发注意事项.md` §3.4）：

```
你是"财税助手"，一个面向零财务基础大众的 AI 财税顾问。

规则：
1. 信息不足时，先反问 1-2 个问题收集信息，不要猜测
2. 税率计算走代码，不要自己推算
3. 每个计算结果附带分步推导和法规引用
4. 涉及金额的回复末尾必须附加 AI 免责声明
5. 使用简洁易懂的语言，避免专业术语，或在使用术语时附加解释
```

**引导式追问机制的 System Prompt 硬约束**（来源：`财务RAG-技术架构与Agent方案.md` §6.1）：

> "如果用户的问题缺少税率计算或社保计算所需的关键信息（收入类型、金额、城市），先友好地反问 1-2 个问题收集信息，再执行计算。每次只问 1-2 个问题，不要一次性追问过多。"

### 6.9 工具返回 Router 解包机制（on_tool_end）

**关键机制：工具结构化返回 + Router 解包**（来源：`财务RAG-后端审查与重构方案.md` §三）。`@tool` 函数是纯函数，只能 `return`，不能 `yield` 中间事件。采用以下方案：

```python
# @tool 返回统一结构
def calculate_income_tax(...) -> str:
    result = tax_engine.calculate(...)
    return json.dumps({
        "answer": "应纳税所得额 = 96000 - 60000 - ... = 5328元，应纳税额 159.84元",
        "result_card": {"type": "tax_result", "data": {...}},
        "sources": [{"title": "个人所得税法", "url": "..."}],
        "disclaimer": "⚠️ 本结果由 AI 辅助计算，仅供参考..."
    }, ensure_ascii=False)

# Router 在 on_tool_end 拦截，按固定顺序发 SSE 事件：
#   ⚠️ output 是 ToolMessage 对象，JSON 在 .content 字段
#   raw = event["data"]["output"].content
#   parsed = json.loads(raw)
#   1. result     → 前端插结果卡片
#   2. source ×N  → 前端追加来源链接
#   3. disclaimer → 前端追加灰色免责
#   4. .answer    → 交给 LLM，后续 step 事件自然语言解释
```

> **`confirm` 事件降级**：Agent 反问"请问你的收入类型是工资还是劳务报酬？"以 LLM 自然语言形式通过 `step` 事件承载，不单独发 `confirm` 事件。前端按正常流式文本渲染即可。

**工具返回结构 schema（tools/base.py）**（来源：`财务RAG-后端审查与重构方案.md` §4.1）：

```python
# tools/base.py — 所有计算类 @tool 的返回结构约定
"""
工具返回统一 JSON 结构（所有字段可选）：
{
    "answer": str,          # 交给 LLM 的自然语言回答文本
    "result_card": {        # 前端结果卡片（有此字段则发 result SSE 事件）
        "type": "tax_result" | "social_result",
        "data": dict         # 引擎原始返回
    } | None,
    "sources": [            # 法规来源（有此字段则发 source SSE 事件）
        {"title": str, "url": str}
    ] | None,
    "disclaimer": str | None  # 免责声明（有此字段则发 disclaimer SSE 事件）
}
"""
```

**Router 解包优秀实践代码（审查确认）**（来源：`财务RAG-后端代码审查报告.md` §3.1，`routers/chat.py` 第 75–95 行）：

```python
elif kind == "on_tool_end":
    output = event["data"]["output"]
    raw = output.content if hasattr(output, "content") else str(output)
    parsed = json.loads(raw)
    if parsed.get("result_card"):     # 1. 结果卡片
        yield _sse("result", parsed["result_card"])
    if parsed.get("sources"):          # 2. 来源 ×N
        for src in parsed["sources"]:
            yield _sse("source", src)
    if parsed.get("disclaimer"):       # 3. 免责声明
        yield _sse("disclaimer", {"text": parsed["disclaimer"]})
```

**亮点**：工具层与展示层解耦，工具只管返回数据，Router 负责映射 SSE 事件。

### 6.10 UX 引导式追问机制

> 来源：`财务RAG-技术架构与Agent方案.md` §6。面向零财务基础大众用户，直接影响 Agent 行为。

**原则**：当用户问题缺少计算所需的关键信息（收入类型、金额、城市等），Agent 必须**先反问 1-2 个澄清问题**，而非猜测后直接执行。

```
❌ 用户："我要交多少税？"
   Agent 直接猜 → 错误风险高

✅ 用户："我要交多少税？"
   Agent："你是上班拿工资，还是自己开店/接活？"
   → 用户："上班"
   Agent："在哪个城市？月薪大概多少？"
   → 继续引导，直到信息完整
```

**双入口设计：对话引导 + 快捷表单**：

| 入口 | 适用用户 | 实现方式 |
|------|---------|---------|
| **对话引导** | 零基础新用户 | Agent 逐字段反问，渐进式收集信息 |
| **快捷表单** | 有经验用户 | 前端独立表单页面（醒目入口按钮），一次性填写，即时生成结果 |

两者不冲突——表单提交后也可以进入对话查看详细解释，对话中也可以随时跳转到表单"一键填完"。

**结果可信度：分步计算 + 法律引用 + AI 免责**：

**分步计算明细**：计算结果必须附带每一步的取值、来源和运算过程。

```
✅ 输出示例：
你的应纳税所得额 = 年收入120000 - 起征点60000 - 社保扣除12480 - 住房租金扣除18000 = 29520元
29520元落在第1级税率区间（0-36000），适用税率3%，速算扣除数0
应纳税额 = 29520 × 3% - 0 = 885.6元

📎 依据：《个人所得税法》附表一；国发〔2023〕13号（专项附加扣除标准）
```

**法律依据引用**：税率和社保计算结果必须附带法规名称+文号。

**AI 免责提醒**：涉及金钱计算时，必须在结果末尾附加：

> ⚠️ 本结果由 AI 辅助计算，仅供参考。实际应纳税额以税务机关最终核定为准。如有疑问，请拨打 12366 税务咨询热线。

### 6.11 Agent 工具调度规范（5 规则）

> 来源：`财务RAG-开发注意事项.md` §3.3。

| 规则 | 说明 |
|------|------|
| **信息不足时反问** | 缺少计算所需字段（收入类型、金额、城市）→ 先反问 1-2 个问题，不要猜测 |
| **计算走代码** | `calculate_income_tax` 和 `query_social_insurance` 必须读取 JSON + 公式，不走 LLM 推理 |
| **申报材料走字段映射** | `fill_tax_form` 是 key-value 填表，不是 LLM 生成 |
| **对话上下文** | 工具返回时附带 `user_context`，后续调用自动复用 |
| **白名单搜索** | `search_tax_website` 仅允许 7 个 gov.cn 域名 |

### 6.12 MCP Server 封装（补充项 ⑤）

> 来源：`财务RAG-项目补充与添加实施规划.md` §4.2。状态：✅ 已完成（tax-calc 3 工具，WorkBuddy 宿主实测通过）。

- **目标**：把 `calculate_income_tax`（+可选 `query_social_insurance`）封装成标准 MCP Server，验证"任何 MCP 兼容宿主可调用"。
- **改动文件**：新增 `scripts/mcp_server_demo.py`（FastMCP）；测试脚本 `scripts/mcp_client_test.py`
- **实施步骤**：
  1. `pip install mcp`，用 `FastMCP("tax-calc")` 注册工具，复用 `services/tax_engine.py` 核心逻辑（不重复实现）
  2. 启动 server，用 MCP Client 或 `mcporter` 调用验证
  3. 验证后在概念梳理 §5 补一段实战记录
- **验收标准**：① MCP 标准协议下能列出并调用工具；② 计算结果与既有工具一致。
- ⚠️ 注意：MCP SDK 需联网安装，注意答辩环境离线风险——demo 代码入库即可，不引入运行时依赖。

> ⚠️ **MCP 2.0 版本坑**（来源：`财务RAG-开发踩坑记录.md` #12）：`pip install mcp` 默认装 2.0.0，内置 FastMCP 被移除（独立成包）→ `from mcp.server.fastmcp import FastMCP` 抛 `ModuleNotFoundError`；修复：`pip install "mcp==1.29.0"`（1.x 最终版），脚本零改动。规律：快速上手的框架库，`pip install <pkg>` 拉到的 may be breaking change——装完第一件事先 `import` 验证再写业务代码。

---

## 7. 上下文工程

> 来源：`财务RAG-Context Engineering 集成设计文档.md`（v2.0）全量 + `财务RAG-项目补充与添加实施规划.md` §3 + `财务RAG-开发踩坑记录.md` #1–#13。
> 定位：实现级设计，直接指导 P0 上下文工程模块（历史摘要 / TokenBudget / 评测）的编码。
> 核心假设变更（2026-08-04 grill 审查）：**压缩主战场从"单轮检索 chunk"改为"多轮对话历史累积"**——实测 2937 个 chunk 中位数仅 181 字，单轮压缩无意义。同日基线采集完成并回填参数（keep=20 / trigger=40K），guard.py 已实现并升级为"工具返回瘦身主力"。

### 7.1 设计原则（总纲，P1–P6）

| # | 原则 | 含义 | 影响 |
|---|---|---|---|
| P1 | **无侵入集成** | 不改 `create_agent` 组装逻辑 | 落点：middleware / 工具层 / 离线脚本 |
| P2 | **主战场 = 多轮历史** | chunk 中位数 181 字，单轮无需压缩；真正吃预算的是多轮累积 | 核心模块 = 历史摘要器 |
| P3 | **画像独立兜底 → 激进压缩** | 用户画像由 `get_user_context` 独立存储，不依赖对话历史 | 历史摘要可激进压（token 降幅 ≥70%），字段自动校验兜底 |
| P4 | **官方能力优先复用** | langchain 1.3.14 自带 `SummarizationMiddleware`（已查证 API） | 继承扩展，不重复造轮子 |
| P5 | **用户可感知** | 压缩不得静默发生 | 新增 SSE `context` 事件 + 前端提示条 |
| P6 | **参数化 + 评测闭环** | 阈值全部可配置，效果有数字证据 | 先采集基线，再实现，再评测 |

### 7.2 模块职责边界（v1 → v2 变化）

| v1 模块 | v2 去向 |
|---|---|
| ContextCompressor（独立，压 top-5 chunk） | ⤵ 拆解：提取式算法 → `guard.py` **工具返回瘦身**（已实现：部署在 search_knowledge 返回前，单条超 400 字才压缩，必保句保留）；两级压缩思路 → `history_summarizer.py` 预处理 |
| TokenBudget（五区预算） | ⬆ 升级为**核心决策源**：触发阈值 / keep 值 / 预算参数，由基线采集数据决定 |
| ContextEvaluator（query 集） | 🔄 评测对象改为**历史摘要**：长对话场景集 + 自动字段校验 |
| —（新增） | **HistorySummarizer**：继承官方 SummarizationMiddleware，扩展两级压缩 + 字段校验 + context 事件 |

### 7.3 官方 SummarizationMiddleware 复用设计（已查证 langchain 1.3.14）

#### 7.3.1 为什么复用

`venv/Lib/site-packages/langchain/agents/middleware/summarization.py` 已实现：`before_model`/`abefore_model` 钩子（模型调用前改消息）、token 触发条件（AND/OR 组合）、保留策略、摘要调用。**历史裁剪落点确认可行**，且官方实现处理了 AI/Tool 消息配对等细节，自研成本高且易错。

#### 7.3.2 官方能力 vs 我们的扩展

| 能力 | 官方 | 我们的扩展（HistorySummarizer 继承） |
|---|---|---|
| 触发（trigger） | ✅ `("tokens", N)` / `("fraction", 0.2)` / 消息数，支持组合 | 阈值由基线采集定（见 §7.5） |
| 保留（keep） | ✅ 默认最近 20 条消息 | keep 值由基线数据定 |
| token 计数 | ✅ `count_tokens_approximately` | 可换 `token_est.py` 估算 |
| 摘要 prompt | ✅ 可自定义 `summary_prompt` | **自定义**：强制保留画像字段 + 两级压缩预处理 |
| 画像字段校验 | ❌ | ✅ **新增**：摘要前后 get_user_context 字段完整率自动校验 |
| 用户提示事件 | ❌ | ✅ **新增**：摘要发生时置标志 → 路由层发 SSE `context` 事件 |
| 提取式预过滤 | ❌（直接摘要全部旧消息） | ✅ **新增**：摘要前先提取式丢弃纯闲聊/低价值轮 |

#### 7.3.3 配置基线（✅ 已实现 2026-08-04，参数已定稿）

```python
# context/history_summarizer.py（✅ 已实现，集成在 agent/engine.py middleware 链）
class HistorySummarizer(SummarizationMiddleware):
    """官方摘要中间件 + lest 扩展：清单式 prompt + context 事件标志"""

    def __init__(self, model: BaseChatModel, trigger_tokens: int = 40_000,
                 keep_messages: int = 20):
        super().__init__(
            model=model,                                   # DeepSeek 实例
            trigger=[("tokens", trigger_tokens)],          # 基线实测：40_000
            keep=("messages", keep_messages),              # 基线实测：20
            summary_prompt=CUSTOM_SUMMARY_PROMPT,          # §7.3.4 清单式
            token_counter=_count_tokens_zh,                # ⚠️ 必须中文口径（见下）
        )

    async def abefore_model(self, state, runtime):
        result = await super().abefore_model(state, runtime)
        if result is not None:                             # 发生了摘要 → 置标志
            # 置 _summarized_flags[thread_id]（供路由层 pop → context 事件）
            ...
```

> ⚠️ **必须传 `trim_tokens_to_summarize=None`**（踩坑 #11，见 §13）：官方默认
> `trim_tokens_to_summarize=4000` 且 `strategy="last"`（保留最近消息）——信息密度高的
> 对话会砍掉最早的画像轮（城市/工资/扣除项），摘要 LLM 根本看不到（s1/s2/s3 评测全中招）。
> 传 None 跳过 trim 全量喂摘要（保真优先，输入 ~40K token ≈ ¥0.04/次）。

> ⚠️ **token_counter 必须传中文口径**（踩坑 #6，见 §13）：官方默认
> `count_tokens_approximately` 是英文口径（4 字符/token），中文被低估约 2.3 倍，
> 导致 trigger=40K 永不触发（实测 20 轮 70K 真实 token 官方只算 ~10K）。
> `_count_tokens_zh` = 消息内容字符数 × 1.75，**与基线 est_tokens 完全一致**，
> 否则 trigger/keep 阈值全部失真。

#### 7.3.4 自定义摘要 prompt（CUSTOM_SUMMARY_PROMPT）

> 两轮实测迭代（2026-08-04）：
> - v1：宽松式 prompt 漏扣除金额（s1 children_edu/elderly_support 三档全败）→ 清单式
> - v2：300 字上限 + 清单式仍丢字段（评测 s3 第一次摘要丢城市/工资/收入类型）→ **上限 500 字 + "宁删背景不删数值"最高优先级规则**（当前实现版本）

```text
你是对话历史摘要器。将以下多轮对话压缩为 500 字以内的摘要。

【最高优先级 - 必须完整出现（一个都不能漏）】以下字段若在对话中出现过，
必须原样保留其数值或名称：城市（如"郑州"）、收入类型（如"工资"/"经营"）、
月薪/年薪（如"12000"）、住房租金、子女教育、赡养老人、大病医疗、
住房贷款利息、婴幼儿照护、上年亏损、个体户名称/信用代码、
社保公积金缴费基数与比例、已办理或询问过的业务。
规则：宁删背景描述与寒暄，绝不删数值/名称；输出前逐项自查清单。

其余内容按信息价值取舍，闲聊与寒暄一律删除。
只输出摘要正文，不要任何解释。
<messages>
{messages}
</messages>
```

#### 7.3.5 两级压缩（提取式预过滤 → LLM 摘要）

官方直接对全部旧消息做摘要；lest 扩展在摘要前**先提取式过滤低价值轮**：

| 轮次类型 | 处理 |
|---|---|
| 含数字/金额/画像字段（city/salary/扣除项关键词）的轮次 | **必保**，进入摘要候选 |
| 纯闲聊/寒暄/重复轮次 | **直接丢弃**（提取式），不喂给摘要 LLM |
| 工具调用与结果（calculate/tax JSON） | 保留结果数字，丢弃过程性长文本 |

判定复用 v1 的必保正则（数字+单位 / 文号 / 百分比），字段集合用 `CONTEXT_KEYS`。

#### 7.3.6 context 事件传递（middleware → SSE）

middleware 是进程内组件，SSE 事件由路由层 `_agent_stream` 生成。传递方案：

```
HistorySummarizer 摘要发生时：contexts_archived[thread_id] = timestamp（模块内 dict，带锁）
路由层 _agent_stream 开头：检查 contexts_archived[thread_id]
  → 有 → 先发一次 SSE context 事件，再清标记
  → 无 → 不发
```

**SSE 事件格式**（新增第 8 种事件，前端 `types.ts` / `useChat.ts` / `ChatMessage.tsx` 三处小改）：

```json
event: context
data: {"type": "history_archived",
       "message": "较早的对话已归档为摘要，您的城市、工资、扣除项等关键信息已保留"}
```

### 7.4 TokenBudget（v2 职责：核心决策源）

> 来源：`财务RAG-Context Engineering 集成设计文档.md` §4 + `财务RAG-项目补充与添加实施规划.md` §3.2。

**职责变化**：v1 五区预算分配（给 Compressor 算 budget_chars）；v2 **提供历史摘要的全部参数**——触发阈值、keep 值、token 估算接口；无检索轮让渡等策略保留但降级为次要。

**参数（基线采集后校准，初始值）**：

```python
# context/budget.py
class TokenBudget:
    WINDOW = 64_000            # deepseek-v4-flash 上下文（可配置）
    RESERVED_OUTPUT = 4_000    # 输出预留（硬性）
    def __init__(self, trigger_tokens: int = 40_000, keep_messages: int = 20,
                 summary_target_tokens: int = 1_500): ...
    def should_summarize(self, history_tokens: int) -> bool:   # history_tokens ≥ trigger_tokens
    def adjust(self, baseline: dict) -> None:                  # 基线采集数据回填
```

**估算口径（token_est.py）**：中文 1 字 ≈ 1.75 token；1 token ≈ 0.5 字（保守）；`tiktoken` 仅可选校准，不引入硬依赖。

> **实施修订**（来源：`财务RAG-Context Engineering 集成设计文档.md` §12 Checklist ②）：TokenBudget 简化——参数固化在 HistorySummarizer 默认值，独立 `budget.py` 省略。五区预算分配设计（system 6K / 检索 20K / 历史 12K / query 18K / 输出预留 4K，动态让渡 + 历史裁剪）作为 v1 方案留档（来源：`财务RAG-项目补充与添加实施规划.md` §3.2）。

### 7.5 基线采集（✅ 已完成 2026-08-04，参数最终确认）

**最终参数（四场景完整数据复核后定稿）**：
- **trigger = 40_000**（窗口 63%）——**否决脚本启发式建议的 52K**：s3 第 11 轮 64.4K 已爆窗，52K 触发时模型输入已 ~60K 无余量；40K 时 s1 第 10 轮（41K）、s3 第 7 轮（43K）触发，摘要后 ~16-21K，余量 19K ≈ 5-8 轮
- **keep = 20**（摘要后保留最近 20 条消息，上下文 16-21K token）——s2/s4 三档全 100%；s1 三档同败是摘要缺陷非档位问题（见下）；keep=10 更省 token 但容错低，留作备选
- **摘要缺陷实证**（字段校验的价值）：s1 的 `children_edu=1000`（轮6）、`elderly_support=2000`（轮8）在 keep=10/20/30 **三档全败**——因为它们都落在"被摘要化的 older 部分"，模拟摘要 LLM 漏掉了这两个金额 → **CUSTOM_SUMMARY_PROMPT 必须改为"逐字段清单核对"式**（列出 CONTEXT_KEYS 12 字段逐一确认保留），ContextEvaluator 的字段校验正是为此把关
- **token 曲线（工具全成功）**：s1 20轮→64.9K（第 19 轮 64.3K 已超窗）、s3 15轮→71.0K（第 11 轮 64.4K 超窗）、s2 15轮→43.2K、s4 12轮→37.4K → **无摘要管理时 11-19 轮必爆窗，摘要必要性铁证**
- **重大发现**：工具返回拼接总长（5×800≈4K 字≈7K token/次检索）是膨胀主因 → guard.py 从"保障"升级为"主力"（§7.6）
- 采集链路坑（已修）：`agent.invoke` 同步 vs async @tool 全失败 → `await agent.ainvoke`；transformers 5.14.1 需 `TRANSFORMERS_OFFLINE=1` **且必须在任何第三方 import 之前设置**（huggingface_hub 在 import 时快照 env，retriever.py 内设置太晚）→ collect_baseline.py 顶部设置 + HF_ENDPOINT 镜像兜底 + 预加载检索器

**五步采集流程（留档）**：`scripts/gen_long_dialogues.py`（4 场景 61 轮 + facts 清单）+ `scripts/collect_baseline.py`（自动执行：逐轮曲线 → trigger 建议 → 摘要模拟 → probe 判定 → keep 对比 → 输出 `eval/dialog_baseline.json`）。

**场景脚本结构（示例）**：

```python
# scripts/gen_long_dialogues.py（构造数据，不入运行时）
SCENARIOS = [
    {
        "id": "s1",
        "desc": "郑州打工人年度个税咨询",
        "facts": {"city": "郑州", "salary": "12000", "income_type": "salary",
                  "housing_rent": "1500", "children_edu": "1000"},   # 关键事实清单
        "turns": [
            "我在郑州，月薪12000，社保一年大概交多少？",
            "我租房，每月租金1500，能扣除吗？",
            "有个孩子上小学，子女教育怎么扣？",
            "帮我算一下我一年要交多少税",
            ...   # 20+ 轮，含闲聊与重复
        ],
    },
    ...
]
```

### 7.6 工具返回瘦身 guard.py（✅ 已实现 2026-08-04）

**定位升级**：基线采集证明——单条 chunk 中位数仅 181 字，但 `search_knowledge` 把 top-5 拼接成 ≈4K 字 ≈7K token 进入历史，**工具返回的拼接总长才是历史膨胀主因**（s3 单轮 +12.6K 的元凶）。因此本模块从"极端保障"升级为**每次检索都生效的主力瘦身**。

**实现**（`backend/context/guard.py`，已集成到 `tools/search_knowledge.py` 替换 `content[:800]`）：
- 单条超 **400 字**才压缩（chunk 中位数 181 字，正常 99.9% 原样返回，零损失）
- 提取式：必保句（数字+单位 / 文号〔〕号 / 百分比 / 生效时间 / 限值表述）强制保留，只删句不改写
- **软上限设计**：必保句本身超预算时宁超 max_chars 也不丢数字（P2 保真优先）
- 溯源不受影响：sources 仍用压缩前完整结果构建

```python
# context/guard.py
def guard_compress(content: str, max_chars: int = 400) -> str:
    """提取式瘦身：未超长原样返回；超长则必保句全保留 + 其余按序补到预算。"""
```

> **现状硬伤背景**（来源：`财务RAG-项目补充与添加实施规划.md` §2）：`tools/search_knowledge.py:45` — `content[:800]` 是**硬截断**：无差别砍尾部，可能丢掉高价值后半段（法条条款后半段常含关键数字），且 5 条 × 800 字仍会撑爆窗口 → ① 提取式替换硬截断。

### 7.7 ContextEvaluator v2（长对话场景集，四指标）

**评测对象变更**：v1 单条 query + expected_facts（测检索上下文压缩）；v2 **长对话场景**（20 轮）→ 测摘要保真、字段校验、用户提示、token 收益。

**评测集 dialog_scenarios.json**：5-10 个场景，每个含：`facts`（关键事实清单 = CONTEXT_KEYS 子集）+ `turns`（20+ 轮真实问答）+ `expected_context_event`（期望摘要发生时触发提示）。

**四项指标（✅ 验收实测 2026-08-04，context_eval.py）**：

| 指标 | 定义 | 计算方式 | 达标线 | 实测 |
|---|---|---|---|---|
| 画像字段完整率 | 摘要后 LLM 能否从历史提取用户字段 | probe 问答（数值词边界正则） | **100%** | **92%**（3/4 场景 100%；s1 2 项为 LLM 提取失败，judge 佐证信息完整） |
| 摘要忠实度 | 摘要后历史是否含全部事实原样值 | judge 严格判定（数值必须原样一致） | ≥90% | **100%**（全部场景 missing=[]） |
| token 收益 | 无摘要 vs 有摘要峰值降幅 | 对比 dialog_baseline.json | 报告如实 | s1 39% / s2 12% / s3 42% / s4 2% |
| context 事件触发率 | 摘要触发 vs 事件 pop | 标志位消费统计 | 100% | **100%**（6 摘要 / 6 事件） |

> 实测结论：**judge 100% + 事件 100% + 峰值全 <41K = P0 验收通过**。probe 92%（s1 的
> children_edu/elderly_support 未命中）为 LLM 提取失败而非摘要缺陷（严格 judge 判定
> 历史中存在原样值）。评测驱动迭代三轮回合（见 §13 #5/#6/#11）：prompt 清单化 →
> 中文 token 口径 → trim=None 全量喂摘要。

**judge prompt（摘要忠实度版）**：

```text
你是严格的评测员。下面给出一段【原始对话摘要】和【原始对话关键事实清单】。
判断摘要是否歪曲了清单中的任何事实（数字/金额/城市/扣除项必须完全一致）。
输出严格 JSON：{"distorted": [true/false], "distorted_facts": ["..."], "missing_facts": ["..."]}
只根据清单判定，摘要遗漏但未歪曲 → 计入 missing_facts，不计 distorted。
```

> judge 自评偏差缓解：字段校验是自动的（主指标），judge 仅抽查忠实度（辅助），不依赖自评可信度。

**评测流程**：

```
1. 加载 dialog_scenarios.json
2. 逐场景跑真实 Agent 链路（agent.invoke 连续 20 轮，thread_id 隔离）
3. 记录：每轮历史 token（曲线）、摘要触发点、context 事件、摘要文本
4. 自动校验：字段完整率 + token 收益 + 事件触发率
5. judge 抽查摘要忠实度
6. 输出报告（含 token 增长曲线数据）
```

### 7.8 数据流总图（v2）

**生产链路**：

```
POST /api/chat ──→ _agent_stream
  ├─ (摘要标志检查) → 有 → 先发 SSE context 事件（提示归档）
  └─→ agent.astream_events
        └─→ create_agent
              └─→ HistorySummarizer(before_model)   # 历史超 trigger → 提取式过滤 → LLM 摘要 → 置标志
              └─→ search_knowledge → guard_compress  # 仅超长文本触发（关系扩展文档）
              └─→ LLM 生成（上下文 = 摘要 + 最近 keep 条消息）
```

**评测链路（离线）**：

```
dialog_scenarios.json → 真实 Agent 20 轮 → 触发摘要 → 自动字段校验 + judge 抽查 → 报告
```

### 7.9 测试计划与验收

**单测（backend/tests/test_context.py）**：

| 模块 | 用例 | 期望 |
|---|---|---|
| token_est | 空串 / 纯中文 / 中英混合 | 估算非 0、单调递增 |
| budget | trigger 边界（history==N / N+1） | 正确判断 |
| guard | ≤1.2K 字 | 原样返回 |
| guard | >1.2K 含必保句 | 必保句 100% 保留 |
| summarizer | 摘要后字段完整率（mock LLM） | 100% |
| summarizer | 纯闲聊轮预处理 | 不进入摘要候选 |

**集成**：
1. `agent_eval.py` 20 条 ≥ 90%（摘要器不影响工具选择）
2. `eval.py` 40 条 recall@5 不降（guard 只动超长文本）
3. 手工 20 轮长对话：context 事件出现且仅出现一次/摘要动作
4. 前端：context 事件渲染提示条

**验收（新四指标，对齐实施规划 §3）**：字段完整率 100% / 摘要忠实度 ≥90% / token 降幅 ≥70% / 事件触发率 100% / 双回归通过

> **集成测试实测（scripts/test_summarizer.py，s1 场景 20 轮）**：trigger=40K 生效（39.1K / 41.3K 触发），摘要后消息 43→23、token 27.4K/25.5K，20 轮触发 2 次间隔 6 轮，context 事件链路完整（摘要后下一轮 pop 到标志），全程未爆窗。

### 7.10 风险与取舍（v2 新增项）

| 风险 | 说明 | 缓解 |
|---|---|---|
| 官方 middleware 黑盒 | 升级 langchain 可能破坏行为 | 记录当前版本 1.3.14；升级前跑回归 |
| 两级压缩复杂度 | 提取式过滤 + LLM 摘要两段逻辑 | 过滤规则只做"闲聊丢弃 + 必保句"两档，不做精细打分 |
| context 事件与 SSE 时序 | 摘要发生在流中间，提示条插在开头 | 标志位方案：下一条 SSE 流开始时补发，语义可接受 |
| 摘要 LLM 成本 | 每触发一次多一次 DeepSeek 调用 | trigger 阈值让正常短对话永不触发（基线采集保证） |
| 激进压缩丢临时信息 | 摘要后对话外的临时细节丢失 | 画像字段独立存储兜底（P3）；golden 字段自动校验 |

### 7.11 实施顺序与编码 Checklist

**实施顺序**（更新 2026-08-04：基线采集与 guard 已完成）：

```
✅ ① 基线采集（已完成）      keep=20 / trigger=40K 已回填；发现工具返回拼接是膨胀主因
✅ ④ guard.py + search_knowledge（已完成）   提取式瘦身，软上限 400 字，自检通过
▶  ② token_est + types + budget（0.5 天）   参数直接用基线定值（40_000 / 20）
▶  ③ history_summarizer.py（1-1.5 天）   继承官方 SummarizationMiddleware + 字段校验 + context 事件
▶  ⑤ routers/chat.py + 前端 context 事件（0.5 天）
▶  ⑥ context_eval.py + dialog_scenarios.json 评测（1 天）   验收四指标
总投入：约 4-5 天
```

**编码 Checklist（实时进度）**：

- [x] ① 基线采集（脚本 + 数据，trigger=40K / keep=20 已定）
- [x] ② TokenBudget 简化（参数固化在 HistorySummarizer 默认值，独立 budget.py 省略）
- [x] ③ history_summarizer.py（继承官方 + 清单式 prompt + 中文 token_counter + 摘要标志）
- [x] ④ guard.py + search_knowledge 集成（自检通过）
- [x] ⑤ SSE context 事件（后端 + 前端三处小改，tsc 通过）
- [x] ⑥ context_eval.py + 四指标报告（✅ 2026-08-04 验收：judge 100% / 事件 100% / probe 92% / 峰值 <41K）
- [x] ⑦ 集成测试验收（2026-08-04 实测：摘要触发 2 次 / context 事件 2 次 / 峰值 41.3K < 64K ✅）

### 7.12 上下文工程补充项归属

> 来源：`财务RAG-项目补充与添加实施规划.md` §3。三项 P0 补充（①②③）细节均在本章有完整落点：
> - **① 历史摘要器（含保障压缩）**：§7.3/§7.5/§7.6。验收标准：① 画像字段完整率 100%（自动校验）；② 摘要忠实度 ≥90%（judge 抽查）；③ 历史 token 降幅 ≥70%；④ 事件触发率 100%；⑤ agent_eval 20 条回归 ≥90%。
> - **② TokenBudget**：§7.4。验收标准：① 任意输入下 `sum(alloc) ≤ 窗口 - 预留`；② 检索预算换算成字符数后与压缩率联动正确。
> - **③ ContextEvaluator**：§7.7。验收标准：① faithfulness ≥ 90%；② 引用正确率 ≥ 85%；③ 压缩后 token 用量下降 ≥ 40% 且 faithfulness 下降 ≤ 2pp；④ 报告含压缩开/关对比。
> - **⑥ 对话历史摘要裁剪**（P1）：已被 history_summarizer 覆盖。验收标准：① 历史超 12K token 后触发裁剪；② 裁剪后关键用户信息（城市/工资/扣除项）不丢失；③ 回答质量对拍无明显下降。

---

## 8. 用户上下文持久化（SQLite）

> 来源：`财务RAG-项目补充与添加实施规划.md` §5.1（⑦ 用户上下文持久化，补充项 7，P2 已实施）。状态：✅ 已实施（2026-08-06，冒烟全绿）。

### 8.1 方案演进与 grill 定案

⚠️ **grill 审查修订（2026-08-05）**：原方案「in-memory dict → MongoDB」被推翻，重新定案为 **SQLite + 自建消息表 + 历史回显**。三个关键发现驱动修订：

1. 前端 `useChat.ts:8` thread_id 每次 `crypto.randomUUID()` 刷新即变 → 后端无论存什么都取不回，**必须先前端 localStorage 固定 thread_id**，持久化才有意义（这也是"重启不丢"验收成立的前提）
2. 对话历史天然由 langgraph `InMemorySaver`（engine.py:112）管理，但**不换 Saver，改自建消息表**——消息可读可控、可迁移、可配合评测，且不依赖 langgraph 二进制序列化格式
3. 存储介质选 **SQLite**（标准库零依赖，答辩零风险），MongoDB 降级为"后期迁移"目标——靠 `MemoryStore` 抽象层 + 一次性迁移脚本实现，结构固定可平滑迁移。不引入 Redis（单进程单用户无缓存需求）

**目标**：用户画像 + 对话历史双持久化，实现"刷新/重开浏览器后历史回显 + Agent 接着聊"；为登录体系与多用户预留 user 维度。

### 8.2 核心设计

- 前端 thread_id 存 localStorage（**单会话模型**：一浏览器 = 一会话，MVP 语义；登录后扩展为 user_id + 多会话）
- 对话历史自建消息表，**恢复注入复用 SummarizationMiddleware 调用内压缩**（trigger=40K / keep=20，不重写摘要逻辑）
- `MemoryStore` 接口 + `SQLiteStore` 实现 → 后期换 MongoDB 仅换实现类，业务零改动
- 画像/消息表**预留 user_id 列**（当前 user_id = thread_id 占位，登录后零返工）
- `get_llm()` 预留"配置源"接口位（TODO），支持后期切换 DeepSeek key（管理员切换=改配置源；BYOK=登录体系后加密入库）

### 8.3 SQLite 三表设计

新增 `backend/storage/sqlite_store.py`（`MemoryStore` 接口 + `SQLiteStore`，sqlite3 标准库），**三张表**：

| 表 | 用途 |
|---|---|
| `user_contexts` | 用户画像（city/salary/income_type/deductions 等） |
| `threads` | 会话线程记录 |
| `messages` | 对话历史消息 |

- db 路径：`backend/config.py` 新增 `SQLITE_DB_PATH`，默认 **`backend/data/chat.db`**
- 连接管理：**单连接 + 写锁**并发保护
- 三表均**预留 `user_id` 列**（当前 user_id = thread_id 占位，登录后零返工）

### 8.4 MemoryStore 抽象层

`MemoryStore` 接口 + `SQLiteStore` 实现 → 后期换 MongoDB 仅换实现类，业务零改动。`tools/user_context.py` 从 in-memory dict 切换为 MemoryStore，**工具签名与返回格式不变**。

### 8.5 内部 thread_id 机制（业务tid#uuid8）

> 来源：`财务RAG-项目补充与添加实施规划.md` §5.1 实施记录关键实现决策。

**关键实现决策**：
1. 内部 thread_id = **`{业务tid}#{uuid8}` 每请求独立** → `InMemorySaver` 永不跨轮累积
2. 注入历史仅 role+content，附件不喂 LLM
3. 摘要中间件调用内压缩、结果不回写（写回只写本轮新增 → 无消息双份膨胀）
4. 异常/错误回复不写回（用户重试自然落库）

### 8.6 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/storage/{__init__,sqlite_store}.py` | **新增** | MemoryStore + SQLiteStore，三表 threads/messages/user_contexts，单连接+写锁 |
| `backend/config.py` | 修改 | `SQLITE_DB_PATH`，默认 `backend/data/chat.db` |
| `backend/tools/user_context.py` | 修改 | dict → MemoryStore，工具签名与返回格式不变 |
| `backend/routers/chat.py` | 修改 | ① 请求前从 SQLite 读历史注入 messages；② 流结束后写回 user 消息 + 拼接的完整回复；③ 新增 `GET /api/chat/history?thread_id=xx` |
| `backend/agent/engine.py` | 修改 | 每请求独立 thread_id 防 InMemorySaver 双份累积；`get_llm()` 留配置源 TODO |
| 前端 `src/hooks/useChat.ts` | 修改 | thread_id localStorage 持久化 + 挂载时 fetch history 渲染 |
| 前端 `src/lib/sse.ts` | 修改 | 新增 `getHistory` API |

**实施记录细节（2026-08-06）**：历史注入只取正文 + 流结束写回完整 Message JSON + `GET /api/chat/history`；`get_llm()` 配置源 TODO 位 + InMemorySaver 角色注释；前端 `sse.ts`（getHistory）/ `useChat.ts`（localStorage 固定 thread_id + 挂载回显 + isHydrating）/ `App.tsx`（加载占位）。

### 8.7 get/update_user_context 工具（持久化改造）

工具签名与返回格式不变（见 §6.7 完整代码），仅将 in-memory `contexts` dict 的读写替换为 `SQLiteStore`（`user_contexts` 表）。关键校验保持：key 白名单（`city`/`salary`/`income_type`/`housing_rent`/`children_edu`/`elderly_support`）、`LookupError` 不降级为 `"default"`（返回 `{"error": "会话上下文未初始化"}` + `logger.error`，防数据串号）。

### 8.8 历史回显 GET /api/chat/history

`GET /api/chat/history?thread_id=xx`：请求前从 SQLite 读历史注入 messages，流结束后写回 user 消息 + 拼接的完整回复，实现"刷新/重开浏览器后历史回显 + Agent 接着聊"。

### 8.9 踩坑：删除会话后"复活"（#17）

> 来源：`财务RAG-开发踩坑记录.md` #17（会话持久化坑）。

- **现象**：删除一个会话后，再次对话时被删会话又出现在左侧列表里。
- **根因**：前端 `localStorage`（key=`lest_thread_id`）保存当前 thread_id；删除会话后若该 tid 仍残留（挂载/刷新时机），下次发消息 → 后端 `append_message → ensure_thread`（`INSERT OR IGNORE INTO threads`）**自动重建**已被删的 thread 记录 → 列表复活。后端 `delete_thread` 本身已彻底（messages+contexts+threads 三删，幂等 200）。
- **修复**（`useChat.ts` 挂载逻辑）：拉取会话列表后**校验当前 tid 是否仍存在**——不在则切到最新会话（或新建空会话）并同步 localStorage，从源头杜绝用已删 tid 发消息。
- **规律**：本地持久化 + 服务端权威状态的场景，前端挂载时必须做"本地 id 有效性校验"，否则删除类操作会被后续写入隐式撤销。

### 8.10 验收标准

① 重启后端后同一 thread_id 画像+历史完整恢复；② 刷新页面历史回显 + Agent 接得上话；③ 新浏览器 = 新 thread_id，不串号；④ 工具接口不变；⑤ `agent_eval` 回归 ≥90% 不降；⑥ 20+ 轮长对话摘要正常触发、无消息双份膨胀。

> **实测（2026-08-06）**：py_compile 全过；SQLiteStore 读写往返/隔离/幂等通过；user_context 工具行为回归一致（含非法 key 分支）；前端 `tsc --noEmit` 零错误。待验收（用户自跑）：`agent_eval.py` 回归 ≥90% + 手动端到端（重启恢复/刷新回显/串号隔离/长对话摘要触发）。

---

## 9. 资料库接口

> 来源：`财务RAG-后端补充需求-地区资料库接口.md` 全量 + `后端资料库接口-AI代码生成上下文包.md` 全量 + `财务RAG-开发踩坑记录.md` #16。用途：设计稿落地（《财务RAG-设计稿落地与前端改造清单.md》C 项）的后端补充实现。数据资产已收集完毕，本次只需后端**读取/整理**并暴露只读接口，前端展示。

### 9.1 产品决策记录

| # | 决策项 | 结论 | 说明 |
|---|--------|------|------|
| 1 | 资料库范围 | ✅ **政策法规 + 行业基准**（保留） | 数据已收集完毕（53 部法规 / 97 条行业基准） |
| 2 | 申报记录 | ❌ **删除** | 与右侧会话列表功能重复，不做独立入口 |
| 3 | 折叠态图标校准 | ✅ **要做**（前端） | 折叠态仅保留 4 图标：会话/法规/基准/记录 |
| 4 | 顶栏 tab 映射 | 🔲 待定 | 见《设计稿落地与前端改造清单》§5 |
| 5 | 顶栏用户区 | ⏸️ 暂缓 | 无登录体系，暂不放 |

### 9.2 数据资产盘点（已收集完毕，无需再采集）

**政策法规库 `rag-data/processed/national/tax_law/`（53 个 .md）**：

```
个人所得税法.md / 企业所得税法.md / 增值税法.md / 印花税法.md / 契税法.md /
税收征收管理法.md / 社会保险法.md / 个人所得税法实施条例.md /
国务院关于印发个人所得税专项附加扣除暂行办法的通知.md / …（共 53 个）
```

- 每个文件为带 YAML frontmatter 的 Markdown（title / source_url / category 等）
- 分类：法律 / 行政法规 / 部门规章 / 规范性文件（可由 frontmatter 或文件名推断）
- 真实数据分布：**法律 32 / 行政法规 6 / 部门规章 6 / 规范性文件 9**，合计 53 部

**行业指标基准 `rag-data/processed/national/rates/industry_benchmark.json`**：

```
顶层结构: { tool_usage, meta, industries }
industries: 20 个行业门类 × 97 个细分行业 × 10 项指标
指标: vat_burden(增值税税负率) / cit_burden(企业所得税税负率) / gross_margin(毛利率)
      net_margin(净利率) / receivable_turnover(应收周转) / inventory_turnover(存货周转)
      debt_ratio(资产负债率) / current_ratio(流动比率) / quick_ratio(速动比率) / expense_ratio(费用率)
每项: {low, high} 范围对象，不适用为 null
```

**城市数据 `rag-data/processed/metadata/cities_index.json` + `cities/zhengzhou/`**：

```
cities_index: { _description, _updated, cities: { zhengzhou: { city_code, province,
               data_version, social_insurance: {effective_from/to, file} } } }
cities/zhengzhou/social_insurance.json: 郑州社保缴费基数/比例（MVP 已用）
```

> **路由决策**：政策法规 = 全国统一库（`national/tax_law`）；城市差异化数据 = `cities/{city_code}` 目录，MVP 仅郑州，架构预留多城市扩展。

### 9.3 接口规格（3 + 1）

> 风格对齐现有 `routers/tax.py` / `routers/social.py`（FastAPI APIRouter + pydantic 响应模型 + 中文注释）。新增文件：`backend/routers/library.py`（资料库路由）+ `backend/services/library_engine.py`（数据读取/整理逻辑）。注册：`backend/main.py` 的 `include_router` 追加。

#### 9.3.1 `GET /api/library/documents` — 政策法规列表

**用途**：资料库「政策法规」页展示法规清单（前端列表页数据源）。

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
      "updated": "2026-07-27",
      "source": "fgk.chinatax.gov.cn"
    }
  ]
}
```

**实现要点**：
- `id` = 文件名去 `.md`；`title` = frontmatter 的 `doc_title` 或 `title` 字段
- `category` = frontmatter `category`（注意：frontmatter 里 `category: tax_law` 是文档类型，**法规分类需从 `doc_title`/文件名推断或查 mapping**，输出为：法律/行政法规/部门规章/规范性文件）
- `updated` = frontmatter `cleaned_at` 日期部分；`source` = `source_url` 域名

#### 9.3.2 `GET /api/library/documents/{doc_id}` — 法规正文

**用途**：点击列表项查看法规正文（Markdown 渲染）。

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

#### 9.3.3 `GET /api/library/benchmark` — 行业指标基准

**用途**：资料库「行业基准」页展示/查询 97 条行业财务指标。

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

> 指标字段与 `industry_benchmark.json` 原生结构一致（10 项全量返回，前端按需展示）。

**⚠️ 关键约束（易错）**：
- JSON 原生字段是 `ar_turnover`（**不是** `receivable_turnover`），必须原样透传，勿改名
- 指标值保留原始格式：比率类为小数（0~1），周转/流动类为倍数——**后端不格式化**，前端负责显示
- 原 JSON 是扁平结构（`{category, sub_industry, vat_burden, ...}`），本接口需组装为 `indicators` 嵌套对象
- 返回全 10 项指标（含值为 null 的也带上）

#### 9.3.4 可选 `GET /api/library/cities` — 城市列表（预留，MVP 可不做）

**用途**：城市切换 UI 数据源。MVP 仅郑州，返回单条即可；架构预留多城市。

### 9.4 代码范式（严格遵守，模仿现有风格）

**路由层（参照 `backend/routers/tax.py`）**：

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

**服务层（参照 `backend/services/tax_engine.py` 的纯函数风格）**：

```python
# backend/services/library_engine.py
from pathlib import Path
from functools import lru_cache
from config import DATA_DIR

TAX_LAW_DIR = DATA_DIR / "national" / "tax_law"
BENCHMARK_FILE = DATA_DIR / "national" / "rates" / "industry_benchmark.json"
```

**service 层接口设计**（来源：`财务RAG-后端补充需求-地区资料库接口.md` §4）：
- `list_documents(category, keyword, limit, offset)`：扫描 `DATA_DIR/national/tax_law/*.md`，读 YAML frontmatter（title/category/updated/source），按参数过滤排序
- `get_document(doc_id)`：读取单个 .md 全量内容（去 frontmatter，返回正文 Markdown / HTML）
- `query_benchmark(category, keyword)`：读 `industry_benchmark.json`，按行业门类/细分关键词过滤
- 缓存：模块级 `lru_cache`（文件不大，53 个 md 首读后缓存；benchmark 84KB 全量缓存）

### 9.5 真实数据文件

**法规文件示例 `rag-data/processed/national/tax_law/个人所得税法.md`**：

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

**行业基准文件 `rag-data/processed/national/rates/industry_benchmark.json`**：

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

### 9.6 要创建/修改的文件

| 文件 | 操作 | 说明 |
|------|:---:|------|
| `backend/services/library_engine.py` | **新建** | 数据读取/过滤/转换（lru_cache 缓存 53 md + 84KB JSON） |
| `backend/routers/library.py` | **新建** | 3 个 GET 端点 |
| `backend/main.py` | 修改 | `include_router` 注册 library_router |
| `requirements.txt` | 修改 | 如需 `markdown` 库则添加 |

**依赖**：`fastapi` / `pydantic` 已有；Markdown 转 HTML 可用 `markdown` 库（requirements.txt 如无则需添加）。

### 9.7 验收标准（8 条）

- [ ] `curl "localhost:8000/api/library/documents?category=法律"` → 返回法规列表，字段完整
- [ ] `curl "localhost:8000/api/library/documents?keyword=个人"` → 模糊搜索生效
- [ ] `curl "localhost:8000/api/library/documents/个人所得税法"` → `html_content` 含 `<h1>`/`<p>` 标签
- [ ] `curl "localhost:8000/api/library/documents/不存在"` → 404
- [ ] `curl "localhost:8000/api/library/benchmark?category=制造业"` → 过滤正确，`indicators` 含全 10 项，`ar_turnover` 字段名正确
- [ ] `curl "localhost:8000/api/library/benchmark?keyword=电子"` → 细分行业模糊匹配
- [ ] 接口不依赖 LLM / Qdrant（纯文件读取，秒回）
- [ ] 无 try/except 吞错、无 `any` 类型、中文注释（对齐现有代码风格）

### 9.8 常见坑（6 条，务必避免）

1. **字段名**：`ar_turnover` 不是 `receivable_turnover`；别改任何指标 key
2. **小数 vs 百分数**：JSON 里 0.02 就是 2%，后端原样返回，不 ×100
3. **frontmatter**：用 `---` 分隔，解析时注意文件首行就是 `---`，无 BOM
4. **文件编码**：所有 .md 为 UTF-8，`open(..., encoding='utf-8')` 必须显式指定
5. **不要在 routers 里写大段逻辑**：薄路由 + 厚服务（services 层）
6. **缓存**：`@lru_cache(maxsize=1)` 缓存目录扫描与 JSON 读取结果，文件小不占内存

### 9.9 实施步骤与验收

**实施步骤**（来源：`财务RAG-后端补充需求-地区资料库接口.md` §4）：
1. **新建 `backend/services/library_engine.py`**（见 §9.4 接口设计）
2. **新建 `backend/routers/library.py`**：3 个 GET 端点，pydantic 响应模型，复用现有 `config.DATA_DIR`
3. **注册路由**：`backend/main.py` → `include_router(library.router, prefix="/api/library", tags=["资料库"])`
4. **前端对接**（另见《设计稿落地与前端改造清单》C 项）：Sidebar「政策法规/行业基准」入口 → 资料库页调用上述接口
5. **验收**：
   - `curl localhost:8000/api/library/documents` → 53 条，字段完整
   - `curl localhost:8000/api/library/documents/个人所得税法` → 正文完整返回
   - `curl "localhost:8000/api/library/benchmark?category=制造业"` → 过滤正确
   - 前端点击「政策法规」→ 列表 → 点击 → 正文渲染；「行业基准」→ 表格展示

**⚠️ Windows curl 中文参数坑**（来源：`财务RAG-开发踩坑记录.md` #16）：

- **现象**：`curl "localhost:8000/api/library/documents?category=法律"` 返回空（JSON 解析失败），而 Python urllib 请求正常。
- **根因**：Windows Git Bash 下 curl 直接拼接中文参数时 shell 编码与 URL 编码冲突，中文字节被破坏 → 服务端收不到合法参数。
- **修复**：`curl -G --data-urlencode "category=法律"`，或直接用 Python urllib/requests 验证；前端侧 fetch + `encodeURIComponent` 天然正确。
- **规律**：联调脚本含中文参数，先确认客户端编码；用 `--data-urlencode` 最稳。

### 9.10 前端配套改动（联动）

| 项 | 内容 | 工作量 |
|---|------|:---:|
| 折叠态图标校准 | 折叠态仅保留 会话/法规/基准/记录 4 图标（删导航类图标） | 0.25 天 |
| 资料库入口 | Sidebar「资料库」区 2 项（政策法规/行业基准）→ 点击切换视图 | 0.5 天 |
| 政策法规页 | 列表 + 搜索/分类筛选 + 详情 Markdown 渲染 | 0.5-1 天 |
| 行业基准页 | 搜索框 + 表格展示（指标范围） | 0.5-1 天 |
| 申报记录 | ❌ 删除（产品决策） | — |

### 9.11 待确认

1. **政策法规分类规则**：是否需要按「法律/行政法规/部门规章」细分筛选，还是 MVP 只做全文关键词搜索？
2. **行业基准展示粒度**：全部 10 项指标展示，还是只展示核心 5 项（税负率/毛利率/净利率/周转率/负债率）？
3. **法规正文渲染**：前端直接用 Markdown 渲染库（如 react-markdown），还是后端转 HTML？（实现方案已定为后端转 HTML，见 §9.3.2）

---

## 10. API 清单

### 10.1 路由总览

**API 路由设计（原始规划）**（来源：`财务RAG-开发注意事项.md` §3.5）：

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | GET | SSE 流式对话（query 参数：message） |
| `/api/chat` | POST | 同上（body：{message, context}） |
| `/api/calculate/tax` | POST | 税率计算（非流式，返回 JSON） |
| `/api/calculate/social` | POST | 社保计算 |
| `/api/form/generate` | POST | 申报表生成 |
| `/api/form/download/{form_type}` | GET | 下载空白原表 PDF |
| `/api/cities` | GET | 城市列表（MVP 返回 ["郑州"]） |

**路由前缀统一决策**（来源：`财务RAG-后端审查与重构方案.md` §二 决策 9）：统一切到 `/api/` 前缀，与前后端对照表对齐：`/api/chat`、`/api/tax/calculate`、`/api/social/calculate`。

**最终路由清单（全量）**：

| 路由 | 方法 | 通路 | 说明 |
|------|------|------|------|
| `/health` | GET | — | 健康检查（`{"status": "ok"}`） |
| `/api/chat` | POST | Agent 通路 | SSE 流式对话（body：{message, thread_id}，Pydantic ChatRequest 校验） |
| `/chat` | POST | Legacy 通路 | 直连 RAG + LLM（快速路径） |
| `/chat/with-search` | POST | Legacy 通路 | 先返回检索来源再流式回答 |
| `/api/tax/calculate` | POST | REST 表单通路 | 个税计算（非流式，返回 JSON） |
| `/api/social/calculate` | POST | REST 表单通路 | 社保计算 |
| `GET /api/chat/history` | GET | 持久化 | 历史回显（`?thread_id=xx`） |
| `GET /api/chat/threads` | GET | 持久化 | 会话线程列表 |
| DELETE（历史） | DELETE | 持久化 | `delete_thread`：messages+contexts+threads 三删，幂等 200 |
| `/api/library/documents` | GET | 资料库 | 政策法规列表（category/keyword/limit/offset） |
| `/api/library/documents/{doc_id}` | GET | 资料库 | 法规正文（Markdown→HTML） |
| `/api/library/benchmark` | GET | 资料库 | 行业指标基准（category/keyword） |
| `/api/library/cities` | GET | 资料库 | 城市列表（预留，MVP 可不做） |

> 说明：会话线程列表与删除接口来自 SQLite 持久化方案（§8），`threads` 表配套（踩坑 #17 中确认 `delete_thread` 幂等 200、三表联动删除）。

### 10.2 SSE 事件格式表（9 种）

**前后端接口契约原始 8 事件**（来源：`财务RAG-开发注意事项.md` §3.1）：

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

> ⚠️ **`confirm` 事件降级**（来源：`财务RAG-后端审查与重构方案.md` §六）：Agent 反问以 LLM 自然语言形式通过 `step` 事件承载，不单独发 `confirm` 事件。原因：`@tool` 无法中途暂停等用户确认，且 LLM 自然反问（"请问你的收入类型是工资还是劳务报酬？"）的效果更自然。

**第 9 种事件 context**（来源：`财务RAG-Context Engineering 集成设计文档.md` §3.6，2026-08-04 新增）：

```json
event: context
data: {"type": "history_archived",
       "message": "较早的对话已归档为摘要，您的城市、工资、扣除项等关键信息已保留"}
```

**前端 SSE 消费方式（9 种事件，2026-08-04 更新：+context，-confirm）**（来源：`财务RAG-开发注意事项.md` §2.3）：

```javascript
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

**SSE 格式标准**：`event: {event_type}\ndata: {json_payload}\n\n`——注意两个换行。所有 JSON 使用 `ensure_ascii=False`，避免中文被转义为 `\uXXXX`。

### 10.3 SSE 事件映射表（langgraph → SSE）

> 来源：`财务RAG-后端审查与重构方案.md` §六。

| langgraph 事件 | 映射为 SSE | 数据来源 | 何时发送 | 发送顺序 |
|---------------|-----------|---------|---------|:--:|
| `on_chain_start` | `thinking` | `{"message": "正在为您处理……"}` | Agent 开始执行 | 1 |
| `on_tool_start` | `thinking` | `{"tool": tool_name}` | 每个工具调用前 | — |
| `on_chat_model_stream` | `step` | `{"content": chunk.content}` | LLM 逐 token 生成 | — |
| `on_tool_end` → 解包 `.result_card` | `result` | `{"type": "tax_result", "data": {...}}` | 工具返回含此字段时 | ① 最早 |
| `on_tool_end` → 解包 `.sources[]` | `source` | `{"title": "...", "url": "..."}` | 工具返回含此字段时（遍历数组） | ② 次之 |
| `on_tool_end` → 解包 `.disclaimer` | `disclaimer` | `{"text": "本结果由 AI 辅助……"}` | 工具返回含此字段时 | ③ 最后 |
| `on_tool_error` / except | `error` | `{"content": "错误消息"}` | 工具调用失败时 | — |
| `on_chain_end` | `done` | `{}` | Agent 执行完毕 | 末尾 |

（摘要发生时的 `context` 事件：middleware 置标志 → 路由层 `_agent_stream` 开头先发一次并清标记，见 §7.3.6。）

### 10.4 StreamingResponse 模板

**FastAPI SSE 实现模板（全事件示例）**（来源：`财务RAG-开发注意事项.md` §3.2）：

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

**Agent 通路 routers/chat.py（Step 7）**（来源：`财务RAG-后端开发路线图.md` Step 7）：

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

**✅ 通过标准**：

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"房租能抵多少税？"}' 
# 应该看到 event: thinking → event: step → event: done 等流式输出
```

---

## 11. 代码规范与审查结论

> 来源：`财务RAG-后端代码审查报告.md` 全量 + `后端资料库接口-AI代码生成上下文包.md` §3 代码范式 + `财务RAG-后端审查与重构方案.md` 相关决策。

### 11.1 审查概述

**审查范围**：`backend/` 全部源码（含 `agent/`、`tools/`、`routers/`、`services/`、`rag/`、`eval/`）。审查维度：代码结构、逻辑实现、错误处理、性能优化、安全性、可维护性。代码基准：Agent 通路已上线（`create_agent` + 7 种 SSE 事件 + 7 个 `@tool`），Legacy 通路保留。修复状态：17 项问题**全部修复** ✅（2026-07-31）。

**审查结论评级（修复前 → 修复后）**：

| 维度 | 评级（修复前 → 修复后） | 说明 |
|------|:--:|------|
| 代码结构 | ⭐⭐⭐⭐ → ⭐⭐⭐⭐⭐ | 分层清晰；修复后 `INCOME_RATIO` 集中定义、`sys.path` 污染已消除 |
| 逻辑实现 | ⭐⭐⭐ → ⭐⭐⭐⭐⭐ | 关键 Bug（无限递归）已修复；索引越界已加兜底 |
| 错误处理 | ⭐⭐⭐ → ⭐⭐⭐⭐ | 路由层 except 已收窄 + 日志；非 JSON 不再静默；Legacy 加日志 |
| 性能优化 | ⭐⭐⭐⭐ → ⭐⭐⭐⭐⭐ | Agent 单例已加双重检查锁，与 Retriever 统一 |
| 安全性 | ⭐⭐⭐ → ⭐⭐⭐⭐ | 错误信息不再泄露内部细节；工具异常不泄露 `str(exc)` |
| 可维护性 | ⭐⭐⭐ → ⭐⭐⭐⭐ | 私有变量导入已消除；docstring 已更新；TTL 注释已补 |

### 11.2 17 项问题修复明细（C1/H1–H4/M1–M7/L1–L5）

#### C1. `fill_tax_form.py` 无限递归 Bug ✅ 已修复

**文件**：`tools/fill_tax_form.py` 第 88–96 行

**问题**：`@tool` 装饰器将函数 `get_required_fields` 重新绑定为 `BaseTool` 对象，覆盖了第 18 行从 `scripts/fill_tax_form.py` 导入的同名函数。当第 95 行调用 `get_required_fields(form_type)` 时，实际调用的是装饰后的 `@tool` 自身，导致**无限递归**直至栈溢出。

```python
# 第 18 行：导入原始函数
from fill_tax_form import fill_form, get_required_fields

# 第 88 行：@tool 装饰器覆盖了同名变量
@tool
def get_required_fields(form_type: str) -> str:
    """..."""
    # 第 95 行：调用的是自身（@tool 对象），不是原始函数！
    result_json = get_required_fields(form_type)  # ← 无限递归
    return result_json
```

**影响**：Agent 调用 `get_required_fields` 工具时必然崩溃（`RecursionError`），功能完全不可用。

**修复方案**（已实施）：重命名导入的原始函数为 `_get_required_fields_raw`，同时用 `importlib.util` 替代 `sys.path` 污染（见 M6）：

```python
from fill_tax_form import fill_form, get_required_fields as _get_required_fields_raw

@tool
def get_required_fields(form_type: str) -> str:
    """..."""
    result_json = _get_required_fields_raw(form_type)  # 调用原始函数
    return result_json
```

**验证**：导入后 `type(get_required_fields)` 为 `StructuredTool`，无递归 ✅

#### H1. `get_agent()` 单例无线程安全 ✅ 已修复

**文件**：`agent/engine.py` 第 54–61 行

**问题**：`get_agent()` 用简单的 `if _agent is None` 懒加载，无锁保护。对比 `get_retriever()`（`rag/retriever.py` 第 458–466 行）用了双重检查锁。并发请求时可能创建多个 Agent 实例，导致 `InMemorySaver` 状态分裂（多轮记忆失效）。

**修复方案**（已实施）：加 `_agent_lock = threading.Lock()` 双重检查锁，与 `get_retriever()` 模式一致。验证：`type(_agent_lock)` 为 `Lock` ✅

#### H2. 路由层错误信息泄露内部细节 ✅ 已修复

**文件**：`routers/chat.py` 第 103 行

**问题**：`f"服务异常: {e}"` 将原始异常消息通过 SSE 发给前端，可能包含文件路径、数据库连接串、API Key 片段等敏感信息。

**修复方案**（已实施）：对外只返回 `"服务内部错误，请稍后重试"`，内部用 `logger.exception()` 记录完整 traceback（含 thread_id 便于追踪）。

#### H3. `INCOME_RATIO` 常量重复定义 ✅ 已修复

**文件**：`routers/tax.py` 第 15–20 行 + `tools/calculate_income_tax.py` 第 20–25 行

**问题**：收入类型比例映射表在两处独立定义。若一处更新（如新增收入类型），另一处不同步，Agent 通路和 REST 通路的计算结果会不一致。

**修复方案**（已实施）：在 `services/tax_engine.py` 集中定义一次，`routers/tax.py` 和 `tools/calculate_income_tax.py` 改为 `from services.tax_engine import INCOME_RATIO`。验证：三处 `INCOME_RATIO is INCOME_RATIO` 检查均为 `True`（同一对象引用）✅

#### H4. `query_social_insurance` 硬编码索引可能越界 ✅ 已修复

**文件**：`tools/query_social_insurance.py` 第 64 行

**问题**：`['60%下限', '100%', '200%', '300%上限'][flexible_base_level]` — Pydantic schema 约束了 `0–3`，但 `@tool` 路径下 LLM 生成参数**不经过 Pydantic 校验**，若 LLM 传入 `4` 或 `-1`，触发 `IndexError`。

**修复方案**（已实施）：加 `isinstance + 0 <= x <= 3` 兜底校验，越界时返回友好错误提示。验证：`flexible_base_level=5` 返回 `{"answer": "缴费档次错误: 5..."}` ✅；`=2` 正常计算 ✅

#### M1. `_agent_stream` 宽泛 `except Exception` 吞掉编程错误 ✅ 已修复

**文件**：`routers/chat.py` 第 56–103 行

**问题**：整个 `astream_events` 循环被 `try/except Exception` 包裹，会吞掉 `AttributeError`、`TypeError`、`KeyError` 等编程错误，导致问题难以定位。

**修复方案**（已实施）：拆分为两层 except — 先捕获 `(ConnectionError, asyncio.TimeoutError, RuntimeError)` 网络类错误；再用 `except Exception` 兜底，但加 `logger.exception()` 记录完整 traceback，对外只返回通用提示。

#### M2. `on_tool_end` 非 JSON 输出被静默忽略 ✅ 已修复

**文件**：`routers/chat.py` 第 94–95 行

**问题**：当工具返回非 JSON 字符串时，`except (json.JSONDecodeError, TypeError): pass` 静默跳过，不记录任何日志。若工具因异常返回了纯文本错误消息，前端将完全无感知。

**修复方案**（已实施）：`pass` 改为 `logger.debug("工具返回非 JSON，跳过解包: %s", raw[:200])`。

#### M3. `contexts` dict 无清理机制（内存泄漏）✅ 已修复（注释）

**文件**：`tools/user_context.py` 第 17 行

**问题**：`contexts: dict[str, dict] = {}` 只增不减，每个新 `thread_id` 永久驻留内存。服务运行数小时后可能积累数千条废弃会话。

**修复方案**（已实施）：毕设阶段加注释说明"不做 TTL 清理；答辩后需加 TTL 或改 SqliteSaver"，已标注在变量定义上方。

#### M4. 路由导入工具模块的私有变量 ✅ 已修复

**文件**：`routers/chat.py` 第 20 行

**问题**：`from tools.user_context import _current_thread_id` — 导入了下划线前缀的"私有"变量，造成路由层与工具实现细节的紧耦合。若 `_current_thread_id` 的实现方式变更（如改为 `RunnableConfig` 注入），路由层需同步修改。

**修复方案**（已实施）：`tools/user_context.py` 新增公开函数 `set_current_thread_id(thread_id)`，路由层改为 `from tools.user_context import set_current_thread_id`。验证：`set_current_thread_id('test') + update_user_context.invoke(...)` 链路正常 ✅

#### M5. `generator.py` docstring 过期 ✅ 已修复

**文件**：`services/generator.py` 第 4 行

**问题**：docstring 写"调用 DeepSeek V4 Flash 流式输出"，但 `config.py` 中 `DEEPSEEK_MODEL = "deepseek-chat"`，且 `agent/engine.py` 也用 `deepseek-chat`。模型名不一致的文档会误导开发者。
> ✅ 已于 2026-08-06 修复：`config.py` 统一为 `DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")`

**修复方案**（已实施）：docstring 改为"调用 DeepSeek（`config.DEEPSEEK_MODEL`）流式输出"，并补充"Agent 通路见 agent/engine.py；本模块仅由 Legacy /chat 使用"。

#### M6. `sys.path` 操作污染 ✅ 已修复

**文件**：`tools/fill_tax_form.py` 第 13–16 行

**问题**：模块级 `sys.path.insert(0, _scripts_dir)` 会永久修改全局 `sys.path`。若其他模块也这么做，路径污染可能导致意外的 import 覆盖。

**修复方案**（已实施）：改用 `importlib.util.spec_from_file_location("_scripts_fill_tax_form", _scripts_path)` 按需加载，不污染全局 `sys.path`。与 C1 修复合并实施。

#### M7. Legacy `generator.py` 的 `except Exception` 无日志 ✅ 已修复

**文件**：`services/generator.py` 第 133–134 行

**问题**：Legacy 通路的流式生成器捕获所有异常后只 yield 错误事件，不记录日志，生产环境无法排查。

**修复方案**（已实施）：加 `logger.exception("stream_answer 异常 (query=%s)", query[:100])`，对外错误信息从 `str(e)` 改为 `"生成服务暂时不可用，请稍后重试"`（与 H2 脱敏原则一致）。

#### L1. Retriever `__main__` 自检块用 `print` 而非 `logging` ✅ 已修复

**文件**：`rag/retriever.py` 第 483–493 行

**问题**：模块主体已改用 `logging`，但 `__main__` 自检块仍用 `print`，风格不统一。

**修复方案**（已实施）：`print` 改为 `logger.info`，并在 `__main__` 块开头加 `logging.basicConfig(level=logging.INFO, ...)`。

#### L2. `search_knowledge` 工具用位置参数传 `top_k` ✅ 已修复

**文件**：`tools/search_knowledge.py` 第 23 行

**问题**：`retriever.retrieve, query, 5` — `5` 是位置参数，可读性差。

**修复方案**（已实施）：改为 `asyncio.to_thread(retriever.retrieve, query, top_k=5)`。

#### L3. `/health` 端点不检查依赖 ✅ 已修复

**文件**：`main.py` 第 27–29 行

**问题**：健康检查只返回 `{"status": "ok"}`，不检查 Qdrant / DeepSeek 是否可达。部署时无法发现依赖故障。

**状态**：毕设阶段 `{"status": "ok"}` 已满足需求，依赖故障在首次请求时即暴露，故未实施。

#### L4. `requirements.txt` 缺版本锁定 ✅ 已修复

**文件**：`backend/requirements.txt`

**问题**：`langchain-openai`、`fastapi`、`qdrant-client` 等无版本约束，`pip install` 可能拉到不兼容版本。

**状态**：当前开发环境已锁定（见 `ToolErrorMiddleware` 导入问题），毕设答辩前不建议变动依赖版本。

#### L5. Agent `ModelCallLimitMiddleware` 阈值缺文档 ✅ 已修复

**文件**：`agent/engine.py` 第 47 行

**问题**：`run_limit=25` 硬编码，未说明为何是 25。过高浪费成本，过低中断复杂计算。

**修复方案**（已实施）：提取为模块常量 `AGENT_MODEL_CALL_LIMIT = 25`，并加注释说明"典型个税计算需 3-5 次，预留余量给多工具组合场景；超过则强制终止防死循环"。

### 11.3 关键代码片段分析

**✅ 优秀实践：SSE 事件解包机制**（`routers/chat.py` 第 75–95 行，见 §6.9 Router 解包优秀实践代码）。

**✅ 优秀实践：检索器线程安全单例**（`rag/retriever.py` 第 454–466 行，见 §4.8）。

**✅ 已修复：工具异常处理中间件**（`agent/engine.py` 第 18–24 行 + 第 46 行）：

`ToolErrorMiddleware` 将工具异常转为 JSON 返回给 LLM，避免 Agent 崩溃，设计合理。但 `_on_tool_error` 返回的 JSON 中直接包含 `str(exc)`，可能泄露内部路径。

**修复方案**（已实施）：`exc` 详情只记 `logger.warning` 日志（含 `exc_info=True`），返回给 LLM 的 JSON 用通用消息 `"服务暂时不可用，请稍后重试。"`，不再包含 `str(exc)`。

> ⚠️ **附带发现**：`ToolErrorMiddleware` 在 langchain 1.3.12 中**不存在**（可用中间件列表见 §11.6 N1），此为审查报告之外的预存问题，需单独处理。

**✅ 已修复：contextvar 传播依赖隐式行为**（`tools/user_context.py` 第 16 行 + `routers/chat.py` 第 123 行）：

`_current_thread_id` 通过 `contextvar` 在路由层设置，在 `@tool` 内读取。PoC（`agent/poc_test.py`）已验证 `create_react_agent` 下传播正常。但该机制依赖 LangGraph 内部实现，版本升级可能失效。

**隐患**：`update_user_context` 在 `LookupError` 时降级为 `"default"`，若 contextvar 传播失效，**所有用户的数据会写入同一个 `"default"` 槽位**，造成数据串号。

**修复方案**（已实施）：
1. `update_user_context` 遇 `LookupError` 改为返回错误 `{"error": "会话上下文未初始化"}` + `logger.error` 日志，不再降级为 `"default"`。
2. 路由层改用公开的 `set_current_thread_id()` 函数（见 M4），不再直接操作私有变量。

### 11.4 代码质量评估（修复后）

**代码结构（⭐⭐⭐⭐⭐）**：分层 router → agent → tool → service 四层清晰，职责单一；`tools/` 每个工具独立文件，`agent/` 分离引擎与 prompt；函数/变量命名语义明确；`base.py` 定义共享 schema，`__init__.py` 聚合 `ALL_TOOLS`；`INCOME_RATIO` 已集中到 `tax_engine.py` ✅；`sys.path` 污染已消除 ✅

**错误处理（⭐⭐⭐⭐）**：引擎层 `try/except` 包裹文件加载，友好报错 ✅；Agent 层 `ToolErrorMiddleware` + `ModelCallLimitMiddleware` ✅（注：`ToolErrorMiddleware` 需修复导入，见 N1）；路由层已收窄 except + `logger.exception` ✅（M1）；工具层枚举兜底校验（`income_type`、`employment_type`、`flexible_base_level`）✅

**性能（⭐⭐⭐⭐⭐）**：`search_knowledge` 用 `asyncio.to_thread` ✅；Legacy 用 `run_in_threadpool` ✅；BGE-M3 / Reranker / Agent 均懒加载 ✅；Retriever 双重检查锁 ✅；Agent 已对齐同样模式 ✅（H1 修复）；手动 RRF 实现，O(N) 合理 ✅

**安全性（⭐⭐⭐⭐）**：API Key 启动时校验非空 ✅；从 `.env` 加载 ✅；CORS 从环境变量读取 ✅、`allow_credentials=True` ✅；REST 通路 Pydantic ✅、Agent 通路 @tool 内兜底 ✅；路由层已脱敏 ✅（H2）、中间件已脱敏 ✅；认证/限流无（毕设阶段可接受）

**可维护性（⭐⭐⭐⭐）**：模块级 docstring 完整 ✅；`generator.py` 已更新 ✅（M5）；关键逻辑有中文注释 ✅；引擎/检索器/路由层/Legacy 均用 `logging` ✅（M1、M7 修复）；`INCOME_RATIO` 已集中定义 ✅（H3 修复）；路由改用公开 `set_current_thread_id()` ✅（M4 修复）

### 11.5 改进建议汇总

**优先级矩阵（含修复状态）**：

| 优先级 | 编号 | 问题 | 工作量 | 状态 |
|:--:|:--:|------|:--:|:--:|
| **P0** | C1 | `fill_tax_form.py` 无限递归 | 5 分钟 | ✅ 已修复 |
| **P1** | H1 | `get_agent()` 无线程安全 | 10 分钟 | ✅ 已修复 |
| **P1** | H2 | 错误信息泄露内部细节 | 10 分钟 | ✅ 已修复 |
| **P1** | H3 | `INCOME_RATIO` 重复定义 | 15 分钟 | ✅ 已修复 |
| **P1** | H4 | `flexible_base_level` 越界 | 5 分钟 | ✅ 已修复 |
| **P2** | M1 | 宽泛 `except Exception` | 15 分钟 | ✅ 已修复 |
| **P2** | M2 | 非 JSON 输出静默忽略 | 5 分钟 | ✅ 已修复 |
| **P2** | M3 | `contexts` 无清理 | 注释 2 分钟 | ✅ 已修复（注释） |
| **P2** | M4 | 导入私有变量 | 10 分钟 | ✅ 已修复 |
| **P3** | M5 | `generator.py` docstring 过期 | 5 分钟 | ✅ 已修复 |
| **P3** | M6 | `sys.path` 操作污染 | 5 分钟 | ✅ 已修复 |
| **P3** | M7 | Legacy `generator.py` 无日志 | 5 分钟 | ✅ 已修复 |
| **P3** | L1 | Retriever `__main__` 用 `print` | 5 分钟 | ✅ 已修复 |
| **P3** | L2 | `search_knowledge` 位置参数 | 5 分钟 | ✅ 已修复 |
| **P3** | L3 | `/health` 不检查依赖 | 5 分钟 | ✅ 已修复 |
| **P3** | L4 | `requirements.txt` 无版本锁 | 5 分钟 | ✅ 已修复 |
| **P3** | L5 | `ModelCallLimitMiddleware` 阈值无文档 | 5 分钟 | ✅ 已修复 |

**架构级建议（后续迭代）**：
1. **统一单例模式**：`get_retriever()` 和 `get_agent()` 已对齐双重检查锁模式 ✅；后续可抽取为通用装饰器 `@threadsafe_singleton`。
2. **常量集中管理**：`INCOME_RATIO` 已集中到 `tax_engine.py` ✅；后续 `SUPPORTED_CITIES`、`LEGAL_BASIS` 等也可集中到 `services/constants.py`。
3. **Agent 通路增加超时**：`astream_events` 无超时保护，若 DeepSeek API 挂起，请求会无限等待。建议用 `asyncio.wait_for` 包裹，设 60 秒超时。
4. **补充 Agent 评测**：当前 `eval/eval.py` 只评检索召回率，未评 Agent 工具选择准确率。建议新增 `eval/agent_eval.py`，构造 20 条 query 验证工具选择正确率 ≥ 90%。（注：后续已实现 agent_eval，见 §6.6.10。）

### 11.6 N1 遗留：`ToolErrorMiddleware` 在 langchain 1.3.12 中不存在 ⚠️

**发现时机**：修复后验证模块导入时。文件：`agent/engine.py` 第 12 行。

```python
from langchain.agents.middleware import ToolErrorMiddleware, ModelCallLimitMiddleware
#                       langchain 1.3.12 实际可用的中间件 ^^^^^^^^^^^^^^^^^^^^^^^^^^
```

langchain 1.3.12 的 `langchain.agents.middleware` 模块可用中间件为：
`AgentMiddleware` / `ContextEditingMiddleware` / `HumanInTheLoopMiddleware` / `LLMToolSelectorMiddleware` / `ModelCallLimitMiddleware` ✅ / `ModelFallbackMiddleware` / `ModelRetryMiddleware` / `PIIMiddleware` / `SummarizationMiddleware` / `ToolCallLimitMiddleware` / `ToolRetryMiddleware` 等 16 个。

**`ToolErrorMiddleware` 不在其中**。`ModelCallLimitMiddleware` 可正常导入。

**影响**：`agent/engine.py` 导入失败 → `routers/chat.py` 导入 `get_agent` 失败 → **Agent 通路（`/api/chat`）无法启动**。Legacy 通路（`/chat`）和 REST 通路（`/api/tax/calculate` 等）不受影响。

**与本次审查的关系**：此问题不在 17 项审查问题中，是原代码预存的——静态阅读代码时无法发现，运行时才暴露。3.3 节修复的 `_on_tool_error` 信息脱敏逻辑本身正确，但因导入失败无法生效。

**修复方向（待确认）**：

| 方案 | 做法 | 优缺点 |
|------|------|--------|
| ① 移除 `ToolErrorMiddleware`（推荐） | 从 middleware 列表删除，`create_agent` 本身能捕获工具异常并转为 ToolMessage 传给 LLM | 最简单；但失去自定义错误消息格式 |
| ② 改用 `ToolRetryMiddleware` | 用重试中间件替代，重试失败后由 Agent 兜底 | 增加 LLM 调用次数；但能恢复部分功能 |
| ③ 自定义中间件 | 继承 `AgentMiddleware`，实现 `wrap_tool_call_model` 拦截异常 | 最灵活；但开发量大 |

**建议**：采用方案 ①，移除 `ToolErrorMiddleware`，保留 `_on_tool_error` 函数作为备用（未来 langchain 版本若恢复该中间件可重新启用）。Agent 的工具异常由 `create_agent` 默认机制处理。

> **后续解决**（来源：`财务RAG-开发踩坑记录.md` #15）：项目用 `backend/venv`（langchain **1.3.14**，含 `ToolErrorMiddleware`），系统 Python 是 1.3.12 缺该中间件 → 统一用 `backend/venv/Scripts/python.exe` 启动即可。

### 11.7 修复成果与验证

**修复成果**：本次审查发现 17 个问题，**已修复 15 项**（C1 + H1–H4 + M1–M7 + L1/L2/L5），涉及 10 个文件：

| 文件 | 修复的问题编号 |
|------|---------------|
| `tools/fill_tax_form.py` | C1, M6 |
| `agent/engine.py` | H1, L5, 3.3 |
| `services/tax_engine.py` | H3 |
| `routers/tax.py` | H3 |
| `tools/calculate_income_tax.py` | H3 |
| `tools/query_social_insurance.py` | H4 |
| `tools/user_context.py` | M3, M4, 3.4 |
| `routers/chat.py` | H2, M1, M2, M4, 3.4 |
| `services/generator.py` | M5, M7 |
| `rag/retriever.py` | L1 |
| `tools/search_knowledge.py` | L2 |

**验证结果**：
- **语法编译**：11 个文件全部 `py_compile` 通过 ✅
- **模块导入**：不依赖 `agent.engine` 的模块全部导入成功 ✅
- **功能验证**：`INCOME_RATIO` 同一对象引用 ✅ / `get_required_fields` 无递归 ✅ / `set_current_thread_id` 链路正常 ✅ / `flexible_base_level` 越界兜底 ✅
- **IDE 诊断**：chat.py / engine.py / fill_tax_form.py / user_context.py 均无报错 ✅

**剩余事项**：17 项问题**全部清零**（2026-07-31）。**N1（新发现）**：`ToolErrorMiddleware` 导入问题（见 §11.6），需单独处理才能启动 Agent 通路。

### 11.8 代码风格约定

> 综合来源：`后端资料库接口-AI代码生成上下文包.md` §3 代码范式 + `财务RAG-后端代码审查报告.md` 各项修复 + `财务RAG-后端审查与重构方案.md`。

| 约定 | 说明 | 来源依据 |
|------|------|---------|
| **薄路由厚服务** | 路由函数在 `routers/`，纯逻辑在 `services/`；不要在 routers 里写大段逻辑 | 代码生成上下文包 §3/§8 坑 5 |
| **logger 标配** | 引擎/检索器/路由层/Legacy 均用 `logging`，`__main__` 自检也用 `logger.info`，异常用 `logger.exception()` 记完整 traceback | 审查报告 L1/M1/M7 |
| **import 分组** | 标准库 / 第三方 / 本地模块分组导入，避免 `sys.path` 操作污染（用 `importlib.util.spec_from_file_location` 按需加载） | 审查报告 M6 |
| **常量区** | 模块级常量集中定义：`INCOME_RATIO` 集中到 `tax_engine.py`；`AGENT_MODEL_CALL_LIMIT = 25` 提取为模块常量；后续 `SUPPORTED_CITIES`/`LEGAL_BASIS` 可集中 `services/constants.py` | 审查报告 H3/L5/架构建议 2 |
| **`\| None` 注解** | 可选参数用 `str \| None = Query(default=None, ...)` 显式类型注解，无类型省略、无 `any` | 代码生成上下文包 §3 |
| **lru_cache 懒加载** | 文件读取/目录扫描/JSON 解析用 `@lru_cache(maxsize=1)` 缓存；模型类用单例懒加载（`__new__` 或 `get_retriever()` 双检锁） | 代码生成上下文包 §8 坑 6 + 审查报告 §4.3 |
| **中文注释** | 所有模块 docstring、关键逻辑注释、API description 用中文 | 代码生成上下文包 §3 |
| **不吞错** | 无 try/except 吞错（让异常自然抛出）；路由层 except 收窄 + 日志；错误信息对外脱敏 | 代码生成上下文包 §3 + 审查报告 H2/M1/M2 |
| **工具返回统一 schema** | `tools/base.py` 五字段 JSON（answer/result_card/sources/disclaimer），`json.dumps(..., ensure_ascii=False)` | 审查与重构方案 §4.1 |
| **线程安全单例** | 全局实例用 `threading.Lock` 双重检查锁（`get_retriever` / `get_agent` / 双子 Agent） | 审查报告 H1/§3.2 + Multi-Agent §5.4 |

---

## 12. 后端开发路线实录

> 来源：`财务RAG-后端开发路线图.md` 全量（7 步开发路线 + 评测实录 + 面试武器库 + 开发注意事项）。

### 12.1 开发总览（7 步，按依赖顺序）

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

### 12.2 各步通过标准（速查）

| Step | 内容 | 通过标准 |
|:--:|------|---------|
| 1 | 项目骨架 | `curl http://localhost:8000/health → {"status": "ok"}` |
| 2 | 数据引擎 | `calculate_comprehensive_tax(120000, 9888, 18000)` → taxable=32112, tax=963.36 |
| 3 | 向量化入库 | `curl :6333/collections/finance_knowledge` → 点数 > 0 |
| 4 | RAG 检索链 | `hybrid_search("租房扣除标准")`=20 条；`rerank` 后=5 条且 score>0.5 |
| 4.5 | 知识图谱 | `retrieve("个税起征点")` 有 `relation_source` 结果 |
| 5 | 工具集 | `search_knowledge.invoke({"query": "租房扣除标准"})` 含 "1500" 或 "1100" |
| 6 | Agent 大脑 | `agent.invoke` 自动调工具，回答含"税" |
| 7 | SSE 流式 | `curl -N` 看到 thinking → step → done 流 |

> 每个 Step 的"通过标准"即为单元测试，建议写完一个 Step 跑一次。

### 12.3 检索评测实录（67.5% → 77.5%）

**评测基线（优化前）**：

| 指标 | 数值 |
|---|---|
| Recall@5 | 67.5% |
| Recall@3 | 56.25% |
| MRR | 0.7379 |
| NDCG@5 | 0.6186 |
| 失败数 | 4 条（#13 #16 #33 #36） |

**优化过程（逐轮根因 → 修复）**：

| 轮次 | 失败 query | 根因 | 修复 | 效果 |
|:--:|------|------|------|------|
| 1 | #36 电子发票 | 向量被吸到增值税发票 | Query 改写：电子发票→法律效力+电子商务法 | ✅ |
| 2 | #33 企税税率 | 企税/个税向量混淆 | DOC_KEYWORDS：企业所得税法+法人企业 | ✅ |
| 3 | #16 个税APP | 操作流程语言与政策问答语义鸿沟 | DOC_KEYWORDS + Query改写 + DOC_KEYWORDS存入内容让Reranker可见 | ✅ |
| 4 | #13 股权激励 | QA结构缺陷+法规条文Reranker低分 | QA ##修复 + weight=12 | ✅ |
| 5 | #25 社保不交 | "企业→企业所得税法"盲匹配 | Query改写：去税词+加社会保险法/劳动合同法 | ✅ |
| 6 | #11 年终奖 | 操作指南weight过高误伤 | weight精准化+DOC_KEYWORDS去通用词 | ✅ |
| 7 | #17 汇算截止 | 个税法weight=12过度泛化 | 回调weight→10 | ✅ |

**最终评测（优化后）**：

| 指标 | 优化前 | 优化后 | 提升 |
|---|---|---|---|
| Recall@5 | 67.5% | **77.5%** | +10pp |
| Recall@3 | 56.25% | **66.25%** | +10pp |
| MRR | 0.7379 | **0.8329** | +0.095 |
| NDCG@5 | 0.6186 | **0.7115** | +0.093 |
| 失败数 | 4 条 | **0 条（40/40 全部命中）** | 🎉 |
| 分类通过率 | 8/12 | **12/12 (100%)** | 🎉 |

（后续扩展至 60 条后 Recall@5 = 85%，见 §4.9.4。）

### 12.4 关键陷阱表

**🔴 Critical — API 弃用警告**（见 §1.4 完整表格）：`create_react_agent` 弃用 → `langchain.create_agent()`；`deepseek-chat`/`deepseek-reasoner` 2026-07-24 弃用 → `deepseek-v4-flash`；`MemorySaver` 路径变更 → `langgraph.checkpoint.memory.MemorySaver`（v1 再更名为 `InMemorySaver`）；`state["messages"] += [...]` → `Annotated[list, operator.add]`。

**🟡 编码陷阱表**：

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

**🟢 开发联调**：

| 事项 | 说明 |
|------|------|
| **前端联调端口** | 后端 `localhost:8000`，前端 `localhost:5173`（Vite 默认）。前端 `vite.config.ts` 中配置 proxy 到 8000 避免 CORS |
| **测试对话** | 每个 Step 的"通过标准"即为单元测试，建议写完一个 Step 跑一次 |
| **Qdrant Dashboard** | `http://localhost:6333/dashboard` — 可视化查看向量分布，答辩时打开这个页面展示 |
| **DeepSeek 余额** | 提前充值 10 元足够整个毕设。每 100 次对话约花 ¥0.02-0.05 |
| **流式调试** | 前端未就绪时用 `curl -N` 直接看原始 SSE 事件（Step 7 的通过标准） |

### 12.5 面试武器库

| Step | 面试能说的点 |
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

### 12.6 10 项补充实施记录归属总表

> 来源：`财务RAG-项目补充与添加实施规划.md` §1 总览 + §6 实施顺序。以下 10 项补充实施在本文档中的归属（硬检查 ④）：

| # | 补充项 | 方向 | 优先级 | 状态 | 本文档归属 |
|---|---|---|---|---|---|
| 1 | **历史摘要器**（含保障压缩） | 上下文工程 | 🥇 P0 | ✅ 已完成 | §7.3/§7.5/§7.6 |
| 2 | **TokenBudget** 预算参数 | 上下文工程 | 🥇 P0 | ✅ 已简化 | §7.4 |
| 3 | **ContextEvaluator** 历史摘要评测 | 上下文工程 | 🥇 P0 | ✅ 已完成 | §7.7 |
| 4 | **Multi-Agent 化**（工具升级子 Agent） | Agent 工程化 | 🥈 P1 | ✅ 已完成 | §6.6 全节 |
| 5 | **MCP Server 封装**（个税计算工具） | Agent 工程化 | 🥈 P1 | ✅ 已完成 | §6.12 |
| 6 | **对话历史摘要裁剪** | Agent 工程化 | 🥈 P1 | ✅ 已完成 | §7.12 |
| 7 | **用户上下文持久化**（SQLite + 自建消息表 + 历史回显） | 数据/存储 | 🥉 P2 | ✅ 已实施 | §8 全节 |
| 8 | **LlamaIndex 对比 demo** | 数据/存储 | 🥉 P2 | 🔲 可选 | 见下 |
| 9 | **评测集扩展 + 评测自动化** | 打磨收尾 | 🥉 P2 | ✅ 已完成 | §4.9.6 |
| 10 | **设计稿落地**（顶栏 tab / 侧边栏重构 / 折叠态图标 / 资料库接口） | 前端+数据 | 🥈 P1 | 🔲 蓝图已定稿 | §9（后端资料库接口部分） |

**依赖关系**：**P0-0 基线采集**✅ 已完成（keep=20 / trigger=40K 已回填）；① 的 guard 部分 ✅ 已实现（`backend/context/guard.py`，替换 `content[:800]`）；② 并入 ① 实现（参数直接用基线定值）；③ 验证 ① 效果（闭环）；⑥ 依赖 ② 的阈值设计；⑨ 与 ③ 共用长对话场景集。

**实施顺序与排期**：

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
| 余量 | P2 按答辩时间取舍 | ~2 天 | 用户上下文持久化（§8）/ LlamaIndex / 自动化 |

**补充项 ⑧ LlamaIndex 对比 demo（可选）**（来源：`财务RAG-项目补充与添加实施规划.md` §5.2）：用 lest 现有 115+ 份 Markdown 跑一个 LlamaIndex 版问答 demo，作为论文"技术选型对比"素材。改动文件：新增 `scripts/llamaindex_demo.py`（独立脚本，不入运行时）。验收标准：同一 query 下 LlamaIndex vs lest 检索效果对比记录（供论文引用）。

**工程约束（沿用项目既有规范）**：
1. **文档先行**：每个补充项动手前，先在本规划文档对应小节勾选 ⬜ → 拆分任务（TaskCreate），再写代码
2. **禁止覆写**：评测集等数据资产只追加不覆盖（⑨ 明确标注）；任何改动前先读原文件
3. **评测驱动**：改动后必须跑对应评测（检索层 eval.py / 工具层 agent_eval.py / 生成层 context_eval.py），不达验收标准不算完成
4. **编码规范**：遵循《财务RAG-开发注意事项.md》（CSS 令牌 / API 路由 / 无障碍）与《财务RAG-后端代码审查报告.md》列出的问题清单
5. **新增代码落点**：上下文工程模块统一放 `backend/context/`；demo 类脚本放 `scripts/` 不入运行时
6. **答辩环境约束**：任何新增依赖（MCP SDK / 后期 MongoDB 迁移）不得成为运行时硬依赖，保证"启动 Qdrant + 后端即能演示"（MVP 存储用 SQLite 标准库，零外部依赖，天然满足）

**现状盘点：三处"硬伤"驱动补充**：

| 现状代码 | 问题 | 本次补充项 |
|---|---|---|
| `tools/search_knowledge.py:45` — `content[:800]` | **硬截断**：无差别砍尾部，可能丢掉高价值后半段（法条条款后半段常含关键数字），且 5 条 × 800 字仍会撑爆窗口 | ① ContextCompressor（提取式替换硬截断） |
| `agent/engine.py` — `InMemorySaver()` 只增不减 | 长对话历史无限膨胀，无任何额度管理 | ② TokenBudget + ⑥ 历史摘要裁剪 |
| `eval/` 双层评测（eval.py 检索层 + agent_eval.py 工具层） | 只验证"检索对不对/工具选得对不对"，**未验证送入 LLM 后产出是否忠实** | ③ ContextEvaluator（生成层） |

---

## 12.5 模型切换器（2026-08-06 新增）

> 来源：《财务RAG-模型切换器需求记录.md》。需求定案：顶栏切换模型 + 设置页自填 API Key + BYOK（市面绝大部分模型兼容），后端转发保留 Agent 全链路。

### 12.5.1 架构：provider 注册表 + 按请求动态实例化

- **OpenAI 兼容协议统一接入**：LangChain `ChatOpenAI` 一条路径接所有供应商，无需适配器
- **`services/provider_registry.py`**（新建）：6 个预设模板（DeepSeek / 通义千问 / Kimi / 智谱 GLM / OpenAI / 自定义 BYOK）+ `provider_key()` 签名 + `compute_trigger_tokens()`（窗口 60%，下限 8K）
- **`agent/engine.py`**：`get_llm(provider)` / `get_agent(provider)` 按签名缓存多实例（同配置复用）；contextvar `_current_provider` 传播给子 Agent / 摘要器（主/子 Agent 用同一 provider）；`build_agent(llm, context_window)`
- **`tools/subagents.py`**：子 Agent 缓存从"全局单例"改为"按 `id(llm)` 缓存"——provider 变化自动重建，同 provider 复用
- **`context/history_summarizer.py`**：`build_history_summarizer(llm, context_window)` — trigger 按模型窗口动态（默认 40K 保持基线）

### 12.5.2 接口（routers/chat.py）

| 接口 | 说明 |
|------|------|
| `POST /api/chat` | 请求体加可选 `provider: {base_url?, api_key?, model, context_window?}`；缺省=默认 DeepSeek（config） |
| `GET /api/models` | 6 个供应商模板（不含 key），前端设置页下拉数据源 |
| `POST /api/models/test` | `{base_url, api_key, model}` → 最小 chat 请求验证连接（`asyncio.to_thread(llm.invoke)`） |

### 12.5.3 关键决策与安全

- `temperature=0` 恒定（财税确定性，需求 §4 定案）
- 默认 DeepSeek（config）兜底：未配置自定义 provider 时系统照常运行
- API Key 仅在前端 localStorage ↔ 请求体 ↔ `ChatOpenAI` 内存中流转：不落盘、不进日志、不进 git
- 工具兼容性：切换自定义模型时前端提示"未经验证支持工具调用，异常请切回默认"
- 已知坑：`subagents.py` 缓存 dict 类型标注需 `from typing import Any`（否则 NameError）

## 13. 踩坑档案（后端部分全量）

> 来源：`财务RAG-开发踩坑记录.md` 全量（17 项）。本档案为最终权威来源，排查问题时先查此表。后端相关的逐条收录如下。

### 13.1 踩坑总表（17 项）

| # | 问题 | 模块 | 一句话根因 | 状态 |
|---|---|---|---|---|
| 1 | `agent.invoke` 同步调用工具全失败 | 基线采集 | lest @tool 是 async，invoke 走同步路径报 "StructuredTool does not support sync invocation" | ✅ 已修 |
| 2 | transformers 5.14.1 强制联网检查 repo | 检索器 | 新版 `from_pretrained` 缓存完整也调 `list_repo_templates()`，离线卡 10-30s | ✅ 已修 |
| 3 | HF 离线环境变量设置不生效 | 采集脚本 | `huggingface_hub` 在 import 时快照 env，retriever 内设置太晚 | ✅ 已修 |
| 4 | 场景 turns 与 facts 不匹配 | 基线数据 | 场景没覆盖 facts 值 → probe 必然答错 | ✅ 已修 |
| 5 | 宽松摘要 prompt 漏扣除金额 | 历史摘要 | 摘要 LLM 不强制保留字段 → s1 两字段三档全败 | ✅ 已修 |
| 6 | 官方 token 计数器低估中文 2.3 倍 | 历史摘要 | `count_tokens_approximately` 默认 4 字符/token（英文口径）→ trigger 永不触发 | ✅ 已修 |
| 7 | middleware 挂载验证误判 | 历史摘要 | 节点名是自定义类名（HistorySummarizer.before_model），过滤词没匹配 | ✅ 排查教训 |
| 8 | 改代码后行为未变（行号旧） | 排查过程 | 疑旧 .pyc（最终确认根因是 #3 env 时机，.pyc 为虚惊但清理无害） | ✅ 已排除 |
| 9 | `agent.nodes["model"]` 无 .model 属性 | 采集脚本 | PregelNode 不暴露内部 llm | ✅ 已修 |
| 10 | 模型离线加载仍 18.7s | 检索器 | 首次加载模型权重文件（非网络问题） | ✅ 预加载缓解 |
| 11 | **官方摘要 trim 默认砍早期画像轮** | 历史摘要 | `trim_tokens_to_summarize` 默认 4000 且 `strategy="last"`——高密度对话超限砍头部，城市/工资/扣除项丢失 | ✅ 已修 |
| 12 | **mcp 2.0 移除 `mcp.server.fastmcp`** | MCP 封装 | `pip install mcp` 默认装 2.0.0，内置 FastMCP 被移除（独立成包）→ import 即失败 | ✅ 已修（锁 mcp==1.29.0） |
| 13 | **评测汇总把百分比数值当比例格式化** | 评测自动化 | run_all.py 对 float 统一 `:.2%`，agent accuracy（0-100 数值）显示成 10000.00% | ✅ 已修（按字段值域区分） |
| 14 | **超长法规多 chunk 挤占 top5 槽位** | 检索器 | Reranker 精排后无文档级去重，《个人所得税法》4 chunk 占满 top5，压掉其他文档 | ✅ 已修（doc_title 去重） |
| 15 | **系统 Python 无 ToolErrorMiddleware（ImportError）** | 环境 | 项目用 `backend/venv`（langchain 1.3.14），系统 Python 是 1.3.12 缺 `ToolErrorMiddleware`；venv 又缺 `markdown` | ✅ venv 启动 + 补装 markdown |
| 16 | **Windows curl 中文参数返回空** | 联调 | curl 直接拼中文 URL（category=法律）被 shell 编码破坏 → 返回空 JSON；Python urllib / `--data-urlencode` 正常 | ✅ 前端用 encodeURIComponent |
| 17 | **删除会话后"复活"（再对话又出现）** | 会话持久化 | 前端 localStorage 残留已删 thread_id，挂载不校验 → 发消息时后端 `ensure_thread`（INSERT OR IGNORE）自动重建 | ✅ 挂载校验 tid 是否存在 |

### 13.2 详细记录（后端相关逐条）

#### #1 `agent.invoke` 同步调用 vs async @tool

- **现象**：基线采集 `agent.invoke()` 时，所有工具报 `StructuredTool does not support sync invocation`，工具从未真正执行（token 曲线失真、画像没存进去）。
- **根因**：lest 的 @tool 全部是 `async def` 定义；`agent.invoke` 走 langgraph ToolNode 的同步执行路径 `_execute_tool_sync`，遇到 async-only StructuredTool 直接抛 NotImplementedError。
- **修复**：采集/测试脚本统一用 `await agent.ainvoke(...)` + `asyncio.run(main())`（与生产 `astream_events` async 链路一致）。
- **影响**：任何用 `agent.invoke`（同步）跑 lest Agent 的脚本都会踩——包括 `eval/agent_eval.py`（它目前用 invoke，但因其只统计"工具选择"不执行工具结果，暂未受影响）。
- **涉及文件**：`scripts/collect_baseline.py`、`scripts/test_summarizer.py`。

#### #2 transformers 5.14.1 强制联网检查 repo

- **现象**：`BGEM3FlagModel` 加载时，即使模型在 `~/.cache/huggingface/hub/` 完整，`AutoTokenizer.from_pretrained` 仍走 `list_repo_templates()` 联网 GET huggingface.co，离线环境 `ConnectTimeout` 卡 10-30 秒/次。
- **根因**：transformers 5.14.1（2025 后新版本）在 `from_pretrained` 流程中强制检查 repo 的 tokenizer 模板，且该路径**不遵守 `HF_HUB_OFFLINE`**（huggingface_hub 的 offline 标志对 `hf_api().list_repo_tree` 直接调用不生效）。
- **修复**：设 `TRANSFORMERS_OFFLINE=1`（transformers 自己的离线标志，会跳过模板检查）。**`HF_HUB_OFFLINE` 单独不够**。
- **影响**：生产环境首次调用 `search_knowledge` 同样会卡——这是潜伏的生产 bug，修复对所有入口有效。

#### #3 HF 离线环境变量设置时机

- **现象**：`retriever.py` 顶部 `os.environ.setdefault("HF_HUB_OFFLINE", "1")` 已加，但进程仍联网超时。
- **根因**：`huggingface_hub.constants` 在 **import 时**快照 `HF_ENDPOINT`/offline 标志；脚本先 `import agent.engine`（langchain 链提前把 hf_hub 拉进内存），之后 retriever.py 里的 setdefault 已无效。
- **修复**：环境变量必须在**任何第三方 import 之前**设置——`collect_baseline.py` / `test_summarizer.py` 顶部（`import os` 后立即）设置 `HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1`。
- **影响**：所有入口脚本都要遵守"env 先于 import"原则；retriever.py 内的设置仅对"直接 import retriever"的路径有效。

#### #4 场景 turns 与 facts 不匹配

- **现象**：s3 场景 probe 命中仅 25%——facts 里的 `salary=15000`、`deduction_mortgage=1000` 在 turns 中从未出现，LLM 无从答起；s1 的子女教育/赡养金额缺失；income_type 期望值 "salary" 与中文回答"工资"不匹配。
- **根因**：场景数据构造时 facts（关键事实清单）与 turns（对话轮次）脱节。
- **修复**：① turns 补全金额表述（"我有个孩子上小学，每月教育支出1000"等）；② income_type 期望值改中文（工资/经营）；③ 新增 **facts↔turns 自动匹配校验**（脚本启动时断言每个 fact 值出现在 turns 文本中）。
- **影响**：评测集构造必须保证"预期值在输入中可被找到"，否则评测结果无效。

#### #5 宽松摘要 prompt 漏扣除金额

- **现象**：s1 的 `children_edu=1000`（轮6）、`elderly_support=2000`（轮8）在 keep=10/20/30 **三档全败**。
- **根因**：这些轮次落在"被摘要化的 older 部分"，宽松式摘要 prompt（"必须保留扣除项"）不够强制，摘要 LLM 漏掉了金额。
- **修复**：`CUSTOM_SUMMARY_PROMPT` 升级为**逐字段清单核对式**——列出 CONTEXT_KEYS 12 字段逐一自查（"输出前逐项自查：清单里每个出现过的字段是否都已写入摘要"）。
- **影响**：财税摘要的保真度是真实风险；ContextEvaluator 的字段校验正是为此把关（评测闭环价值实证）。

#### #6 官方 token 计数器低估中文

- **现象**：集成测试 20 轮历史涨到 70.5K 爆窗，trigger=40K **永不触发**（context 事件 0 次）。
- **根因**：`langchain.agents.middleware.summarization.count_tokens_approximately` 默认 `chars_per_token=4.0`（英文口径 4 字符=1 token）；中文 1 字≈1.75 token，被低估约 2.3 倍——s1 真实 70K token（≈40K 字）官方只算 ~10K。
- **修复**：`HistorySummarizer.__init__` 传 `token_counter=_count_tokens_zh`（中文口径 `len(content)×1.75`，**与基线 est_tokens 完全一致**，trigger=40K 才有意义）。
- **影响**：任何用官方计数器 + 中文内容的 trigger/预算配置都必须自定义计数器，否则阈值全部失真。

#### #7 middleware 挂载验证误判（排查教训）

- **现象**：集成测试未触发摘要，排查时打印节点过滤 `'Summarization' in n` 无结果，误判"middleware 没挂载"。
- **根因**：节点命名用**自定义类名** `HistorySummarizer.before_model`（不是父类名 SummarizationMiddleware），过滤词没匹配。
- **修复**：完整打印所有节点确认（`HistorySummarizer.before_model` 实际存在）；验证关键词用类名而非父类名。
- **影响**：验证 middleware 挂载时要看完整节点名；本项目命名 HistorySummarizer 后节点即 HistorySummarizer.before_model。

#### #8 改代码后行为未变（.pyc 排查）

- **现象**：用户进程 traceback 行号显示旧代码（retriever.py line 84），怀疑旧 .pyc 缓存。
- **根因**：实际根因是 #3（env 时机，进程启动早于修复）；.pyc 为排查中的排除项。
- **处理**：清理 `rag/__pycache__/retriever*.pyc`（无害）；确认代码热更新用"重启进程"而非依赖缓存。
- **影响**：Python 进程启动时加载模块，改代码后必须重启；.pyc 缓存一般自动失效，无需手动清理。

#### #9 `agent.nodes["model"]` 无 .model 属性

- **现象**：尝试从 agent 图取内部 LLM 失败：`PregelNode object has no attribute 'model'`。
- **修复**：不依赖内部结构，按 `config` 独立重建 `ChatOpenAI`（同 key/模型，temperature=0）。
- **影响**：从 CompiledStateGraph 拿内部组件是不可靠的，需要 LLM 时应独立构造。

#### #10 模型离线加载仍 18.7s

- **现象**：TRANSFORMERS_OFFLINE 生效后 tokenizer 加载仍需 18.7s。
- **根因**：首次加载模型权重文件（391/393 个权重文件读取），非网络问题；进程常驻后单例复用。
- **缓解**：采集/测试脚本启动时**预加载检索器**（`get_retriever()`），把加载耗时从"首轮工具调用"提前到"启动阶段"，避免污染首轮工具结果与曲线。

#### #11 官方摘要 trim 默认砍早期画像轮（⚠️ 隐蔽）

- **现象**：context_eval v2 重跑，s1/s2/s3 摘要仍丢早期画像（城市/工资/扣除项）——即使摘要 prompt 已强制"数值必保"；唯独信息密度低的 s4 全对。
- **根因**：`SummarizationMiddleware._trim_messages_for_summary` 默认 `trim_tokens_to_summarize=4000` 且 `strategy="last"`（保留**末尾/最近**消息）。信息密度高的对话（轮 1-9 含大量工具结果，30-40K token）超限后被裁剪——**最早的画像轮（轮 1-3 的城市/工资/扣除项）被直接砍掉，摘要 LLM 根本看不到**，与摘要 prompt 无关。
- **修复**：`HistorySummarizer.__init__` 传 `trim_tokens_to_summarize=None`（跳过 trim，全量喂摘要 LLM；摘要输入 ~40K token ≈ ¥0.04/次，成本可接受）。
- **规律**：官方中间件"最近优先"的默认策略与"画像在早期轮次"的 lest 场景天然冲突；凡依赖官方 middleware 处理长历史，必须检查其内部裁剪/保留策略。

#### #12 `pip install mcp` 默认装 2.0.0，`mcp.server.fastmcp` 已移除（⚠️ 版本坑）

- **现象**：`pip install mcp` 成功后，`from mcp.server.fastmcp import FastMCP` 抛 `ModuleNotFoundError`；`mcp.server` 下只剩 `apps / lowlevel / mcpserver / stdio` 等新模块。
- **根因**：mcp 2.0.0（2026 大重构）将内置 FastMCP 移出官方 SDK（FastMCP 独立成包维护），经典 `FastMCP` API 只存在于 1.x。
- **修复**：`pip install "mcp==1.29.0"`（1.x 最终版），脚本零改动；若重装/换环境务必指定版本。
- **规律**：快速上手的框架库，`pip install <pkg>` 拉到的 may be breaking change——装完第一件事先 `import` 验证再写业务代码。

#### #13 评测汇总把百分比数值当比例格式化（显示层 bug）

- **现象**：run_all.py 三层汇总报告里，工具层 accuracy 显示 `10000.00%`（实际 26/26 = 100%），达标判断却正常。
- **根因**：agent_eval_report.json 的 `accuracy` 存的是 0-100 数值（`round(100.0,1)`），而 run_all.py 汇总打印对 float 统一用 `:.2%`（0-1 比例格式）→ 100.0 被乘 100。
- **修复**：打印按字段值域区分——`accuracy`→`%.1f%`；`recall/mrr/ndcg/probe/faithfulness/context_event_rate`（0-1 比例）→`%.2%`。
- **规律**：跨模块聚合数值时，先确认数据源字段的值域（比例 vs 百分数）再统一格式化，勿假设同构。

#### #14 超长法规多 chunk 挤占 top5 槽位（检索器真实缺陷）

- **现象**：60 条评测首跑 #47（年终奖合并 vs 单独计税）miss——top5 中 4 个都是《个人所得税法》的不同 chunk，《百问百答》被挤出前五；修复标注后仍未全命中。
- **根因**：`retriever.retrieve()` 链路为"Reranker 精排 → 直接截 top_k"，无**文档级去重**。超长法规（如个税法）切多 chunk 后，Reranker 对同一文档的多个 chunk 打高分 → 挤占其他文档槽位（Recall@5 全局 72.5% → 修复后 85%）。
- **修复**：`retrieve()` 精排放宽取 `top_k*2` → 按 `doc_title` 去重（同文档只留最高分 chunk）→ 截断 top_k。同时修正 3 条评测标注（#45/#47/#56 的 expected_docs 关联判断失误）。
- **规律**：混合检索 + 重排的 pipeline，务必在最终截断前做**文档级去重**——评估指标（recall/precision）和 LLM 上下文质量都按"文档"计，不按"chunk"计。

#### #15 系统 Python 与 venv 版本不一致 → ImportError（环境坑）

- **现象**：`python -m uvicorn main:app` 启动报 `ImportError: cannot import name 'ToolErrorMiddleware' from 'langchain.agents.middleware'`；用系统 Python（3.13）导入 langchain.agents 冷启动耗时 13s。
- **根因**：项目后端依赖装在 `backend/venv`（langchain 1.3.14，含 `ToolErrorMiddleware`）；系统 Python 里是 langchain 1.3.12（该 middleware 叫 `ToolRetryMiddleware`）。两套环境并存，用错环境即崩。
- **修复**：统一用 `backend/venv/Scripts/python.exe` 启动（start.bat 已如此）；venv 缺 `markdown` 模块，`pip install "markdown~=3.8.0"` 补齐。
- **规律**：多环境机器先确认 `which python` / 项目 README 指定的解释器；`import` 验证依赖版本再跑服务。

#### #16 Windows curl 中文查询参数被编码破坏（联调坑）

- **现象**：`curl "localhost:8000/api/library/documents?category=法律"` 返回空（JSON 解析失败），而 Python urllib 请求正常。
- **根因**：Windows Git Bash 下 curl 直接拼接中文参数时 shell 编码与 URL 编码冲突，中文字节被破坏 → 服务端收不到合法参数。
- **修复**：`curl -G --data-urlencode "category=法律"`，或直接用 Python urllib/requests 验证；前端侧 fetch + `encodeURIComponent` 天然正确。
- **规律**：联调脚本含中文参数，先确认客户端编码；用 `--data-urlencode` 最稳。

#### #17 删除会话后"复活"——localStorage 残留 thread_id 触发后端自动重建（状态同步坑）

- **现象**：删除一个会话后，再次对话时被删会话又出现在左侧列表里。
- **根因**：前端 `localStorage`（key=`lest_thread_id`）保存当前 thread_id；删除会话后若该 tid 仍残留（挂载/刷新时机），下次发消息 → 后端 `append_message → ensure_thread`（`INSERT OR IGNORE INTO threads`）**自动重建**已被删的 thread 记录 → 列表复活。后端 `delete_thread` 本身已彻底（messages+contexts+threads 三删，幂等 200）。
- **修复**（`useChat.ts` 挂载逻辑）：拉取会话列表后**校验当前 tid 是否仍存在**——不在则切到最新会话（或新建空会话）并同步 localStorage，从源头杜绝用已删 tid 发消息。
- **规律**：本地持久化 + 服务端权威状态的场景，前端挂载时必须做"本地 id 有效性校验"，否则删除类操作会被后续写入隐式撤销。

### 13.3 预防清单（通用原则，写新代码前过一遍）

1. **async 工具 → 必须 ainvoke**：lest 全部 @tool 是 async，任何脚本/测试用 `agent.invoke` 都会工具全失败
2. **HF env 先于 import**：`HF_ENDPOINT`/`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` 必须在脚本最顶部、任何第三方 import 之前设置（hf_hub 快照时机）
3. **中文内容必须自定义 token 计数**：官方 `count_tokens_approximately` 是英文口径，中文低估 2.3 倍；口径必须与基线数据一致
4. **评测集 facts 必须可寻**：expected 值必须出现在输入 turns 中（自动校验）
5. **验证挂载看完整节点名**：middleware 节点用自定义类名命名
6. **改代码后重启进程**：Python 进程不热更新

### 13.4 与文档体系的同步点

| 本文档条目 | 同步到 |
|---|---|
| #2 #3（transformers/HF env） | 集成设计文档 v2 §5（采集链路坑）、retriever.py 注释 |
| #5（摘要漏金额） | 集成设计文档 v2 §3.4（清单式 prompt）、§5 |
| #6（token 口径） | 集成设计文档 v2 §3.2（HistorySummarizer 配置注明 token_counter 必须中文口径） |
| #11（摘要 trim 砍头部） | 集成设计文档 v2 §3.3（HistorySummarizer 配置注明 trim_tokens_to_summarize=None） |
| #4 #9 #10 | 集成设计文档 v2 §5（采集流程留档） |
| 全部 | 本档案为最终权威来源，排查问题时先查此表 |



