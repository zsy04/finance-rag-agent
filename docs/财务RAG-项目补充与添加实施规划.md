# 财务RAG-项目补充与添加实施规划

> 定位：接下来所有对 lest 的**补充/添加**的实施蓝图。承接《财务RAG-求职技术补强-概念梳理》§9 的三模块设计，扩展至 Agent 工程化、数据与存储、打磨收尾三个方向。
> 性质：规划文档，每项含「目标 / 为什么现在补 / 改动文件 / 实施步骤 / 验收标准 / 工作量」，可直接转成开发任务逐项落地。
> 更新：2026-08-04 创建。

---

## 1. 补充项总览（9 项）

| # | 补充项 | 方向 | 优先级 | 工作量 | 状态 |
|---|---|---|---|---|---|
| 1 | **历史摘要器**（含保障压缩） | 上下文工程 | 🥇 P0 | 1.5-2 天 | ✅ 已完成（集成测试通过） |
| 2 | **TokenBudget** 预算参数 | 上下文工程 | 🥇 P0 | 0.5 天 | ✅ 已简化（参数固化于摘要器） |
| 3 | **ContextEvaluator** 历史摘要评测 | 上下文工程 | 🥇 P0 | 1 天 | ✅ 已完成（judge 100% / 事件 100% / probe 92%） |
| 4 | **Multi-Agent 化**（工具升级子 Agent） | Agent 工程化 | 🥈 P1 | 1-2 天 | ✅ 已完成（双层评测全绿） |
| 5 | **MCP Server 封装**（个税计算工具） | Agent 工程化 | 🥈 P1 | 1-2 天 | ✅ 已完成（tax-calc 3 工具，WorkBuddy 宿主实测通过） |
| 6 | **对话历史摘要裁剪** | Agent 工程化 | 🥈 P1 | 0.5 天 | ✅ 已完成（已被 history_summarizer 覆盖） |
| 7 | **用户上下文持久化**（grill 定案：SQLite + 自建消息表 + 历史回显） | 数据/存储 | 🥉 P2 | 1.5-2 天 | 🔲 已定案待实施 |
| 8 | **LlamaIndex 对比 demo** | 数据/存储 | 🥉 P2 | 半天 | 🔲 可选 |
| 9 | **评测集扩展 + 评测自动化** | 打磨收尾 | 🥉 P2 | 1 天 | ✅ 已完成（60 条，Recall@5 = 85%，run_all.py 落地） |

**依赖关系**：**P0-0 基线采集**✅ 已完成（keep=20 / trigger=40K 已回填）；① 的 guard 部分 ✅ 已实现（`backend/context/guard.py`，替换 `content[:800]`），摘要器部分待做；② 并入 ① 实现（参数直接用基线定值）；③ 验证 ① 效果（闭环）；⑥ 依赖 ② 的阈值设计；⑨ 与 ③ 共用长对话场景集。

> 决策逻辑：**P0 三件套是"低成本、高叙事价值"的核心补强**——§9 已给出接口级设计，且直击现有代码两处硬伤（见 §3）；P1 是求职差异化；P2 按时间余量取舍。

---

## 2. 现状盘点：三处"硬伤"驱动本次补充

| 现状代码 | 问题 | 本次补充项 |
|---|---|---|
| `tools/search_knowledge.py:45` — `content[:800]` | **硬截断**：无差别砍尾部，可能丢掉高价值后半段（法条条款后半段常含关键数字），且 5 条 × 800 字仍会撑爆窗口 | ① ContextCompressor（提取式替换硬截断） |
| `agent/engine.py` — `InMemorySaver()` 只增不减 | 长对话历史无限膨胀，无任何额度管理 | ② TokenBudget + ⑥ 历史摘要裁剪 |
| `eval/` 双层评测（eval.py 检索层 + agent_eval.py 工具层） | 只验证"检索对不对/工具选得对不对"，**未验证送入 LLM 后产出是否忠实** | ③ ContextEvaluator（生成层） |

---

## 3. P0 — 上下文工程三件套（承接概念梳理 §9）

> 设计细节见《求职技术补强-概念梳理》§9.2-9.4 与《财务RAG-Context Engineering 集成设计文档》**v2.0**。
> ⚠️ **grill 审查修订（2026-08-04）**：压缩主战场从"单轮 chunk"改为"多轮历史摘要"——实测 2937 个 chunk 中位数仅 181 字，单轮压缩无意义。本节三项按 v2 架构重排；详细设计见集成设计文档 v2.0。

### 3.1 ① 历史摘要器 + 工具返回瘦身（核心，摘要器待实现）

- **目标**：继承官方 `SummarizationMiddleware`（langchain 1.3.14 已查证 API），扩展**两级压缩**（提取式过滤低价值轮 → LLM 摘要）、**画像字段自动校验**、**SSE context 用户提示**；工具返回瘦身 `guard.py` **已实现 ✅**。
- **改动文件**：
  - ✅ 已完成：`backend/context/guard.py`（提取式瘦身，软上限 400 字，自检通过）、`backend/tools/search_knowledge.py`（替换 `content[:800]`）
  - 待做：`backend/context/history_summarizer.py`（继承官方）、`backend/agent/engine.py`（middleware 链）、`backend/routers/chat.py`（context 事件）、前端 `types.ts` / `useChat.ts` / `ChatMessage.tsx`（提示条）
- **实施步骤**（剩余）：
  1. ✅ 基线采集完成（见集成设计文档 §5）：**keep=20 / trigger=40K**
  2. 继承 SummarizationMiddleware：`model=DeepSeek`、`trigger=("tokens", 40_000)`、`keep=("messages", 20)`、自定义 `summary_prompt`（画像字段必保）
  3. 扩展：提取式预过滤低价值轮 + 摘要标志 → context 事件
  4. ✅ guard.py 已实现（基线数据证明工具返回拼接是膨胀主因，从"保障"升级为"主力"）
  5. SSE context 事件：后端新增第 8 种事件 + 前端提示条
- **验收标准**：① 画像字段完整率 100%（自动校验）；② 摘要忠实度 ≥90%（judge 抽查）；③ 历史 token 降幅 ≥70%；④ 事件触发率 100%；⑤ agent_eval 20 条回归 ≥90%。

### 3.2 ② TokenBudget — 预算参数决策源（0.5 天，参数由基线校准）

- **目标**：五区预算分配（system 6K / 检索 20K / 历史 12K / query 18K / 输出预留 4K），动态让渡 + 历史裁剪。
- **改动文件**：
  - 新增 `backend/context/budget.py`（dataclass `BudgetAllocation`，类 `TokenBudget`）
  - 修改 `backend/tools/search_knowledge.py`：`budget_chars` 由 `TokenBudget.allocate(has_retrieval=True).retrieval_chars` 换算得出
- **实施步骤**：
  1. 实现 token 估算函数（中文 1 字 ≈ 1.5~2 token，可选 tiktoken cl100k_base 校准）
  2. 实现 `allocate()` 五区分配 + 无检索轮让渡逻辑
  3. 实现 `trim_history()`（先裁最旧轮次，为 ⑥ 打基础）
  4. 单测：极端输入（历史 100K token / 无检索轮）下预算总和不超窗口-输出预留
- **验收标准**：① 任意输入下 `sum(alloc) ≤ 窗口 - 预留`；② 检索预算换算成字符数后与 ① 的压缩率联动正确。

### 3.3 ③ ContextEvaluator — 历史摘要质量评测（长对话场景集，1 天）

- **目标**：补齐三层评测的生成层——faithfulness / 引用正确率 / 上下文利用率 / token 效率，用 LLM-as-judge 验证 ① ② 效果。
- **改动文件**：
  - 新增 `backend/eval/context_eval.py`（judge 复用 DeepSeek，temperature=0）
  - 新增 `backend/eval/eval_set_v2.json`（20 条起步：10 条知识问答 + 10 条计算类，含 `expected_facts` + `golden_answer`）
- **实施步骤**：
  1. 设计 eval_set_v2 结构（复用 eval_set.json 的 id/query/category，新增 expected_facts）
  2. 实现评测流程：rewrite → retrieve → **Compressor 开/关两组** → 生成 → judge 判定
  3. 实现四项指标计算与对比报告输出（压缩前 vs 后）
  4. 跑通 20 条，输出基线报告
- **验收标准**：① faithfulness ≥ 90%；② 引用正确率 ≥ 85%；③ 压缩后 token 用量下降 ≥ 40% 且 faithfulness 下降 ≤ 2pp；④ 报告含压缩开/关对比。

---

## 4. P1 — Agent 工程化扩展

### 4.1 ④ Multi-Agent 化（2-2.5 天）

> ✅ **已完成（2026-08-05）**：设计 v1.5 → 编码 → 三轮评测迭代，全部验收指标达标。

> ✅ **设计文档已出（2026-08-04，v1.5）**：《财务RAG-Multi-Agent 集成设计文档》——经 grill-me 压力审查修订，**拆两个子 Agent（计税+社保）+ `AGENT_MODE` 模式开关 + prompt 双版本 + 子 Agent 失败降级 + 绕过检测（强制重算）**（审查发现：prompt 残留工具名诱导调未注册工具；子 Agent 多轮未算出结果时复用 tool_calls 参数直调原工具兜底；LLM 可能不调工具"心算"绕过 → answer 含税额但无 result_card 时强制重算），含完整 prompt / 代码骨架 / 双层评测 / 路由三道防线 / 一致性硬校验 / 降级机制 / 绕过检测 / 风险回退。**实现级细节以此文档为准，本节仅保留方向。**

**✅ 评测结果（2026-08-05）**：

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

**踩坑记录**：
1. langgraph-prebuilt 1.1.0 ToolNode sync 路径只走 `_execute_tool_sync`，不检测 async 工具 → 4 个 `async def @tool` 全部改为 sync `def` + 内部 `asyncio.run()`
2. 评测用例 `direct_args` 参数名必须与工具 `args_schema` 字段严格对齐
3. `fill_tax_form` 需在 SYSTEM_PROMPT_MULTI 中加示例 + B 表两步流程结构化，否则 LLM 倾向先查画像再放弃

- **目标**：把计税、社保两个领域升级为独立子 Agent，跑通轻量版 Multi-Agent demo，验证"单 Agent → 多 Agent"改造路径。
- **改造路径**（两步走，先轻后重）：
  - 轻量版（推荐先行）：保留主 Agent，计税/社保收进**双子 Agent**（`create_agent` 构建，独立 system prompt + 画像读写 + 领域工具，无 checkpointer 无历史，**全局单例**），包成 `tax_subagent` / `social_subagent` 两个 tool 挂回主 Agent——SSE 协议不变、前端零改动；B 表"先填表再计税"顺序由主 Agent 协调；**`AGENT_MODE` 配置一键切换回纯工具形态（回退/演示）**，**prompt 同步拆两版杜绝"调不到子 Agent"**，**子 Agent 未算出结果时复用 tool_calls 参数直调原工具兜底**
  - 完整版（可选）：Supervisor 模式，主 Agent 做路由分发，子 Agent 并行（⚠️ langgraph-prebuilt 1.1.0 无 `create_supervisor`，需自建 StateGraph，见设计文档 §4.2）
- **改动文件**：新增 `backend/tools/subagents.py`（双子 Agent + 降级）、`backend/eval/multi_agent_eval.py`（主层对拍）、`backend/eval/subagent_eval.py`（子层评测 + 降级用例）；修改 `backend/config.py`（AGENT_MODE）、`backend/agent/prompts.py`（双子 prompt + SYSTEM_PROMPT 拆两版）、`backend/agent/engine.py`（`get_llm()` 单例 + ALL_TOOLS/prompt 同源组装）、`backend/eval/agent_eval.py`（9 条迁名 + B 表用例 + 邻域混淆用例）
- **验收标准**：① 主层对拍 8 条（计税 5+社保 3）数值完全一致；② `agent_eval.py` 20 条迁名后回归 ≥90% 不降；③ 子层 `subagent_eval.py` 内部选工具命中 ≥90%；④ 冒烟：multi 形态计税 3 条 + 社保 2 条 + 检索/填表各 1 条无回归，tools 形态回归现状；⑤ 延迟实测记录（接受 +20-40%）；⑥ `AGENT_MODE=tools` 切换后行为与现状一致；⑦ **一致性硬校验：multi 形态 20 条零 "not registered" 报错、prompt 工具名 100% 注册**；⑧ **降级验证：绕圈用例 100% 复用参数降级成功，数值与直调一致**；⑨ **绕过检测：2 条心算诱导用例 100% 拦截（输出必须带 result_card）**。

### 4.2 ⑤ MCP Server 封装（1-2 天）

- **目标**：把 `calculate_income_tax`（+可选 `query_social_insurance`）封装成标准 MCP Server，验证"任何 MCP 兼容宿主可调用"。
- **改动文件**：新增 `scripts/mcp_server_demo.py`（FastMCP）；测试脚本 `scripts/mcp_client_test.py`
- **实施步骤**：
  1. `pip install mcp`，用 `FastMCP("tax-calc")` 注册工具，复用 `services/tax_engine.py` 核心逻辑（不重复实现）
  2. 启动 server，用 MCP Client 或 `mcporter` 调用验证
  3. 验证后在概念梳理 §5 补一段实战记录
- **验收标准**：① MCP 标准协议下能列出并调用工具；② 计算结果与既有工具一致。
- ⚠️ 注意：MCP SDK 需联网安装，注意答辩环境离线风险——demo 代码入库即可，不引入运行时依赖。

### 4.3 ⑥ 对话历史摘要裁剪（0.5 天）

- **目标**：长对话超限时，把最旧 N 轮压缩成一条 LLM 摘要，替代原始轮次。
- **改动文件**：修改 `backend/agent/engine.py`（新增 middleware 或复用 `trim_messages`）；配合 ② 的 `trim_history()`
- **实施步骤**：① 实现摘要回调（复用 DeepSeek，`temperature=0`）；② 接入 middleware 链；③ 长对话压力测试（20+ 轮）
- **验收标准**：① 历史超 12K token 后触发裁剪；② 裁剪后关键用户信息（城市/工资/扣除项）不丢失；③ 回答质量对拍无明显下降。

---

## 5. P2 — 数据与打磨

### 5.1 ⑦ 用户上下文持久化（grill 定案 2026-08-05：SQLite + 自建消息表 + 历史回显）

> ⚠️ **grill 审查修订（2026-08-05）**：原方案「in-memory dict → MongoDB」被推翻，重新定案为 **SQLite + 自建消息表 + 历史回显**。三个关键发现驱动修订：
> 1. 前端 `useChat.ts:8` thread_id 每次 `crypto.randomUUID()` 刷新即变 → 后端无论存什么都取不回，**必须先前端 localStorage 固定 thread_id**，持久化才有意义（这也是"重启不丢"验收成立的前提）；
> 2. 对话历史天然由 langgraph `InMemorySaver`（engine.py:112）管理，但**不换 Saver，改自建消息表**——消息可读可控、可迁移、可配合评测，且不依赖 langgraph 二进制序列化格式；
> 3. 存储介质选 **SQLite**（标准库零依赖，答辩零风险），MongoDB 降级为"后期迁移"目标——靠 `MemoryStore` 抽象层 + 一次性迁移脚本实现，结构固定可平滑迁移。不引入 Redis（单进程单用户无缓存需求）。

- **目标**：用户画像 + 对话历史双持久化，实现"刷新/重开浏览器后历史回显 + Agent 接着聊"；为登录体系与多用户预留 user 维度。
- **核心设计**：
  - 前端 thread_id 存 localStorage（**单会话模型**：一浏览器 = 一会话，MVP 语义；登录后扩展为 user_id + 多会话）
  - 对话历史自建消息表，**恢复注入复用 SummarizationMiddleware 调用内压缩**（trigger=40K / keep=20，不重写摘要逻辑）
  - `MemoryStore` 接口 + `SQLiteStore` 实现 → 后期换 MongoDB 仅换实现类，业务零改动
  - 画像/消息表**预留 user_id 列**（当前 user_id = thread_id 占位，登录后零返工）
  - `get_llm()` 预留"配置源"接口位（TODO），支持后期切换 DeepSeek key（管理员切换=改配置源；BYOK=登录体系后加密入库）
- **改动文件**：
  - 新增 `backend/storage/sqlite_store.py`（`MemoryStore` 接口 + `SQLiteStore`，sqlite3 标准库，三张表：`user_contexts` / `threads` / `messages`）
  - 修改 `backend/tools/user_context.py`（in-memory dict → MemoryStore，**工具签名与返回格式不变**）
  - 修改 `backend/routers/chat.py`（① 请求前从 SQLite 读历史注入 messages；② 流结束后写回 user 消息 + 拼接的完整回复；③ 新增 `GET /api/chat/history?thread_id=xx`）
  - 修改 `backend/agent/engine.py`（每请求独立 thread_id 防 InMemorySaver 双份累积；`get_llm()` 留配置源 TODO）
  - 修改前端 `src/hooks/useChat.ts`（thread_id localStorage 持久化 + 挂载时 fetch history 渲染）、`src/lib/sse.ts`（新增 `getHistory` API）
- **实施步骤**：
  1. 建表 + `MemoryStore`/`SQLiteStore` 实现（含写锁并发保护）
  2. `user_context.py` 切换存储实现 → 回归验证工具行为不变
  3. `chat.py` 注入/写回逻辑 + `GET /api/chat/history`
  4. `engine.py` 每请求独立 thread_id + 配置源 TODO 位
  5. 前端 localStorage + 历史回显渲染
  6. 验收评测（见下）
- **验收标准**：① 重启后端后同一 thread_id 画像+历史完整恢复；② 刷新页面历史回显 + Agent 接得上话；③ 新浏览器 = 新 thread_id，不串号；④ 工具接口不变；⑤ `agent_eval` 回归 ≥90% 不降；⑥ 20+ 轮长对话摘要正常触发、无消息双份膨胀。
- **工作量**：1.5-2 天（较原 1 天增加：历史回显 API + 注入机制 + 前端改动）。

### 5.2 ⑧ LlamaIndex 对比 demo（半天，可选）

- **目标**：用 lest 现有 115+ 份 Markdown 跑一个 LlamaIndex 版问答 demo，作为论文"技术选型对比"素材。
- **改动文件**：新增 `scripts/llamaindex_demo.py`（独立脚本，不入运行时）
- **验收标准**：同一 query 下 LlamaIndex vs lest 检索效果对比记录（供论文引用）。

### 5.3 ⑨ 评测集扩展 + 评测自动化（1 天）

- **目标**：eval_set.json 40 条 → 60 条（重点补：个体户 B 表、年终奖、汇算清缴案例、专项附加扣除边界值）；把三层评测串成一键脚本。
- **改动文件**：修改 `backend/eval/eval_set.json`（**追加不覆盖**）；新增 `backend/eval/run_all.py`（检索层 + 工具层 + 生成层一键跑）
- **验收标准**：① 新评测集跑通且 recall@5 不降；② `run_all.py` 单命令输出三层报告。

---

## 6. 实施顺序与排期

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
| 余量 | P2 按答辩时间取舍 | ~2 天 | 用户上下文持久化（§5.1）/ LlamaIndex / 自动化 |

> 详细排期与实施顺序见《Context Engineering 集成设计文档》v2.0 §11（含编码 Checklist §12）。

> 建议原则：**每个 P0 项完成即跑一遍评测留下数据**（压缩率、faithfulness、token 用量），这些数字就是答辩和面试的实证素材。

---

## 7. 工程约束（沿用项目既有规范）

1. **文档先行**：每个补充项动手前，先在本规划文档对应小节勾选 ⬜ → 拆分任务（TaskCreate），再写代码
2. **禁止覆写**：评测集等数据资产只追加不覆盖（⑨ 明确标注）；任何改动前先读原文件
3. **评测驱动**：改动后必须跑对应评测（检索层 eval.py / 工具层 agent_eval.py / 生成层 context_eval.py），不达验收标准不算完成
4. **编码规范**：遵循《财务RAG-开发注意事项.md》（CSS 令牌 / API 路由 / 无障碍）与《财务RAG-后端代码审查报告.md》列出的问题清单
5. **新增代码落点**：上下文工程模块统一放 `backend/context/`（对齐概念梳理 §7 的 lest 落点）；demo 类脚本放 `scripts/` 不入运行时
6. **答辩环境约束**：任何新增依赖（MCP SDK / 后期 MongoDB 迁移）不得成为运行时硬依赖，保证"启动 Qdrant + 后端即能演示"（§5.1 定案：MVP 存储用 SQLite 标准库，零外部依赖，天然满足）

---

## 8. 与现有文档的衔接

| 本文档章节 | 上游设计 | 下游产出 |
|---|---|---|
| §3 P0 三件套 | 《求职技术补强-概念梳理》§9.2-9.4 → 《Context Engineering 集成设计文档》（已出） | 编码实现（按设计文档 §9 Checklist） |
| §4.1 Multi-Agent | 《求职技术补强-概念梳理》§3 → **《财务RAG-Multi-Agent 集成设计文档》v1.0（已出）** | 论文"Agent 架构演进"章节素材 |
| §4.2 MCP | 《求职技术补强-概念梳理》§5 | 概念梳理 §5.3 实战记录更新 |
| §5.3 评测扩展 | 《后端开发路线图》Step 6 / 复盘报告 §4.3 | 答辩 PPT"评测驱动迭代"数据 |
| 全篇 | 项目 README 技术栈速览 | README 功能清单更新 |

---

> 执行规则：逐项落地时在本文档勾选状态（🔲 → ✅）并记录实测数据；发现新需求随时追加小节（仅追加，不删除既有内容）。
