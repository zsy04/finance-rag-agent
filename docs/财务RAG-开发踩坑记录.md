# 财务RAG-开发踩坑记录

> 定位：lest 开发过程中遇到的**技术问题与解决方案**档案，供排查复用、演示叙事、文档同步。
> 更新：2026-08-06 追加（设计稿落地联调 3 坑：venv 环境 / curl 中文 / 会话复活）。

---

## 1. 踩坑总表（17 项）

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

---

## 2. 详细记录

### 2.1 `agent.invoke` 同步调用 vs async @tool

- **现象**：基线采集 `agent.invoke()` 时，所有工具报 `StructuredTool does not support sync invocation`，工具从未真正执行（token 曲线失真、画像没存进去）。
- **根因**：lest 的 @tool 全部是 `async def` 定义；`agent.invoke` 走 langgraph ToolNode 的同步执行路径 `_execute_tool_sync`，遇到 async-only StructuredTool 直接抛 NotImplementedError。
- **修复**：采集/测试脚本统一用 `await agent.ainvoke(...)` + `asyncio.run(main())`（与生产 `astream_events` async 链路一致）。
- **影响**：任何用 `agent.invoke`（同步）跑 lest Agent 的脚本都会踩——包括 `eval/agent_eval.py`（它目前用 invoke，但因其只统计"工具选择"不执行工具结果，暂未受影响）。
- **涉及文件**：`scripts/collect_baseline.py`、`scripts/test_summarizer.py`。

### 2.2 transformers 5.14.1 强制联网检查 repo

- **现象**：`BGEM3FlagModel` 加载时，即使模型在 `~/.cache/huggingface/hub/` 完整，`AutoTokenizer.from_pretrained` 仍走 `list_repo_templates()` 联网 GET huggingface.co，离线环境 `ConnectTimeout` 卡 10-30 秒/次。
- **根因**：transformers 5.14.1（2025 后新版本）在 `from_pretrained` 流程中强制检查 repo 的 tokenizer 模板，且该路径**不遵守 `HF_HUB_OFFLINE`**（huggingface_hub 的 offline 标志对 `hf_api().list_repo_tree` 直接调用不生效）。
- **修复**：设 `TRANSFORMERS_OFFLINE=1`（transformers 自己的离线标志，会跳过模板检查）。**`HF_HUB_OFFLINE` 单独不够**。
- **影响**：生产环境首次调用 `search_knowledge` 同样会卡——这是潜伏的生产 bug，修复对所有入口有效。

### 2.3 HF 离线环境变量设置时机

- **现象**：`retriever.py` 顶部 `os.environ.setdefault("HF_HUB_OFFLINE", "1")` 已加，但进程仍联网超时。
- **根因**：`huggingface_hub.constants` 在 **import 时**快照 `HF_ENDPOINT`/offline 标志；脚本先 `import agent.engine`（langchain 链提前把 hf_hub 拉进内存），之后 retriever.py 里的 setdefault 已无效。
- **修复**：环境变量必须在**任何第三方 import 之前**设置——`collect_baseline.py` / `test_summarizer.py` 顶部（`import os` 后立即）设置 `HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1`。
- **影响**：所有入口脚本都要遵守"env 先于 import"原则；retriever.py 内的设置仅对"直接 import retriever"的路径有效。

### 2.4 场景 turns 与 facts 不匹配

- **现象**：s3 场景 probe 命中仅 25%——facts 里的 `salary=15000`、`deduction_mortgage=1000` 在 turns 中从未出现，LLM 无从答起；s1 的子女教育/赡养金额缺失；income_type 期望值 "salary" 与中文回答"工资"不匹配。
- **根因**：场景数据构造时 facts（关键事实清单）与 turns（对话轮次）脱节。
- **修复**：① turns 补全金额表述（"我有个孩子上小学，每月教育支出1000"等）；② income_type 期望值改中文（工资/经营）；③ 新增 **facts↔turns 自动匹配校验**（脚本启动时断言每个 fact 值出现在 turns 文本中）。
- **影响**：评测集构造必须保证"预期值在输入中可被找到"，否则评测结果无效。

### 2.5 宽松摘要 prompt 漏扣除金额

- **现象**：s1 的 `children_edu=1000`（轮6）、`elderly_support=2000`（轮8）在 keep=10/20/30 **三档全败**。
- **根因**：这些轮次落在"被摘要化的 older 部分"，宽松式摘要 prompt（"必须保留扣除项"）不够强制，摘要 LLM 漏掉了金额。
- **修复**：`CUSTOM_SUMMARY_PROMPT` 升级为**逐字段清单核对式**——列出 CONTEXT_KEYS 12 字段逐一自查（"输出前逐项自查：清单里每个出现过的字段是否都已写入摘要"）。
- **影响**：财税摘要的保真度是真实风险；ContextEvaluator 的字段校验正是为此把关（评测闭环价值实证）。

### 2.6 官方 token 计数器低估中文

- **现象**：集成测试 20 轮历史涨到 70.5K 爆窗，trigger=40K **永不触发**（context 事件 0 次）。
- **根因**：`langchain.agents.middleware.summarization.count_tokens_approximately` 默认 `chars_per_token=4.0`（英文口径 4 字符=1 token）；中文 1 字≈1.75 token，被低估约 2.3 倍——s1 真实 70K token（≈40K 字）官方只算 ~10K。
- **修复**：`HistorySummarizer.__init__` 传 `token_counter=_count_tokens_zh`（中文口径 `len(content)×1.75`，**与基线 est_tokens 完全一致**，trigger=40K 才有意义）。
- **影响**：任何用官方计数器 + 中文内容的 trigger/预算配置都必须自定义计数器，否则阈值全部失真。

### 2.7 middleware 挂载验证误判（排查教训）

- **现象**：集成测试未触发摘要，排查时打印节点过滤 `'Summarization' in n` 无结果，误判"middleware 没挂载"。
- **根因**：节点命名用**自定义类名** `HistorySummarizer.before_model`（不是父类名 SummarizationMiddleware），过滤词没匹配。
- **修复**：完整打印所有节点确认（`HistorySummarizer.before_model` 实际存在）；验证关键词用类名而非父类名。
- **影响**：验证 middleware 挂载时要看完整节点名；本项目命名 HistorySummarizer 后节点即 HistorySummarizer.before_model。

### 2.8 改代码后行为未变（.pyc 排查）

- **现象**：用户进程 traceback 行号显示旧代码（retriever.py line 84），怀疑旧 .pyc 缓存。
- **根因**：实际根因是 #3（env 时机，进程启动早于修复）；.pyc 为排查中的排除项。
- **处理**：清理 `rag/__pycache__/retriever*.pyc`（无害）；确认代码热更新用"重启进程"而非依赖缓存。
- **影响**：Python 进程启动时加载模块，改代码后必须重启；.pyc 缓存一般自动失效，无需手动清理。

### 2.9 `agent.nodes["model"]` 无 .model 属性

- **现象**：尝试从 agent 图取内部 LLM 失败：`PregelNode object has no attribute 'model'`。
- **修复**：不依赖内部结构，按 `config` 独立重建 `ChatOpenAI`（同 key/模型，temperature=0）。
- **影响**：从 CompiledStateGraph 拿内部组件是不可靠的，需要 LLM 时应独立构造。

### 2.10 模型离线加载仍 18.7s

- **现象**：TRANSFORMERS_OFFLINE 生效后 tokenizer 加载仍需 18.7s。
- **根因**：首次加载模型权重文件（391/393 个权重文件读取），非网络问题；进程常驻后单例复用。
- **缓解**：采集/测试脚本启动时**预加载检索器**（`get_retriever()`），把加载耗时从"首轮工具调用"提前到"启动阶段"，避免污染首轮工具结果与曲线。

---

## 3. 预防清单（通用原则，写新代码前过一遍）

1. **async 工具 → 必须 ainvoke**：lest 全部 @tool 是 async，任何脚本/测试用 `agent.invoke` 都会工具全失败
2. **HF env 先于 import**：`HF_ENDPOINT`/`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` 必须在脚本最顶部、任何第三方 import 之前设置（hf_hub 快照时机）
3. **中文内容必须自定义 token 计数**：官方 `count_tokens_approximately` 是英文口径，中文低估 2.3 倍；口径必须与基线数据一致
4. **评测集 facts 必须可寻**：expected 值必须出现在输入 turns 中（自动校验）
5. **验证挂载看完整节点名**：middleware 节点用自定义类名命名
6. **改代码后重启进程**：Python 进程不热更新

---

## 4. 与文档体系的同步点

| 本文档条目 | 同步到 |
|---|---|
| #2 #3（transformers/HF env） | 集成设计文档 v2 §5（采集链路坑）、retriever.py 注释 |
| #5（摘要漏金额） | 集成设计文档 v2 §3.4（清单式 prompt）、§5 |
| #6（token 口径） | 集成设计文档 v2 §3.2（HistorySummarizer 配置注明 token_counter 必须中文口径） |
| #11（摘要 trim 砍头部） | 集成设计文档 v2 §3.3（HistorySummarizer 配置注明 trim_tokens_to_summarize=None） |
| #4 #9 #10 | 集成设计文档 v2 §5（采集流程留档） |
| 全部 | 本档案为最终权威来源，排查问题时先查此表 |

### 2.11 官方摘要 trim 默认砍早期画像轮（⚠️ 隐蔽）

- **现象**：context_eval v2 重跑，s1/s2/s3 摘要仍丢早期画像（城市/工资/扣除项）——即使摘要 prompt 已强制"数值必保"；唯独信息密度低的 s4 全对。
- **根因**：`SummarizationMiddleware._trim_messages_for_summary` 默认 `trim_tokens_to_summarize=4000` 且 `strategy="last"`（保留**末尾/最近**消息）。信息密度高的对话（轮 1-9 含大量工具结果，30-40K token）超限后被裁剪——**最早的画像轮（轮 1-3 的城市/工资/扣除项）被直接砍掉，摘要 LLM 根本看不到**，与摘要 prompt 无关。
- **修复**：`HistorySummarizer.__init__` 传 `trim_tokens_to_summarize=None`（跳过 trim，全量喂摘要 LLM；摘要输入 ~40K token ≈ ¥0.04/次，成本可接受）。
- **规律**：官方中间件"最近优先"的默认策略与"画像在早期轮次"的 lest 场景天然冲突；凡依赖官方 middleware 处理长历史，必须检查其内部裁剪/保留策略。

### 2.12 `pip install mcp` 默认装 2.0.0，`mcp.server.fastmcp` 已移除（⚠️ 版本坑）

- **现象**：`pip install mcp` 成功后，`from mcp.server.fastmcp import FastMCP` 抛 `ModuleNotFoundError`；`mcp.server` 下只剩 `apps / lowlevel / mcpserver / stdio` 等新模块。
- **根因**：mcp 2.0.0（2026 大重构）将内置 FastMCP 移出官方 SDK（FastMCP 独立成包维护），经典 `FastMCP` API 只存在于 1.x。
- **修复**：`pip install "mcp==1.29.0"`（1.x 最终版），脚本零改动；若重装/换环境务必指定版本。
- **规律**：快速上手的框架库，`pip install <pkg>` 拉到的 may be breaking change——装完第一件事先 `import` 验证再写业务代码。

### 2.13 评测汇总把百分比数值当比例格式化（显示层 bug）

- **现象**：run_all.py 三层汇总报告里，工具层 accuracy 显示 `10000.00%`（实际 26/26 = 100%），达标判断却正常。
- **根因**：agent_eval_report.json 的 `accuracy` 存的是 0-100 数值（`round(100.0,1)`），而 run_all.py 汇总打印对 float 统一用 `:.2%`（0-1 比例格式）→ 100.0 被乘 100。
- **修复**：打印按字段值域区分——`accuracy`→`%.1f%`；`recall/mrr/ndcg/probe/faithfulness/context_event_rate`（0-1 比例）→`%.2%`。
- **规律**：跨模块聚合数值时，先确认数据源字段的值域（比例 vs 百分数）再统一格式化，勿假设同构。

### 2.14 超长法规多 chunk 挤占 top5 槽位（检索器真实缺陷）

- **现象**：60 条评测首跑 #47（年终奖合并 vs 单独计税）miss——top5 中 4 个都是《个人所得税法》的不同 chunk，《百问百答》被挤出前五；修复标注后仍未全命中。
- **根因**：`retriever.retrieve()` 链路为"Reranker 精排 → 直接截 top_k"，无**文档级去重**。超长法规（如个税法）切多 chunk 后，Reranker 对同一文档的多个 chunk 打高分 → 挤占其他文档槽位（Recall@5 全局 72.5% → 修复后 85%）。
- **修复**：`retrieve()` 精排放宽取 `top_k*2` → 按 `doc_title` 去重（同文档只留最高分 chunk）→ 截断 top_k。同时修正 3 条评测标注（#45/#47/#56 的 expected_docs 关联判断失误）。
- **规律**：混合检索 + 重排的 pipeline，务必在最终截断前做**文档级去重**——评估指标（recall/precision）和 LLM 上下文质量都按"文档"计，不按"chunk"计。

### 2.15 系统 Python 与 venv 版本不一致 → ImportError（环境坑）

- **现象**：`python -m uvicorn main:app` 启动报 `ImportError: cannot import name 'ToolErrorMiddleware' from 'langchain.agents.middleware'`；用系统 Python（3.13）导入 langchain.agents 冷启动耗时 13s。
- **根因**：项目后端依赖装在 `backend/venv`（langchain 1.3.14，含 `ToolErrorMiddleware`）；系统 Python 里是 langchain 1.3.12（该 middleware 叫 `ToolRetryMiddleware`）。两套环境并存，用错环境即崩。
- **修复**：统一用 `backend/venv/Scripts/python.exe` 启动（start.bat 已如此）；venv 缺 `markdown` 模块，`pip install "markdown~=3.8.0"` 补齐。
- **规律**：多环境机器先确认 `which python` / 项目 README 指定的解释器；`import` 验证依赖版本再跑服务。

### 2.16 Windows curl 中文查询参数被编码破坏（联调坑）

- **现象**：`curl "localhost:8000/api/library/documents?category=法律"` 返回空（JSON 解析失败），而 Python urllib 请求正常。
- **根因**：Windows Git Bash 下 curl 直接拼接中文参数时 shell 编码与 URL 编码冲突，中文字节被破坏 → 服务端收不到合法参数。
- **修复**：`curl -G --data-urlencode "category=法律"`，或直接用 Python urllib/requests 验证；前端侧 fetch + `encodeURIComponent` 天然正确。
- **规律**：联调脚本含中文参数，先确认客户端编码；用 `--data-urlencode` 最稳。

### 2.17 删除会话后"复活"——localStorage 残留 thread_id 触发后端自动重建（状态同步坑）

- **现象**：删除一个会话后，再次对话时被删会话又出现在左侧列表里。
- **根因**：前端 `localStorage`（key=`lest_thread_id`）保存当前 thread_id；删除会话后若该 tid 仍残留（挂载/刷新时机），下次发消息 → 后端 `append_message → ensure_thread`（`INSERT OR IGNORE INTO threads`）**自动重建**已被删的 thread 记录 → 列表复活。后端 `delete_thread` 本身已彻底（messages+contexts+threads 三删，幂等 200）。
- **修复**（`useChat.ts` 挂载逻辑）：拉取会话列表后**校验当前 tid 是否仍存在**——不在则切到最新会话（或新建空会话）并同步 localStorage，从源头杜绝用已删 tid 发消息。
- **规律**：本地持久化 + 服务端权威状态的场景，前端挂载时必须做"本地 id 有效性校验"，否则删除类操作会被后续写入隐式撤销。
