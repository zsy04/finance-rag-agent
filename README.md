# 财务 RAG Agent · 项目总览

> **毕设项目** | **财税生活助手** — 面向零财务基础大众的 AI 财税问答 Web 应用
> **决策日期**：2026-07-26 | **状态**：Phase 2 后端核心完成（RAG检索+流式问答已跑通），待 Phase 3 前端联调

---

## 一句话定义

用自然语言对话替代复杂税务软件，让每个人都能看懂自己的税、算对自己的钱、填对申报表。

---

## 技术栈速览

| 层级 | 选型 |
|------|------|
| LLM | DeepSeek V4 Flash（`deepseek-v4-flash`） |
| Agent 框架 | LangChain `create_agent` + LangGraph `StateGraph` |
| Embedding | BGE-M3（FlagEmbedding），GPU fp16，稠密+稀疏双向量 |
| 向量库 | Qdrant Docker，原生混合检索（`docker compose up -d`） |
| 重排器 | BGE-Reranker-v2-m3（BAAI），双阶段检索 |
| 后端 | FastAPI + `StreamingResponse` SSE 流式 |
| 前端 | Vite + React 18 + TypeScript + shadcn/ui |
| PDF 转换 | Microsoft MarkItDown v0.1.6 |
| 环境 | Windows 笔记本，16GB RAM，RTX 4060 8GB，NVMe SSD |

---

## 检索链路

```
用户提问 → 元数据预过滤（relevance_tier 分层）
         → BGE-M3 双向量编码（稠密 1024d + 稀疏词汇）
         → Qdrant 混合检索（RRF 融合 → Top-30）
         → BGE-Reranker-v2-m3 精排 → Top-5
         → 拼接上下文 + System Prompt
         → DeepSeek V4 Flash 流式输出
```

## 切分策略（Grill-me 决议）

| 参数 | 值 | 说明 |
|------|:---:|------|
| 语义边界 | 税法 `### 第X条` / QA `## 问句` | MarkdownHeaderTextSplitter |
| chunk 上限 | 800 字 | BGE-M3 最佳窗口 |
| chunk 下限 | 80 字 | 不跨条目合并 |
| 重叠 | 120 字（15%） | 边界不切断关键句 |

## 评测

```bash
cd backend
python eval/eval.py          # 40 条 query，recall@5 / MRR / NDCG
python eval/eval.py -v       # 逐条打印详情
python eval/eval.py --category 个税  # 按分类评测
```

评测数据集 `backend/eval/eval_set.json`，共 40 条，覆盖个税、增值税、社保、契税等 10 个类别。每次修改检索链路后跑一次对比指标变化。

## Agent 工具集（7 个）

| 工具 | 数据源 | 功能 |
|------|--------|------|
| `search_knowledge` | Qdrant 向量库 | 智能问答（三层分层召回） |
| `calculate_income_tax` | `tax_rate_tables.json`（代码） | 个税计算（综合/经营/年终奖/累计预扣） |
| `query_social_insurance` | `cities/zhengzhou/social_insurance.json`（代码） | 社保+公积金计算 |
| `fill_tax_form` | 字段映射 + openpyxl（代码）| 申报表自动填写（A表/B表） |
| `get_filing_guide` | `operations/` 操作指引 | 个税APP申报流程指引 |
| `search_industry_benchmark` | `industry_benchmark.json`（代码）| 行业财务指标参照 |
| `search_tax_website` | Web Search 白名单 | 实时政策查询 |

---

## 快速启动（Docker）

本项目仅 Qdrant 使用 Docker，后端和前端在宿主机直接运行（GPU 直通 BGE-M3）。

```bash
# 1. 安装 Docker Desktop（仅一次）
#    https://docs.docker.com/desktop/setup/install/windows-install/

# 2. 拉取镜像（仅一次）
docker pull qdrant/qdrant

# 3. 启动 Qdrant
cd F:\lest
docker compose up -d

# 4. 验证
#    浏览器打开 http://localhost:6333 → 看到 Qdrant 欢迎页即成功
#    Dashboard: http://localhost:6333/dashboard

# 5. 开发完后停止（数据保留在 ./qdrant_data/）
docker compose down
```

---

## 项目文件结构

```
F:\lest\
├── README.md              ← 你在这里
├── docker-compose.yml     ← Qdrant 容器
├── .gitignore
├── docs/                  ← 全部方案文档（14 个）
│   ├── 财务RAG-资料收集蓝图.md
│   ├── 财务RAG-MVP资料收集执行表.md
│   ├── 财务RAG-资料收集预处理方案.md
│   ├── 财务RAG-技术架构与Agent方案.md
│   ├── 财务RAG-产品定义与答辩策略.md
│   ├── 财务RAG-UI设计方案.md
│   ├── 财务RAG-AI提示词工程文档-v1.0.md
│   ├── 财务RAG-开发注意事项.md
│   ├── 财务RAG-后端开发路线图.md
│   ├── 财务RAG-前后端对照表.md
│   └── 税率表缺失清单.md
├── scripts/               ← 数据处理脚本（9 个）
│   ├── clean_to_md.py         ← 原始 MHTML → Markdown
│   ├── clean_noise.py         ← UI 噪声正则清洗
│   ├── heading_linebreak.py   ← 标题标准化 + 智能换行
│   ├── metadata_tier.py       ← 相关性分层（旧版）
│   ├── final_preprocess.py    ← 全流程预处理（新版）
│   ├── benchmark_to_json.py   ← Excel 行业基准 → JSON
│   ├── md_tables_to_json.py   ← MD 税率表 → JSON
│   └── fill_tax_form.py       ← 申报表自动填写工具
├── backend/
│   ├── eval/                  ← 检索评测
│   │   ├── eval_set.json      ← 40 条评测数据集
│   │   └── eval.py            ← 评测脚本（recall/MRR/NDCG）
│   ├── rag/                   ← RAG 核心
│   └── ...
├── rag-data/              ← 数据（raw + processed）
│   ├── staging/               ← 119 个原始 MHTML/.doc
│   ├── processed/
│   │   ├── national/
│   │   │   ├── tax_law/       ← 53 个税法 Markdown
│   │   │   ├── qa_corpus/     ← 62 个问答 Markdown
│   │   │   ├── rates/         ← JSON 税率表 + 行业基准
│   │   │   ├── operations/    ← 操作指引 Markdown
│   │   │   └── templates/     ← 申报表 A表+B表 模板
│   │   └── cities/
│   │       └── zhengzhou/     ← 郑州社保+公积金 JSON
│   └── 个税操作指南.md
├── qdrant_data/           ← Qdrant 数据（不提交）
├── backend/               ← 后端（FastAPI + RAG + SSE，已跑通）
└── frontend/              ← 前端代码（已有基础）
```

| # | 文档 | 读什么 | 何时读 |
|:--:|------|--------|--------|
| **1** | `docs/财务RAG-资料收集蓝图.md` | 7 大知识域，"收集什么" | 了解项目全貌 |
| **2** | `docs/财务RAG-MVP资料收集执行表.md` | 70 项资料 + 下载链接 + 优先级 | 动手收集资料 |
| **3** | `docs/财务RAG-资料收集预处理方案.md` | 目录结构 + 元数据 + MarkItDown + 质检 | 组织与清洗资料 |
| **4** | `docs/财务RAG-技术架构与Agent方案.md` | 技术栈 + 检索链路 + 6 工具 + UX 规范 | 了解系统设计 |
| **5** | `docs/财务RAG-产品定义与答辩策略.md` | 用户故事 + 亮点 + PPT + 演示 | 准备答辩 |
| **6** | `docs/财务RAG-UI设计方案.md` | 布局 + 3 个视图 + SSE 格式 + 设计系统 | 了解 UI 设计 |
| **7** | `docs/前端开发-AI编程Prompt.md` | 🚀 **前端开发时粘贴给 AI 的上下文**（自包含，14 节） | **开始写前端代码时** |
| **8** | `docs/财务RAG-AI提示词工程文档-v1.0.md` | 完整版 AI 开发上下文（含更多 hooks/SDK 细节） | 需要更详细的 AI 提示时 |
| **9** | `docs/财务RAG-开发注意事项.md` | CSS 令牌 + 组件 + SSE + 无障碍 + API 路由 | 编码时查规范 |
| **10** | `docs/财务RAG-后端开发路线图.md` | 7 步后端开发 + 面试话术 + 注意事项 | 后端编码指南 |
| **10** | `docs/财务RAG-前后端对照表.md` | 接口 + SSE 事件 + 数据类型 + 联调清单 | 前后端联调 |

---

## Git 工作流

### 仓库

- GitHub：先 Private，答辩前改 Public
- 分支：`main`（Trunk-Based，单人开发）

### 分支策略

```bash
# 每个功能开短分支，合并后删除
git checkout -b feat/rag-ingestion
# ... 开发 ...
git add . && git commit -m "feat: BGE-M3 向量化入库"
git checkout main && git merge feat/rag-ingestion
git branch -d feat/rag-ingestion
```

### 提交规范（Conventional Commits）

```
feat:     新功能   → feat: 添加个税计算工具
fix:      修 bug   → fix: SSE 双换行缺失
docs:     文档     → docs: 更新 LLM 模型版本
refactor: 重构     → refactor: 抽取 RAG 检索链
chore:    杂项     → chore: 更新 .gitignore
```

### 首次推送

```bash
# 在 github.com 创建仓库后
git remote add origin https://github.com/USER/finance-rag-agent.git
git push -u origin main
```

---

## 开发阶段 & 里程碑

```
Phase 0 — 方案设计    ✅ 已完成（文档体系）
    │
Phase 1 — 资料收集    ✅ 已完成（115 个文件 + 3 个 JSON 数据源）
    │   ├── 53 税法 + 62 QA → 标准化标题 + 智能换行 + 四层相关性
    │   ├── tax_rate_tables.json（个税+车船税+印花税，含计算流程）
    │   ├── industry_benchmark.json（20 门类×97 行业×10 指标）
    │   └── cities/zhengzhou/social_insurance.json（社保+公积金）
    │
Phase 2 — 后端开发     ✅ RAG检索链 + DeepSeek流式问答已跑通
    │                     → `backend/rag/retriever.py` + `backend/services/generator.py`
    │                     🎯 第一 checkpoint 达成：POST /chat → SSE 流式回答税务问题
    │
Phase 3 — 前端联调      → `docs/财务RAG-前后端对照表.md`
    │
Phase 4 — 联调 & 演示  → `docs/财务RAG-前后端对照表.md`
    │
Phase 5 — 答辩准备     → `docs/财务RAG-产品定义与答辩策略.md`
```

---

## 给面试官看的摘要

本项目实现了一个完整的 **RAG + Agent 财税问答系统**：

- **检索**：三层分层召回（元数据预过滤 + BGE-M3 双向量混合检索 + BGE-Reranker 精排），覆盖 70 份全国财税政策 + 郑州地方数据
- **Agent**：LangChain `create_agent` + LangGraph，6 个工具 Function Calling 自动路由，LLM 不参与金额计算
- **安全**：税率计算走 JSON + 代码，申报材料走字段映射，实时搜索限定 7 个政府域名白名单
- **体验**：流式 SSE + 分步计算展示 + 关键节点确认 + 法规溯源 + AI 免责
- **工程**：FastAPI + React + shadcn/ui，前后端分离，文档完整，可独立开发
