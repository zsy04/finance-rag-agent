# 财务 RAG Agent · 项目总览

> **毕设项目** | **财税生活助手** — 面向零财务基础大众的 AI 财税问答 Web 应用
> **决策日期**：2026-07-26 | **状态**：方案设计完成，待开发

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
用户提问 → BGE-M3 双向量编码 → Qdrant 混合检索 Top-20 → Reranker 精排 Top-5 → DeepSeek 流式输出
```

## Agent 工具集（6 个）

| 工具 | 数据源 | 功能 |
|------|--------|------|
| `search_knowledge` | Qdrant 向量库 | 智能问答 |
| `calculate_income_tax` | JSON 税率表（代码） | 个税计算 |
| `query_social_insurance` | JSON 城市数据（代码） | 社保计算 |
| `fill_tax_form` | 字段映射（代码） | 申报材料生成 |
| `get_filing_guide` | MD 操作指引 | 申报流程指引 |
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
├── docs/                  ← 全部方案文档
│   ├── 财务RAG-资料收集蓝图.md
│   ├── 财务RAG-MVP资料收集执行表.md
│   ├── 财务RAG-资料收集预处理方案.md
│   ├── 财务RAG-技术架构与Agent方案.md
│   ├── 财务RAG-产品定义与答辩策略.md
│   ├── 财务RAG-UI设计方案.md
│   ├── 财务RAG-AI提示词工程文档-v1.0.md
│   ├── 财务RAG-开发注意事项.md
│   ├── 财务RAG-后端开发路线图.md
│   └── 财务RAG-前后端对照表.md
├── qdrant_data/           ← Qdrant 数据（不提交）
├── backend/               ← 后端代码（待开发）
└── frontend/              ← 前端代码（待开发）
```

| # | 文档 | 读什么 | 何时读 |
|:--:|------|--------|--------|
| **1** | `docs/财务RAG-资料收集蓝图.md` | 7 大知识域，"收集什么" | 了解项目全貌 |
| **2** | `docs/财务RAG-MVP资料收集执行表.md` | 70 项资料 + 下载链接 + 优先级 | 动手收集资料 |
| **3** | `docs/财务RAG-资料收集预处理方案.md` | 目录结构 + 元数据 + MarkItDown + 质检 | 组织与清洗资料 |
| **4** | `docs/财务RAG-技术架构与Agent方案.md` | 技术栈 + 检索链路 + 6 工具 + UX 规范 | 了解系统设计 |
| **5** | `docs/财务RAG-产品定义与答辩策略.md` | 用户故事 + 亮点 + PPT + 演示 | 准备答辩 |
| **6** | `docs/财务RAG-UI设计方案.md` | 布局 + 3 个视图 + SSE 格式 + 设计系统 | 了解 UI 设计 |
| **7** | `docs/财务RAG-AI提示词工程文档-v1.0.md` | TypeScript 类型 + 组件树 + hooks + SSE + 样式 | **AI 编码时粘贴为上下文** |
| **8** | `docs/财务RAG-开发注意事项.md` | CSS 令牌 + 组件 + SSE + 无障碍 + API 路由 | 编码时查规范 |
| **9** | `docs/财务RAG-后端开发路线图.md` | 7 步后端开发 + 面试话术 + 注意事项 | 后端编码指南 |
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
Phase 0 — 方案设计 ✅ 已完成（本文档体系）
    │
Phase 1 — 资料收集     → `docs/财务RAG-资料收集预处理方案.md`
    │
Phase 2 — 后端开发     → `docs/财务RAG-后端开发路线图.md`（7 步）
    │                     🎯 第一 checkpoint：RAG 问答可流式回答一个税务问题
    │
Phase 3 — 前端开发     → `docs/财务RAG-AI提示词工程文档-v1.0.md`
    │
Phase 4 — 联调 & 演示  → `docs/财务RAG-前后端对照表.md`
    │
Phase 5 — 答辩准备     → `docs/财务RAG-产品定义与答辩策略.md`
```

---

## 给面试官看的摘要

本项目实现了一个完整的 **RAG + Agent 财税问答系统**：

- **检索**：BGE-M3 双向量 + Qdrant 混合检索 + BGE-Reranker 双阶段精排，覆盖 70 份全国财税政策 + 郑州地方数据
- **Agent**：LangChain `create_agent` + LangGraph，6 个工具 Function Calling 自动路由，LLM 不参与金额计算
- **安全**：税率计算走 JSON + 代码，申报材料走字段映射，实时搜索限定 7 个政府域名白名单
- **体验**：流式 SSE + 分步计算展示 + 关键节点确认 + 法规溯源 + AI 免责
- **工程**：FastAPI + React + shadcn/ui，前后端分离，文档完整，可独立开发
