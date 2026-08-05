# 财务RAG-求职技术补强-概念梳理

> 定位：秋招求职前的**技术概念学习清单**，覆盖 12 张 JD 的核心需求与个人知识缺口（Context Engineering / Multi-Agent / LlamaIndex / MCP 及其他高频要求）。
> 性质：纯概念梳理 + 学习路线，不含代码设计（代码设计见后续《Context Engineering 集成设计文档》）。
> 更新：2026-08-02 创建；2026-08-04 增补 §9（lest 三模块补强设计细节）；同日 **Context Engineering 三件套落地完成 ✅**，全文状态同步，§3 Multi-Agent 升级为下一主攻方向（设计见《财务RAG-Multi-Agent 集成设计文档》）。

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
| **Context Engineering** | ✅ **已落地**（三件套：guard 瘦身 + 历史摘要器 + 上下文评测，见 §9） | ✅ 完成 |
| **Multi-Agent 协作** | ❌ 未接触（设计文档已出，待编码） | 🔴 高 |
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
| 3 压缩 | ✅ **guard.py 提取式瘦身**（软上限 400 字、必保句保留） | — |
| 4 组装 | Agent System Prompt + 7 工具定义 ✅ | 统一 ContextBuilder 管线 |
| 5 Token 预算 | ✅ **历史摘要器**（trigger=40K / keep=20 / 两级压缩） | — |
| 6 记忆 | Option C（per-user 隔离，get/update_user_context）+ 摘要裁剪 ✅ | — |
| 7 Query 理解 | query rewriter + 40 条评测集 ✅ | — |
| 8 评测 | ✅ **上下文评测**（judge 忠实度 100% / 事件触发率 100%） | — |

> 结论：**8 环节已全部闭环**（2026-08-04 三件套落地：guard.py 工具瘦身 + history_summarizer 历史摘要 + context_eval 上下文评测）。
> 完成细节与踩坑见 §9 完成状态 + 《开发踩坑记录.md》。下一步主攻方向：**Multi-Agent（§3 → 新设计文档）**。

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

> ✅ **2026-08-05 已完成**：设计 v1.5 → 编码 → 三轮评测迭代。三层评测全绿（主 Agent 路由 26/26 100% / 主层对拍 8/8 / 子层 10/10），`AGENT_MODE=tools` 一键回退保留。实现细节见《财务RAG-Multi-Agent 集成设计文档》（v1.5）和《财务RAG-项目补充与添加实施规划》§4.1。本节保留概念速查。

> ⚠️ **2026-08-04 状态更新**：本节已从"概念层"升级为**下一主攻方向**，实现级设计见《财务RAG-Multi-Agent 集成设计文档》（**v1.5**，经 grill-me 审查修订：拆计税+社保双子 Agent、双层评测、路由三道防线、全局单例、`AGENT_MODE` 模式开关、prompt 双版本、子 Agent 失败降级、**绕过检测强制重算**）。本节保留概念速查，代码落点以设计文档为准。

### 3.1 概念

**Single Agent（当前 lest 形态）**：一个 Agent + N 个工具，LLM 决定调用哪个工具。

**Multi-Agent**：多个角色化 Agent 分工协作，例如：
- 主控 Agent（Router/Supervisor）：理解任务 → 派发给子 Agent
- 研究员 Agent（Researcher）：负责检索/收集资料
- 计算 Agent（Calculator）：负责精确计算（如个税）
- 填表 Agent（Form Filler）：负责生成申报表

### 3.2 为什么需要（与 lest 的关联）

lest 的 8 个 @tool 已经是"准多 Agent"：把"知识检索/个税计算/社保查询/填表/指引"从工具升级为**子 Agent**，每个子 Agent 有自己的 System Prompt、工具集和记忆——这就是 Multi-Agent 化改造路径，**改造成本低、叙事价值高**。
> ✅ 已在 lest 落地为**双子 Agent 设计**（计税 + 社保，Tool-as-Subagent）：设计决策见设计文档 v1.5（§3 顶部指引），含模式开关/prompt 双版本/失败降级/绕过检测。

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
2. ✅ **已在 lest 落地**（双子 Agent，Tool-as-Subagent，2026-08-05 编码完成，三层评测全绿）——实现见《财务RAG-Multi-Agent 集成设计文档》v1.5 + 实施规划 §4.1
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
| ✅ | Context Engineering | 三件套已落地：guard 瘦身 + 历史摘要器 + 上下文评测（§9 完成状态） | 已完成（3-5 天） | `backend/context/` ✅ |
| 🥇 | **Multi-Agent** | **已完成（2026-08-05 落地）** | 2 天 | Agent 架构升级 ✅ |
| 🥈 | MCP 实战 | 把 1 个 @tool 封装成 MCP Server demo | 1-2 天 | scripts/ 或 backend/app/mcp/ |
| 🥈 | MongoDB | 概念学习 + 用户上下文切换存储 | 1 天 | 记忆系统优化 |
| 🥉 | LlamaIndex | 对比学习 + 可选问答 demo | 半天 | 论文技术选型对比素材 |
| 🥉 | LoRA 微调 | 概念学习，暂不实操 | 半天 | 面试话术即可 |
| 🏅 | TDD/AI Coding 叙事 | 整理方法论文档 | 半天 | docs/ + README |

## 8. 面试一句话速查卡

| 问题 | 一句话回答 |
|---|---|
| 什么是 Context Engineering？ | 把送进模型窗口的每条信息当作可设计要素：筛选/压缩/组装/预算/记忆/评测 |
| 为什么 RAG 不够？ | RAG 解决"检索什么"，CE 解决"送进去什么、怎么送、花多少 token" |
| 多 Agent 和单 Agent 的区别？ | 单 Agent=1 个大脑多个工具；多 Agent=多个角色化大脑分工协作，主控路由+共享状态。lest 已把计税升级为独立子 Agent（tool-as-subagent） |
| LangChain vs LlamaIndex？ | LangChain 强在编排与工具；LlamaIndex 强在索引与文档问答 |
| MCP 是什么？ | 统一 LLM 应用与外部工具的接入协议，一次实现处处可用（AI 的 USB） |
| 你做过上下文评测吗？ | lest 用 40 条评测集做检索评测，下一步补"引用正确率"评测，测送入 LLM 后是否忠实 |

---

## 9. lest 三模块补强设计细节（ContextCompressor / TokenBudget / ContextEvaluator）

> 本章把 §2.4 映射表中缺失的 3 个模块展开为**可直接指导编码的设计**，衔接《财务RAG-Context Engineering 集成设计文档》（已出，2026-08-04）。仅做接口级设计 + 落点分析，不含完整实现。基于 lest 当前代码现状（`backend/rag/retriever.py` 4 层检索链、`backend/agent/engine.py` create_agent、`backend/eval/` 双层评测）撰写。
> 三模块的**落地实施（任务拆解/排期/验收）见《财务RAG-项目补充与添加实施规划》§3**。
> ⚠️ **grill 审查修订（2026-08-04）**：经压力审查，**压缩主战场从"单轮 chunk"改为"多轮历史摘要"**——实测 2937 个 chunk 中位数仅 181 字，单轮压缩无意义（§9.2 的假设失效）。修订要点：
> - ContextCompressor 降级为**保障压缩 guard.py**（仅关系扩展文档 >1.2K 字触发），其提取式算法/必保正则保留迁移
> - 核心变为**继承官方 `SummarizationMiddleware`**（langchain 1.3.14 自带，已查证）的历史摘要器，扩展两级压缩 + 画像字段校验 + **SSE context 用户提示事件**（用户新增需求：压缩时给用户提示）
> - 评测改用**长对话场景集**（§9.4 的 query 集方案废弃）；验收四指标：字段完整率 100% / 摘要忠实度 ≥90% / token 降幅 ≥70% / 事件触发率 100%
> - 完整设计见《Context Engineering 集成设计文档》**v2.0**；§9.2-9.4 中与本修订冲突的内容以 v2.0 为准
>
> ✅ **完成状态（2026-08-04）**：三件套已全部实现并通过评测——`backend/context/guard.py`（工具瘦身）+ `history_summarizer.py`（历史摘要，trigger=40K/keep=20/清单式 prompt/中文 token 口径/trim=None）+ SSE `context` 事件（前后端）。验收：judge 忠实度 **100%**、事件触发率 **100%**、probe 92%、历史峰值 <41K 不爆窗。开发全程 11 项踩坑见《财务RAG-开发踩坑记录.md》。面试可直接讲"评测驱动迭代三轮回合修 3 个根因"。

### 9.1 三模块在现有链路中的插入位置

先说清一个约束：lest 使用 `create_agent`（LangChain v1），system_prompt、工具定义、历史消息由框架**黑盒组装**，拿不到中间 prompt。所以三模块的落点必须选在"能插进去"的地方：

| 模块 | 插入位置 | 改动面 |
|---|---|---|
| ContextCompressor | `search_knowledge` 工具内部（`retriever.retrieve` 返回后、工具返回前） | 零 Agent 改动，纯 RAG 层 |
| TokenBudget | (a) 作为 Compressor 的预算参数；(b) 对话历史裁剪（消息进入 Agent 前） | (a) 无侵入；(b) 需 middleware / checkpointer 定制 |
| ContextEvaluator | 离线评测脚本（eval/ 目录），不改运行时 | 独立闭环 |

> 设计原则：**先无侵入落地，再逐步内化**。Compressor 放进工具层即可生效，不需要碰 create_agent——这是 MVP 阶段成本最低、风险最小的改造路径。

### 9.2 ContextCompressor — 上下文压缩模块

**问题**：当前 `search_knowledge` 返回 top-5，每个 chunk 是法条/问答原文片段，常见 500~2000 字。5 条全量塞入 ≈ 2.5K~10K 字（≈ 5K~20K token），挤占窗口，且大量低信息密度句子（程序性描述、重复条款）空耗预算。

**压缩模式选型**（财税法条场景的特殊性）：

| 模式 | 原理 | 成本 | 保真度 | 适用 |
|---|---|---|---|---|
| 提取式 | 按句子重要性抽取关键句，重排拼装 | 0 LLM 调用，毫秒级 | 高（原文句子） | **默认** |
| LLM 摘要 | 小模型生成摘要 | 1 次 LLM 调用/批 | 中（有失真风险） | 提取后仍超预算 |
| 截断 | 直接砍尾部 | 0 | 低（丢失关键内容） | 兜底，尽量不用 |

**为什么默认提取式**：法条数字（扣除额度、税率、年限）错一个就是错误答案。摘要式压缩可能把"1500 / 1100 / 800 三档"概括成"按城市分档"，丢掉精度。提取式只删句子不改写，保真度最高。

**关键信息保护**（提取式的核心技巧）：含数字、法条文号（如"国发〔2018〕41号"）、百分比的句子**强制保留**，不参与重要性淘汰。优先级链：

```
必保句（数字/文号/百分比） > 高 Reranker 分句子 > 段落首句 > 其余按分淘汰
```

**接口设计**：

```python
# backend/context/compressor.py（新目录，对齐 §7 的 lest 落点）
@dataclass
class CompressedChunk:
    content: str            # 压缩后文本
    doc_title: str          # 保留溯源
    source_file: str
    original_len: int       # 原始字符数
    compressed_len: int     # 压缩后字符数
    ratio: float            # 压缩率 = compressed_len / original_len
    method: str             # "extractive" | "llm" | "pass-through"

class ContextCompressor:
    def __init__(self, budget_chars: int,
                 llm: Optional[ChatOpenAI] = None,
                 protect_patterns: Optional[list[str]] = None): ...
    def compress(self, chunks: list[dict], mode: str = "extractive") -> list[CompressedChunk]:
        """按预算压缩 top-k chunks；总长未超预算时原样透传（pass-through）"""
```

**关键设计点**：
- **预算未超时不压缩**——压缩不是目的，控预算才是；透传避免无谓的信息损失与延迟
- **压缩发生在检索后、组装前**——在 `search_knowledge` 返回前调用，对 Agent 完全透明
- **保留溯源字段**——压缩只动 content，`doc_title / source_file / final_score` 原样保留，法规引用不受影响
- **按分数分配预算**——高 final_score 的 chunk 给足额度（甚至不压缩），低分 chunk 重压；避免"每个 chunk 都压一刀"的均摊策略

**参数来源**：`budget_chars` 由 TokenBudget 计算（见 9.3），不是写死常量——两个模块在此解耦。

**面试叙事**："RAG 拿回 top-5 后我加了 ContextCompressor，提取式为主、数字文号必保、按分数分配预算，压缩率 ~60% 而忠实度不掉——因为只删句子、不改写。"

### 9.3 TokenBudget — Token 预算模块

**问题**：现在 prompt 由 system_prompt（~46 行）+ 7 个工具定义 + 全量对话历史（InMemorySaver 只增不减）+ 检索块组成，没有任何额度管理。长对话 + 多轮工具调用后历史无限膨胀，迟早顶爆窗口，或挤掉检索空间。

**计数口径**：中文 1 字 ≈ 1.5~2 token（实测为准）；可用 `tiktoken`（cl100k_base）或 DeepSeek API 实测校准，本地快速路径用估算即可。

**预算分配表**（以 DeepSeek 64K 窗口为例，预留 4K 输出）：

| 分区 | 预算 | 策略 |
|---|---|---|
| system + 工具定义 | 6K | 固定，不参与竞争 |
| 检索上下文（retrieval） | 20K | 动态：Compressor 的 `budget_chars` 由此决定 |
| 对话历史（memory） | 12K | 超出后裁剪最旧轮次 / LLM 摘要压缩 |
| 本轮 query + 中间工具结果 | 18K | 工具结果（计算 JSON）通常几百 token |
| 输出预留 | 4K | 硬性保留，防止截断 |

**动态策略**（面试加分的点）：
- **无检索轮次**：retrieval 的 20K 额度转移给 memory 或 query（如闲聊、纯计算轮）
- **历史摘要裁剪**：超过 12K 时把最旧的 N 轮用 LLM 压成一条摘要（约 500 token）替代原始轮次——"有损但可控"
- **上限兜底**：全部分区之和不得超过 `窗口 - 输出预留`，超了先压历史、再压检索

**落点**：
1. 参数化：`TokenBudget` 计算 → 输出 `budget_chars` → 喂给 ContextCompressor
2. 历史裁剪：消息进入 Agent 前用 `trim_messages`（LangChain 内置）或自定义 middleware 执行——`create_agent` 的 `middleware` 参数已预留扩展位（现挂 ToolError / ModelCallLimit 两个）

**接口设计**：

```python
# backend/context/budget.py
@dataclass
class BudgetAllocation:
    system_tools: int        # system + 工具定义
    retrieval_chars: int     # 供 Compressor 使用（字 vs token 换算）
    memory_tokens: int
    query_tokens: int
    reserved_output: int

class TokenBudget:
    def __init__(self, window_size: int = 64_000, reserved_output: int = 4_000): ...
    def allocate(self, has_retrieval: bool, history_tokens: int) -> BudgetAllocation: ...
    def trim_history(self, messages: list, max_tokens: int) -> list:
        """裁剪最旧轮次；可选摘要压缩回调"""
```

**面试叙事**："窗口是 64K 但你不能真的塞 64K——我做了 TokenBudget，按 system/检索/历史/查询/输出预留五区分配，无检索时额度让渡，历史超限先裁旧再摘要，让预算成为显式工程约束。"

### 9.4 ContextEvaluator — 上下文质量评测

**问题**：现有两层评测只验证"检索对不对、工具选得对不对"，**没有验证'送进 LLM 的上下文最终产出是否忠实'**——而这正是 Context Engineering 的验收标准。

**三层评测体系（现状 → 补齐）**：

| 层 | 现有实现 | 指标 | 状态 |
|---|---|---|---|
| 检索层 | `eval/eval.py` + eval_set.json（40 条） | recall@k / precision@k / MRR / NDCG@5 | ✅ 已有 |
| 工具层 | `eval/agent_eval.py`（20 条） | 工具选择准确率 ≥90% | ✅ 已有 |
| 生成层 | **新增 `eval/context_eval.py`** | faithfulness / 引用正确率 / 上下文利用率 / token 效率 | 🔴 本次补 |

**eval_set v2 结构**（在现有 40 条基础上扩展，不动旧集）：

```json
{
  "id": 41,
  "query": "租房可以税前扣除多少",
  "expected_docs": ["个人所得税专项附加扣除暂行办法"],
  "expected_facts": [
    "直辖市、省会（首府）城市、计划单列市以及国务院确定的其他城市 1500 元/月",
    "市辖区户籍人口超 100 万的城市 1100 元/月",
    "其他城市 800 元/月"
  ],
  "golden_answer": "……（人工写好的标准答案）"
}
```

**四项指标定义**：

| 指标 | 定义 | 计算方式 |
|---|---|---|
| Faithfulness（忠实度） | 回答中每个事实句能否被检索上下文支持 | LLM-as-judge：把 {检索上下文, 回答} 给 judge 模型逐句判定，支持句数 / 总句数 |
| Citation Accuracy（引用正确率） | 回答引用的 source 是否真的支撑对应断言 | 抽 3-5 句带引用的断言，人工或 judge 判定对错 |
| Context Utilization（上下文利用率） | top-k 中真正被回答用到的比例 | 判定每句回答对应哪条检索块，命中块数 / top-k 数 |
| Token Efficiency（token 效率） | 单位 token 产出的有效信息 | 有效事实数 / 输入 token 数；对比压缩开/关两组 |

**评测流程**：
1. 读 eval_set_v2.json → 每条 query 走真实链路（rewrite → retrieve → **Compressor 开/关两组** → Agent 生成）
2. judge 模型（复用 DeepSeek，temperature=0）打 faithfulness 与引用正确率
3. 输出对比报告：压缩前 vs 压缩后的 faithfulness / token 用量 / 延迟——**这就是压缩模块的验收证据**

**建议门槛**：faithfulness ≥ 90%；引用正确率 ≥ 85%；压缩后 token 用量下降 ≥ 40% 且 faithfulness 下降 ≤ 2 个百分点。

**面试叙事**："我补了第三层评测——生成层。用 LLM-as-judge 测 faithfulness 和引用正确率，40+ 条评测集跑压缩前/后对比，证明压缩省 40% token 而忠实度不掉。这比只报 recall@k 有说服力得多。"

### 9.5 实施顺序与依赖

```
依赖：TokenBudget → ContextCompressor（预算参数） → ContextEvaluator（验收闭环）
顺序（每步可独立交付）：
  ① Compressor（1 天）       — 纯 RAG 层，落地即有 token 收益
  ② TokenBudget（0.5 天）    — 参数化 Compressor + 历史裁剪
  ③ ContextEvaluator（1-1.5 天）— 评测集 v2 + judge 脚本，验证 ①② 效果
总投入：约 3 天，与 §7 学习路线中 Context Engineering 的 3-5 天预算匹配
```

### 9.6 面试总结话术（三件套）

> "Context Engineering 我在 lest 落地了三件套：**Compressor**（提取式压缩、数字文号必保、省 40% token）、**TokenBudget**（五区预算分配、动态让渡、历史裁剪）、**ContextEvaluator**（faithfulness + 引用正确率评测闭环）。一句话：RAG 决定检索什么，这三件套决定送进去什么、花多少、好不好——并用数据证明效果好。"

---

## 附：相关外部资料索引

- Anthropic Context Engineering 博客（2025）：上下文工程概念的提出源头
- LangGraph 官方文档 Multi-Agent 章节
- LlamaIndex 官方 "Understanding LlamaIndex" 概念页
- MCP 官方规范文档（modelcontextprotocol.io）
- HuggingFace PEFT/LoRA 教程

> 学习过程中如发现新概念/新工具，随时追加到本文档对应章节（仅追加，不删除既有内容）。
