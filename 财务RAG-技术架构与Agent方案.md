# 财务 RAG Agent · 技术架构与 Agent 方案

> **文档类型**：系统设计 | **决策日期**：2026-07-26 | **项目**：毕设
> **关联文档链**：`财务RAG-资料收集蓝图.md` → `财务RAG-MVP资料收集执行表.md` → `财务RAG-资料收集预处理方案.md` → **本文档** → `财务RAG-产品定义与答辩策略.md` → `财务RAG-UI设计方案.md`
> **本文定位**：编码阶段的系统设计依据。定义技术栈、检索链路、Agent 工具集、项目结构。

---

## 一、技术栈

| 层级 | 选型 | 关键细节 |
|------|------|---------|
| **LLM** | DeepSeek V4 Flash | `deepseek-v4-flash`，LangChain `create_agent`，流式 SSE，$0.14/$0.28 /百万token |
| **Embedding** | BGE-M3（FlagEmbedding） | GPU fp16 加速，稠密 1024维 + 稀疏词汇权重 双输出 |
| **向量库** | Qdrant Docker | 原生混合检索，`docker compose up -d`，Web UI :6333，`docker-compose.yml` 在项目根目录 |
| **重排器** | BGE-Reranker-v2-m3（BAAI） | 双阶段检索：Qdrant 初排 Top-20 → Reranker 精排 Top-5 |
| **后端** | FastAPI | `StreamingResponse` SSE 流式输出，OpenAI 兼容 SDK |
| **前端** | React + shadcn/ui | monorepo `frontend/`，纯 CSR |
| **PDF 转换** | Microsoft MarkItDown v0.1.6 | 申报表模板 PDF→MD 转换 |
| **硬件** | RTX 4060 8GB / 16GB RAM | Qdrant 答辩时启动，日常关后台释放内存 |

---

## 二、检索链路

```
用户提问
  ↓
BGE-M3 双向量编码（dense 1024d + sparse 词汇权重）
  ↓
Qdrant 混合检索 → 召回 Top-20
  ↓
BGE-Reranker-v2-m3 精排 → Top-5
  ↓
拼接 System Prompt + RAG 上下文 + 用户提问
  ↓
DeepSeek V4 Flash → StreamingResponse 流式输出
```

---

## 三、Agent 工具集

LLM（DeepSeek V4 Flash）根据用户意图自动选择工具。工具返回结构化结果后，由 LLM 组织语言流式输出。

### 工具总览

| # | 工具名 | 输入 | 数据源 | 对应功能 |
|:--:|--------|------|------|:--:|
| 1 | `search_knowledge` | 用户问题原文 | Qdrant 向量库（已入库知识） | 智能问答 |
| 2 | `calculate_income_tax` | 收入类型、金额、扣除项、省份 | JSON 税率表（代码计算） | 税率计算 |
| 3 | `query_social_insurance` | 城市、就业类型、工资 | JSON 城市数据（代码计算） | 税率计算 |
| 4 | `fill_tax_form` | 申报表类型、用户个人信息 | 字段映射（代码执行） | 申报材料生成 |
| 5 | `get_filing_guide` | 申报场景、城市 | MD 操作指引（文件读取） | 申报指引 |
| 6 | `search_tax_website` | 搜索关键词 | Web Search（白名单域名） | 实时政策 |

### 3.1 `search_knowledge` — RAG 检索

```
输入: query (用户问题原文)
动作: BGE-M3 双向量编码 → Qdrant 混合检索 Top-20 → Reranker 精排 Top-5
输出: [{content, source_url, doc_title, score}, ...]
```

### 3.2 `calculate_income_tax` — 个税计算

```
输入: income_type, annual_income, special_deductions[], province, city
动作: 读取 JSON 税率表 → 按公式计算（不经过 LLM）
输出: {taxable_income, tax_amount, marginal_rate, detail_breakdown}
```

### 3.3 `query_social_insurance` — 社保公积金

```
输入: city, employment_type, salary
动作: 读取 cities/{city}/ JSON → 计算个人/单位应缴
输出: {breakdown: {养老:{单位,个人}, 医疗:{...}, ...}, total_personal, total_employer}
```

### 3.4 `fill_tax_form` — 申报材料生成

```
输入: form_type, user_profile {name, id_card, incomes, deductions, ...}
动作: 字段映射 → 填入模板 → 生成 Markdown 表格
输出: {markdown_table, blank_pdf_url, warnings[]}
```
> ⚠️ 不走 LLM，纯字段映射。保留空白 PDF 原表供用户自行下载。

### 3.5 `get_filing_guide` — 申报流程指引

```
输入: scenario (个税年度汇算/个体户B表/小规模增值税), city
动作: 读取 processed/operations/ + cities/{city}/ 操作指引
输出: {steps: [{step_number, description}], 官方入口_url, 咨询热线}
```

### 3.6 `search_tax_website` — 税务官网白名单搜索

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

---

## 四、RAG vs 实时搜索 调度逻辑

| 用户问 | 走 RAG | 走 Web Search |
|--------|:--:|:--:|
| "租房扣除标准是多少" | ✅ | — |
| "今年出台了哪些新税政" | — | ✅ |
| "社保基数调整了吗" | ⚠️ 可能过期 | ✅ |
| 复杂问题 | ✅ | ✅ 交叉验证 |

LLM 根据问题是否涉及时效性（"最新""今年""最近"等关键词）自动路由。

---

## 五、Agent 调度架构

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

**Agent 实现方式**：LangChain `create_agent` + `MemorySaver`，6 个 `@tool` 通过 Function Calling 自动路由。详见 `财务RAG-后端开发路线图.md`。

---

## 六、UX 用户体验设计规范

> 面向零财务基础大众用户。以下规范基于用户行为分析逐项确认，直接影响 Agent 行为和前端交互设计。

### 6.1 引导式追问机制

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

System Prompt 硬约束：

> "如果用户的问题缺少税率计算或社保计算所需的关键信息（收入类型、金额、城市），先友好地反问 1-2 个问题收集信息，再执行计算。每次只问 1-2 个问题，不要一次性追问过多。"

### 6.2 双入口设计：对话引导 + 快捷表单

| 入口 | 适用用户 | 实现方式 |
|------|---------|---------|
| **对话引导** | 零基础新用户 | Agent 逐字段反问，渐进式收集信息 |
| **快捷表单** | 有经验用户 | 前端独立表单页面（醒目入口按钮），一次性填写，即时生成结果 |

两者不冲突——表单提交后也可以进入对话查看详细解释，对话中也可以随时跳转到表单"一键填完"。

### 6.3 结果可信度：分步计算 + 法律引用 + AI 免责

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

### 6.4 对话级上下文记忆

同一会话中，用户提供的个人信息（城市、工资、收入类型、扣除项）自动复用，不需要重复输入。

```
用户："我在郑州，月薪8000，社保扣多少？"
Agent：[计算郑州社保] → 记忆: {city: "郑州", salary: 8000}

用户："那我个税要交多少？"
Agent：[自动使用记忆的城市和工资计算个税，无需追问]

用户："帮我生成个税申报表"
Agent：[自动使用记忆的所有信息填入表单]
```

实现方式：工具返回时，将提取到的用户关键信息写入对话历史的 `user_context` 字段。后续每次工具调用时，优先读取 `user_context` 中已有的信息，仅追问缺失字段。

---

## 七、项目结构

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

---

## 八、开发环境依赖

### 已就绪

| 工具 | 版本/状态 |
|------|---------|
| Python | 3.13.12 (managed venv) |
| Node.js | 22.22.2 |
| MarkItDown | v0.1.6 ✅ |
| NVIDIA Driver | 560.94 / CUDA 12.6 ✅ |
| RTX 4060 | 8GB VRAM ✅ |

### 需安装

| 工具 | 安装方式 |
|------|---------|
| Docker Desktop | https://docs.docker.com/desktop/setup/install/windows-install/ |
| Qdrant 镜像 | `docker pull qdrant/qdrant` |

### Python 依赖

```bash
pip install fastapi uvicorn[standard]    # 后端框架
pip install FlagEmbedding                # BGE-M3 + Reranker
pip install qdrant-client                # Qdrant SDK
pip install openai                       # DeepSeek（OpenAI 兼容 SDK）
pip install sse-starlette                # SSE 流式
```

### 需注册

| 平台 | 用途 |
|------|------|
| DeepSeek API Key | https://platform.deepseek.com |

---

## 九、不在此文档范围

本方案定义系统架构和工具设计，以下内容归属编码执行阶段：

- 具体代码实现
- 前端页面 UI 设计
- Qdrant 数据写入脚本
- 申报表字段映射逻辑编码
- 白名单搜索的具体实现
