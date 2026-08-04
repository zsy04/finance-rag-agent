# 财务RAG-求职技术补强-概念梳理

> 定位：秋招求职前的**技术概念学习清单**，覆盖 12 张 JD 的核心需求与个人知识缺口（Context Engineering / Multi-Agent / LlamaIndex / MCP 及其他高频要求）。
> 性质：纯概念梳理 + 学习路线，不含代码设计（代码设计见后续《Context Engineering 集成设计文档》）。
> 更新：2026-08-02 创建。

---

## 1. 背景与目标

### 1.1 为什么需要这份文档

秋招 JD（AI 应用/FDE/AI Agent 方向）的高频关键词：**Agent、RAG、Prompt Engineering、Context Engineering、MCP、Multi-Agent、LangChain/LangGraph、向量数据库**。当前个人技能现状与缺口如下：

| 技术 | 个人现状 | 缺口等级 |
|---|---|---|
| RAG 检索链路（BGE-M3 + Reranker + Qdrant） | ✅ 熟练（lest 核心） | — |
| LangChain Agent 编排（create_agent + 7 tools） | ✅ 熟练 | — |
| Prompt Engineering / System Prompt 设计 | ✅ 熟练 | — |
| SSE 流式 / FastAPI 全栈 | ✅ 熟练 | — |
| 评测驱动迭代（40 条评测集） | ✅ 熟练 | — |
| **Context Engineering** | 🟡 有实践未系统化 | 🔴 高 |
| **Multi-Agent 协作** | ❌ 未接触 | 🔴 高 |
| **LlamaIndex** | ❌ 未接触 | 🟡 中 |
| **MCP（Model Context Protocol）** | 🟡 已学基本概念 | 🟡 中（补实战） |
| MongoDB / NoSQL | ❌ 未接触 | 🟡 中 |
| LLM 微调（PEFT/LoRA） | ❌ 未接触 | 🟡 中（算法向） |
| AI Coding 工具链（Cursor/WorkBuddy/SDD） | 🟢 日常使用 | —（包装即可） |

### 1.2 文档目标

1. 建立 Context Engineering 的系统认知（概念 + 技术清单）
2. 快速理解 Multi-Agent、LlamaIndex、MCP 的核心概念与适用场景
3. 给出每项技术的**学习优先级 / 投入时间 / lest 落点**，指导后续学习与项目补强

---

## 2. Context Engineering（上下文工程）— 重点

### 2.1 是什么

**Context Engineering（上下文工程）**：把"送进大模型上下文窗口（context window）的每一条信息"当作可设计、可管理、可优化的产品要素——包括如何**筛选、压缩、排序、记忆、预算**上下文，以及如何**组装**成最终 prompt。

核心理念（2025 年 Anthropic 提出后行业广泛采用）：
> Context window 是 AI 应用的第一性约束。决定 LLM 输出质量的最重要因素，不是模型本身，而是**你给了它什么上下文**。

### 2.2 为什么重要（面试叙事价值）

- 它是 RAG、Agent、记忆系统三者的**共同底层能力**
- JD 中"Context Engineering"正在成为独立考点（TikTok/字节、AI Agent 核心岗点名）
- 把"我会 RAG"升级为"我懂上下文工程"，是**差异化记忆点**

### 2.3 核心环节全景图（8 环节）

| # | 环节 | 解决什么问题 | 关键技术 / 工具 |
|---|---|---|---|
| 1 | **检索（Retrieval）** | 从知识库找最相关片段 | 向量检索（BGE-M3）、混合检索（dense+sparse）、BM25、Reranker |
| 2 | **上下文筛选（Selection）** | 检索结果多，选哪些 | top-k 截断、相关性阈值、去重、Recency 排序 |
| 3 | **上下文压缩（Compression）** | 选中的还是太长 | LLM 摘要、提取式压缩（高亮关键句）、删除低价值片段 |
| 4 | **组装（Assembly）** | 如何拼成 prompt | 角色/系统指令/示例/检索块/历史/问题的结构化布局 |
| 5 | **Token 预算（Budget）** | 窗口有限，怎么分配 | token 计数（tiktoken）、按优先级分区（system/检索/历史/问题） |
| 6 | **记忆（Memory）** | 跨轮/跨会话状态 | 短期（MemorySaver）、长期（用户画像/向量记忆）、记忆读写工具 |
| 7 | **Query 理解（Query Understanding）** | 用户问得模糊 | Query Rewriting、意图分类、多查询扩展（Multi-Query） |
| 8 | **上下文评测（Evaluation）** | 送进去的质量如何 | 引用正确率、答案忠实度、上下文利用率、token 效率 |

### 2.4 lest 现状 vs 8 环节（映射）

| 环节 | lest 已有实现 | 缺失/可补强 |
|---|---|---|
| 1 检索 | BGE-M3 混合检索 top-30 + Reranker 精排 top-5 ✅ | — |
| 2 筛选 | top-5 截断 ✅ | 去重、时间/来源优先级 |
| 3 压缩 | ❌ | **新模块 ContextCompressor** |
| 4 组装 | Agent System Prompt + 7 工具定义 ✅ | **统一 ContextBuilder 管线** |
| 5 Token 预算 | ❌ | **新模块 TokenBudget** |
| 6 记忆 | Option C（per-user 隔离，get/update_user_context）✅ | 长对话摘要裁剪 |
| 7 Query 理解 | query rewriter + 40 条评测集 ✅ | — |
| 8 评测 | 40 条 RAG 评测（检索命中）🟡 | **引用正确率评测（ContextEvaluator）** |

> 结论：8 环节已有 5.5 个，缺 3 个（压缩/预算/上下文评测）——恰好是最容易独立成模块、最出彩的部分。

### 2.5 核心技术名词速查

| 名词 | 一句话解释 |
|---|---|
| Token / Tokens | 模型处理文本的最小单元（中文约 1 字≈1-2 token） |
| Context Window | 模型一次能处理的最大 token 数（如 128K） |
| System Prompt | 给模型的"总规则"，通常固定不变 |
| Few-shot / In-context Learning | 在 prompt 里给示例，让模型"照猫画虎" |
| Reranker | 对初检索结果做精细重排的模型（如 BGE-Reranker-v2-m3） |
| Context Compression | 把长上下文压短再送进模型（摘要/截断/高亮） |
| Token Budget | 给各上下文区块分配 token 额度的策略 |
| Memory（短期/长期） | 短期=本轮对话；长期=跨会话的用户状态/画像 |
| Query Rewriting | 把用户问题改写得更利于检索（扩写/改写/纠错） |
| 忠实度（Faithfulness） | 回答是否忠于检索到的上下文（防幻觉的关键指标） |

---

## 3. Multi-Agent（多 Agent 协作）

### 3.1 概念

**Single Agent（当前 lest 形态）**：一个 Agent + N 个工具，LLM 决定调用哪个工具。

**Multi-Agent**：多个角色化 Agent 分工协作，例如：
- 主控 Agent（Router/Supervisor）：理解任务 → 派发给子 Agent
- 研究员 Agent（Researcher）：负责检索/收集资料
- 计算 Agent（Calculator）：负责精确计算（如个税）
- 填表 Agent（Form Filler）：负责生成申报表

### 3.2 为什么需要（与 lest 的关联）

lest 的 7 个 @tool 已经是"准多 Agent"：把"知识检索/个税计算/社保查询/填表/指引"从工具升级为**子 Agent**，每个子 Agent 有自己的 System Prompt、工具集和记忆——这就是 Multi-Agent 化改造路径，**改造成本低、叙事价值高**。

### 3.3 主流框架对比

| 框架 | 特点 | 适用场景 | 学习成本 |
|---|---|---|---|
| **LangGraph**（推荐） | 图结构编排，状态机，细粒度控制；与 LangChain 生态无缝 | 生产级 Agent 工作流、多 Agent | 中（需理解 State/Node/Edge） |
| AutoGen（微软） | 对话式多 Agent，支持人机协同 | 研究型、复杂任务分解 | 中 |
| CrewAI | 角色/任务/流程概念直观，低代码 | 快速原型、业务流程自动化 | 低 |
| OpenAI Swarm | 轻量实验性框架，Handoff 概念 | 教学/原型（官方定位非生产） | 低 |

### 3.4 核心机制（面试必答点）

| 机制 | 说明 |
|---|---|
| **路由（Routing）** | 主 Agent 判断任务类型，分发给对应子 Agent |
| **委派（Handoff/Delegation）** | 子 Agent 间转移控制权（谁在说话、谁在用工具） |
| **共享状态（Shared State）** | 多 Agent 之间传递数据的公共状态（LangGraph 的 State） |
| **终止条件（Termination）** | 何时停止循环（达到目标/超步数/预算耗尽） |
| **记忆隔离** | 每个子 Agent 的上下文要不要共享（设计取舍） |

### 3.5 学习路线

1. 读 LangGraph 官方 Multi-Agent 示例（半天）
2. 在 lest 里把 2 个 @tool 升级为子 Agent 跑通 demo（1-2 天）
3. 准备 3 句话对比：LangGraph（图+状态机） vs AutoGen（对话） vs CrewAI（角色）

---

## 4. LlamaIndex

### 4.1 定位

**LlamaIndex（原 GPT Index）**：面向"文档 → 索引 → 问答"的检索框架，与 LangChain 同赛道。核心优势在**索引构建与数据连接**（Data Framework），对文档问答类场景开箱即用。

### 4.2 核心概念

| 概念 | 一句话解释 |
|---|---|
| Document / Node | 文档与切分后的节点（对应 lest 的 chunk） |
| VectorStoreIndex | 把节点向量化建索引（对应 Qdrant Collection） |
| Query Engine | 封装"检索 + 组装 prompt + LLM 回答"的问答入口 |
| Agent / Workflow | 新版提供的 Agent 与事件流编排能力 |

### 4.3 与 LangChain 对比（面试准备 3 句话）

| 维度 | LangChain | LlamaIndex |
|---|---|---|
| 强项 | Agent 编排、工具调用、生态广 | 索引构建、文档问答、数据连接 |
| 检索 | 需组合组件（Retriever/Reranker） | 开箱即用（VectorStoreIndex） |
| 学习曲线 | 组件多、抽象多 | 更直接，面向"问答" |
| 选择依据 | 需要复杂 Agent 流程 | 主要做文档问答 |

### 4.4 学习建议

- **不学深，学对比**：只需能讲清"LangChain 强编排 / LlamaIndex 强索引"即可
- 可选：用 lest 的 115 份税法文档跑一个 LlamaIndex 版问答 demo（半天），对比检索效果，作为论文"技术选型对比"素材

---

## 5. MCP（Model Context Protocol）

### 5.1 是什么（回顾）

**MCP**：Anthropic 提出的开放协议，统一了"LLM 应用 ↔ 外部工具/数据源"的接入标准。类比：**MCP 之于 AI 工具，如 USB 之于外设**——一次实现，处处可用。

### 5.2 三要素

| 要素 | 作用 | 类比 |
|---|---|---|
| **MCP Server** | 提供工具/资源/提示词的服务端 | USB 设备 |
| **MCP Client** | 应用侧连接与调用 | USB 接口 |
| **Host（宿主）** | LLM 应用（Claude Desktop / WorkBuddy / 自研 Agent） | 电脑本体 |

### 5.3 与 lest 的关联

- lest 的 7 个 @tool 目前是 LangChain 内部工具（进程内函数）
- 升级路径：把"个税计算/社保查询"封装成 **MCP Server**，让任何 MCP 兼容的宿主都能调用 —— 这是 JD 里"Agent 能力标准化"的重要加分项
- 面试叙事：从"工具"到"标准协议工具"的工程化升级

---

## 6. 其他 JD 高频缺口补遗

### 6.1 MongoDB / NoSQL

| 概念 | 要点 |
|---|---|
| 文档型数据库 | 数据以 JSON-like 文档存储（BSON），无需预定义 schema |
| 适用场景 | 灵活字段、日志、用户画像、向量存储（MongoDB Atlas Vector Search） |
| 与 SQL 对比 | MySQL 强关系/事务；MongoDB 强灵活/水平扩展 |
| lest 落点 | 用户上下文（per-user profile）可用 MongoDB 替代/并存 JSON 文件 |

### 6.2 LLM 微调（PEFT / LoRA）

| 概念 | 要点 |
|---|---|
| 为什么微调 | 让模型适配领域（法律术语、财税格式）、对齐输出风格 |
| 全参 vs PEFT | 全参训练成本高；PEFT（Parameter-Efficient）只训少量参数 |
| **LoRA** | 注入低秩适配矩阵，训练极小参数量，效果接近全参微调 |
| 工具链 | HuggingFace Transformers / PEFT / TRL（SFT/DPO） |
| 与 RAG 关系 | 知识类用 RAG（可控、可更新）；风格/格式类用微调；可两者结合 |
| lest 落点 | 可选：用 DeepSeek 小模型 + LoRA 做财税回复风格微调 demo（投入大，优先级低） |

### 6.3 TDD / BDD（测试驱动开发）

| 概念 | 要点 |
|---|---|
| TDD | 先写失败测试 → 写实现 → 测试通过 → 重构 |
| BDD | 用 Given/When/Then 描述行为，测试即需求文档 |
| 与 AI 应用的结合 | 评测集就是 AI 领域的"测试用例"——lest 的 40 条 RAG 评测即 TDD 思想 |
| 面试叙事 | "我的评测驱动迭代 = AI 应用的 TDD" |

### 6.4 AI Coding 工具链（Cursor / Claude Code / WorkBuddy）

| 概念 | 要点 |
|---|---|
| AI 原生 IDE | Cursor（编辑器）、Claude Code/CodeBuddy（CLI/Agent）、WorkBuddy（当前环境） |
| SDD（Spec-Driven Development） | 先写规格/设计文档 → AI 按规格实现 → 审查，避免盲目生成 |
| Agent Skills | 把方法论沉淀为可复用技能包（如用户正在做的 RAG skill） |
| 面试叙事 | "我用 AI Coding 工具完成了 X，方法论是规格先行 + 评测驱动"——FDE 岗直接加分 |

---

## 7. 学习路线总表（按优先级）

| 优先级 | 主题 | 核心动作 | 投入 | lest 落点 |
|---|---|---|---|---|
| 🥇 | Context Engineering | 概念 + 8 环节映射（本文档）→ 后续设计文档 → compressor/budget/evaluator 模块 | 3-5 天 | backend/app/context/ 新模块 |
| 🥇 | MCP 实战 | 把 1 个 @tool 封装成 MCP Server demo | 1-2 天 | scripts/ 或 backend/app/mcp/ |
| 🥈 | Multi-Agent | LangGraph 官方示例 + lest 2 个 @tool 升级子 Agent | 1-2 天 | Agent 架构升级 |
| 🥈 | MongoDB | 概念学习 + 用户上下文切换存储 | 1 天 | 记忆系统优化 |
| 🥉 | LlamaIndex | 对比学习 + 可选问答 demo | 半天 | 论文技术选型对比素材 |
| 🥉 | LoRA 微调 | 概念学习，暂不实操 | 半天 | 面试话术即可 |
| 🏅 | TDD/AI Coding 叙事 | 整理方法论文档 | 半天 | docs/ + README |

## 8. 面试一句话速查卡

| 问题 | 一句话回答 |
|---|---|
| 什么是 Context Engineering？ | 把送进模型窗口的每条信息当作可设计要素：筛选/压缩/组装/预算/记忆/评测 |
| 为什么 RAG 不够？ | RAG 解决"检索什么"，CE 解决"送进去什么、怎么送、花多少 token" |
| 多 Agent 和单 Agent 的区别？ | 单 Agent=1 个大脑多个工具；多 Agent=多个角色化大脑分工协作，主控路由+共享状态 |
| LangChain vs LlamaIndex？ | LangChain 强在编排与工具；LlamaIndex 强在索引与文档问答 |
| MCP 是什么？ | 统一 LLM 应用与外部工具的接入协议，一次实现处处可用（AI 的 USB） |
| 你做过上下文评测吗？ | lest 用 40 条评测集做检索评测，下一步补"引用正确率"评测，测送入 LLM 后是否忠实 |

---

## 附：相关外部资料索引

- Anthropic Context Engineering 博客（2025）：上下文工程概念的提出源头
- LangGraph 官方文档 Multi-Agent 章节
- LlamaIndex 官方 "Understanding LlamaIndex" 概念页
- MCP 官方规范文档（modelcontextprotocol.io）
- HuggingFace PEFT/LoRA 教程

> 学习过程中如发现新概念/新工具，随时追加到本文档对应章节（仅追加，不删除既有内容）。
