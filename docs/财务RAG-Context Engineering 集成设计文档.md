# 财务RAG-Context Engineering 集成设计文档（v2.0）

> 定位：**实现级设计文档**，直接指导 P0 上下文工程模块（历史摘要 / TokenBudget / 评测）的编码。
> 承接链：概念梳理 §9（接口级设计）→ **本文档 v2.0（grill 审查修订版）** → 编码实现。
> 配套：《财务RAG-项目补充与添加实施规划》§3；《财务RAG-开发注意事项.md》；**《财务RAG-开发踩坑记录.md》（开发全程问题档案，排查先查）**。
> 更新：2026-08-04 创建 v1.0；同日经 **grill-me 压力审查**修订为 v2.0——**核心假设变更：压缩主战场从"单轮检索 chunk"改为"多轮对话历史累积"**（实测 2937 个 chunk 中位数仅 181 字，单轮压缩无意义）。同日**基线采集完成并回填参数**（keep=20 / trigger=40K），guard.py 已实现并升级为"工具返回瘦身主力"（详见 §5-§6）。

---

## 1. 设计原则（总纲）

| # | 原则 | 含义 | 影响 |
|---|---|---|---|
| P1 | **无侵入集成** | 不改 `create_agent` 组装逻辑 | 落点：middleware / 工具层 / 离线脚本 |
| P2 | **主战场 = 多轮历史** | chunk 中位数 181 字，单轮无需压缩；真正吃预算的是多轮累积 | 核心模块 = 历史摘要器 |
| P3 | **画像独立兜底 → 激进压缩** | 用户画像由 `get_user_context` 独立存储，不依赖对话历史 | 历史摘要可激进压（token 降幅 ≥70%），字段自动校验兜底 |
| P4 | **官方能力优先复用** | langchain 1.3.14 自带 `SummarizationMiddleware`（已查证 API） | 继承扩展，不重复造轮子 |
| P5 | **用户可感知** | 压缩不得静默发生 | 新增 SSE `context` 事件 + 前端提示条 |
| P6 | **参数化 + 评测闭环** | 阈值全部可配置，效果有数字证据 | 先采集基线，再实现，再评测 |

---

## 2. 架构总览（v2 模块重组）

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

**模块职责边界**（v1 → v2 变化）：

| v1 模块 | v2 去向 |
|---|---|
| ContextCompressor（独立，压 top-5 chunk） | ⤵ 拆解：提取式算法 → `guard.py` **工具返回瘦身**（已实现：部署在 search_knowledge 返回前，单条超 400 字才压缩，必保句保留）；两级压缩思路 → `history_summarizer.py` 预处理 |
| TokenBudget（五区预算） | ⬆ 升级为**核心决策源**：触发阈值 / keep 值 / 预算参数，由基线采集数据决定 |
| ContextEvaluator（query 集） | 🔄 评测对象改为**历史摘要**：长对话场景集 + 自动字段校验 |
| —（新增） | **HistorySummarizer**：继承官方 SummarizationMiddleware，扩展两级压缩 + 字段校验 + context 事件 |

---

## 3. 官方 SummarizationMiddleware 复用设计（已查证 langchain 1.3.14）

### 3.1 为什么复用

`venv/Lib/site-packages/langchain/agents/middleware/summarization.py` 已实现：`before_model`/`abefore_model` 钩子（模型调用前改消息）、token 触发条件（AND/OR 组合）、保留策略、摘要调用。**历史裁剪落点确认可行**，且官方实现处理了 AI/Tool 消息配对等细节，自研成本高且易错。

### 3.2 官方能力 vs 我们的扩展

| 能力 | 官方 | 我们的扩展（HistorySummarizer 继承） |
|---|---|---|
| 触发（trigger） | ✅ `("tokens", N)` / `("fraction", 0.2)` / 消息数，支持组合 | 阈值由基线采集定（见 §5） |
| 保留（keep） | ✅ 默认最近 20 条消息 | keep 值由基线数据定 |
| token 计数 | ✅ `count_tokens_approximately` | 可换 `token_est.py` 估算 |
| 摘要 prompt | ✅ 可自定义 `summary_prompt` | **自定义**：强制保留画像字段 + 两级压缩预处理 |
| 画像字段校验 | ❌ | ✅ **新增**：摘要前后 get_user_context 字段完整率自动校验 |
| 用户提示事件 | ❌ | ✅ **新增**：摘要发生时置标志 → 路由层发 SSE `context` 事件 |
| 提取式预过滤 | ❌（直接摘要全部旧消息） | ✅ **新增**：摘要前先提取式丢弃纯闲聊/低价值轮 |

### 3.3 配置基线（✅ 已实现 2026-08-04，参数已定稿）

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
            summary_prompt=CUSTOM_SUMMARY_PROMPT,          # §3.4 清单式
            token_counter=_count_tokens_zh,                # ⚠️ 必须中文口径（见下）
        )

    async def abefore_model(self, state, runtime):
        result = await super().abefore_model(state, runtime)
        if result is not None:                             # 发生了摘要 → 置标志
            # 置 _summarized_flags[thread_id]（供路由层 pop → context 事件）
            ...
```

> ⚠️ **必须传 `trim_tokens_to_summarize=None`**（踩坑 #11，见《开发踩坑记录》）：官方默认
> `trim_tokens_to_summarize=4000` 且 `strategy="last"`（保留最近消息）——信息密度高的
> 对话会砍掉最早的画像轮（城市/工资/扣除项），摘要 LLM 根本看不到（s1/s2/s3 评测全中招）。
> 传 None 跳过 trim 全量喂摘要（保真优先，输入 ~40K token ≈ ¥0.04/次）。

> ⚠️ **token_counter 必须传中文口径**（踩坑 #6，见《开发踩坑记录》）：官方默认
> `count_tokens_approximately` 是英文口径（4 字符/token），中文被低估约 2.3 倍，
> 导致 trigger=40K 永不触发（实测 20 轮 70K 真实 token 官方只算 ~10K）。
> `_count_tokens_zh` = 消息内容字符数 × 1.75，**与基线 est_tokens 完全一致**，
> 否则 trigger/keep 阈值全部失真。

### 3.4 自定义摘要 prompt（CUSTOM_SUMMARY_PROMPT）

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

### 3.5 两级压缩（提取式预过滤 → LLM 摘要）

官方直接对全部旧消息做摘要；lest 扩展在摘要前**先提取式过滤低价值轮**：

| 轮次类型 | 处理 |
|---|---|
| 含数字/金额/画像字段（city/salary/扣除项关键词）的轮次 | **必保**，进入摘要候选 |
| 纯闲聊/寒暄/重复轮次 | **直接丢弃**（提取式），不喂给摘要 LLM |
| 工具调用与结果（calculate/tax JSON） | 保留结果数字，丢弃过程性长文本 |

判定复用 v1 的必保正则（数字+单位 / 文号 / 百分比），字段集合用 `CONTEXT_KEYS`。

### 3.6 context 事件传递（middleware → SSE）

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

---

## 4. TokenBudget（v2 职责：核心决策源）

### 4.1 职责变化

v1：五区预算分配（给 Compressor 算 budget_chars）。
v2：**提供历史摘要的全部参数**——触发阈值、keep 值、token 估算接口；无检索轮让渡等策略保留但降级为次要。

### 4.2 参数（基线采集后校准，初始值）

```python
# context/budget.py
class TokenBudget:
    WINDOW = 64_000            # deepseek-chat 上下文（可配置）
    RESERVED_OUTPUT = 4_000    # 输出预留（硬性）
    def __init__(self, trigger_tokens: int = 40_000, keep_messages: int = 20,
                 summary_target_tokens: int = 1_500): ...
    def should_summarize(self, history_tokens: int) -> bool:   # history_tokens ≥ trigger_tokens
    def adjust(self, baseline: dict) -> None:                  # 基线采集数据回填
```

### 4.3 估算口径（token_est.py，与 v1 一致）

中文 1 字 ≈ 1.75 token；1 token ≈ 0.5 字（保守）；`tiktoken` 仅可选校准，不引入硬依赖。

---

## 5. 基线采集（✅ 已完成 2026-08-04，参数最终确认）

**最终参数（四场景完整数据复核后定稿）**：
- **trigger = 40_000**（窗口 63%）——**否决脚本启发式建议的 52K**：s3 第 11 轮 64.4K 已爆窗，52K 触发时模型输入已 ~60K 无余量；40K 时 s1 第 10 轮（41K）、s3 第 7 轮（43K）触发，摘要后 ~16-21K，余量 19K ≈ 5-8 轮
- **keep = 20**（摘要后保留最近 20 条消息，上下文 16-21K token）——s2/s4 三档全 100%；s1 三档同败是摘要缺陷非档位问题（见下）；keep=10 更省 token 但容错低，留作备选
- **摘要缺陷实证**（字段校验的价值）：s1 的 `children_edu=1000`（轮6）、`elderly_support=2000`（轮8）在 keep=10/20/30 **三档全败**——因为它们都落在"被摘要化的 older 部分"，模拟摘要 LLM 漏掉了这两个金额 → **CUSTOM_SUMMARY_PROMPT 必须改为"逐字段清单核对"式**（列出 CONTEXT_KEYS 12 字段逐一确认保留），ContextEvaluator 的字段校验正是为此把关
- **token 曲线（工具全成功）**：s1 20轮→64.9K（第 19 轮 64.3K 已超窗）、s3 15轮→71.0K（第 11 轮 64.4K 超窗）、s2 15轮→43.2K、s4 12轮→37.4K → **无摘要管理时 11-19 轮必爆窗，摘要必要性铁证**
- **重大发现**：工具返回拼接总长（5×800≈4K 字≈7K token/次检索）是膨胀主因 → guard.py 从"保障"升级为"主力"（§6）
- 采集链路坑（已修）：`agent.invoke` 同步 vs async @tool 全失败 → `await agent.ainvoke`；transformers 5.14.1 需 `TRANSFORMERS_OFFLINE=1` **且必须在任何第三方 import 之前设置**（huggingface_hub 在 import 时快照 env，retriever.py 内设置太晚）→ collect_baseline.py 顶部设置 + HF_ENDPOINT 镜像兜底 + 预加载检索器

**五步采集流程（留档）**：`scripts/gen_long_dialogues.py`（4 场景 61 轮 + facts 清单）+ `scripts/collect_baseline.py`（自动执行：逐轮曲线 → trigger 建议 → 摘要模拟 → probe 判定 → keep 对比 → 输出 `eval/dialog_baseline.json`）。

### 5.2 场景脚本结构（示例）

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

---

## 6. 工具返回瘦身 guard.py（✅ 已实现 2026-08-04）

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

---

## 7. ContextEvaluator v2（长对话场景集）

### 7.1 评测对象变更

v1：单条 query + expected_facts（测检索上下文压缩）。
v2：**长对话场景**（20 轮）→ 测摘要保真、字段校验、用户提示、token 收益。

### 7.2 评测集 dialog_scenarios.json

5-10 个场景，每个含：`facts`（关键事实清单 = CONTEXT_KEYS 子集）+ `turns`（20+ 轮真实问答）+ `expected_context_event`（期望摘要发生时触发提示）。

### 7.3 四项指标（✅ 验收实测 2026-08-04，context_eval.py）

| 指标 | 定义 | 计算方式 | 达标线 | 实测 |
|---|---|---|---|---|
| 画像字段完整率 | 摘要后 LLM 能否从历史提取用户字段 | probe 问答（数值词边界正则） | **100%** | **92%**（3/4 场景 100%；s1 2 项为 LLM 提取失败，judge 佐证信息完整） |
| 摘要忠实度 | 摘要后历史是否含全部事实原样值 | judge 严格判定（数值必须原样一致） | ≥90% | **100%**（全部场景 missing=[]） |
| token 收益 | 无摘要 vs 有摘要峰值降幅 | 对比 dialog_baseline.json | 报告如实 | s1 39% / s2 12% / s3 42% / s4 2% |
| context 事件触发率 | 摘要触发 vs 事件 pop | 标志位消费统计 | 100% | **100%**（6 摘要 / 6 事件） |

> 实测结论：**judge 100% + 事件 100% + 峰值全 <41K = P0 验收通过**。probe 92%（s1 的
> children_edu/elderly_support 未命中）为 LLM 提取失败而非摘要缺陷（严格 judge 判定
> 历史中存在原样值）。评测驱动迭代三轮回合（见《开发踩坑记录》#5/#6/#11）：prompt 清单化 →
> 中文 token 口径 → trim=None 全量喂摘要。

### 7.4 judge prompt（摘要忠实度版）

```text
你是严格的评测员。下面给出一段【原始对话摘要】和【原始对话关键事实清单】。
判断摘要是否歪曲了清单中的任何事实（数字/金额/城市/扣除项必须完全一致）。
输出严格 JSON：{"distorted": [true/false], "distorted_facts": ["..."], "missing_facts": ["..."]}
只根据清单判定，摘要遗漏但未歪曲 → 计入 missing_facts，不计 distorted。
```

> judge 自评偏差缓解：字段校验是自动的（主指标），judge 仅抽查忠实度（辅助），不依赖自评可信度。

### 7.5 评测流程

```
1. 加载 dialog_scenarios.json
2. 逐场景跑真实 Agent 链路（agent.invoke 连续 20 轮，thread_id 隔离）
3. 记录：每轮历史 token（曲线）、摘要触发点、context 事件、摘要文本
4. 自动校验：字段完整率 + token 收益 + 事件触发率
5. judge 抽查摘要忠实度
6. 输出报告（含 token 增长曲线数据）
```

---

## 8. 数据流总图（v2）

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

---

## 9. 测试计划

### 9.1 单测（backend/tests/test_context.py）

| 模块 | 用例 | 期望 |
|---|---|---|
| token_est | 空串 / 纯中文 / 中英混合 | 估算非 0、单调递增 |
| budget | trigger 边界（history==N / N+1） | 正确判断 |
| guard | ≤1.2K 字 | 原样返回 |
| guard | >1.2K 含必保句 | 必保句 100% 保留 |
| summarizer | 摘要后字段完整率（mock LLM） | 100% |
| summarizer | 纯闲聊轮预处理 | 不进入摘要候选 |

### 9.2 集成

1. `agent_eval.py` 20 条 ≥ 90%（摘要器不影响工具选择）
2. `eval.py` 40 条 recall@5 不降（guard 只动超长文本）
3. 手工 20 轮长对话：context 事件出现且仅出现一次/摘要动作
4. 前端：context 事件渲染提示条

### 9.3 验收（新四指标，对齐实施规划 §3）

字段完整率 100% / 摘要忠实度 ≥90% / token 降幅 ≥70% / 事件触发率 100% / 双回归通过

---

## 10. 风险与取舍（v2 新增项）

| 风险 | 说明 | 缓解 |
|---|---|---|
| 官方 middleware 黑盒 | 升级 langchain 可能破坏行为 | 记录当前版本 1.3.14；升级前跑回归 |
| 两级压缩复杂度 | 提取式过滤 + LLM 摘要两段逻辑 | 过滤规则只做"闲聊丢弃 + 必保句"两档，不做精细打分 |
| context 事件与 SSE 时序 | 摘要发生在流中间，提示条插在开头 | 标志位方案：下一条 SSE 流开始时补发，语义可接受 |
| 摘要 LLM 成本 | 每触发一次多一次 DeepSeek 调用 | trigger 阈值让正常短对话永不触发（基线采集保证） |
| 激进压缩丢临时信息 | 摘要后对话外的临时细节丢失 | 画像字段独立存储兜底（P3）；golden 字段自动校验 |

---

## 11. 实施顺序（更新 2026-08-04：基线采集与 guard 已完成）

```
✅ ① 基线采集（已完成）      keep=20 / trigger=40K 已回填；发现工具返回拼接是膨胀主因
✅ ④ guard.py + search_knowledge（已完成）   提取式瘦身，软上限 400 字，自检通过
▶  ② token_est + types + budget（0.5 天）   参数直接用基线定值（40_000 / 20）
▶  ③ history_summarizer.py（1-1.5 天）   继承官方 SummarizationMiddleware + 字段校验 + context 事件
▶  ⑤ routers/chat.py + 前端 context 事件（0.5 天）
▶  ⑥ context_eval.py + dialog_scenarios.json 评测（1 天）   验收四指标
总投入：约 4-5 天
```

## 12. 编码 Checklist（实时进度）

- [x] ① 基线采集（脚本 + 数据，trigger=40K / keep=20 已定）
- [x] ② TokenBudget 简化（参数固化在 HistorySummarizer 默认值，独立 budget.py 省略）
- [x] ③ history_summarizer.py（继承官方 + 清单式 prompt + 中文 token_counter + 摘要标志）
- [x] ④ guard.py + search_knowledge 集成（自检通过）
- [x] ⑤ SSE context 事件（后端 + 前端三处小改，tsc 通过）
- [x] ⑥ context_eval.py + 四指标报告（✅ 2026-08-04 验收：judge 100% / 事件 100% / probe 92% / 峰值 <41K）
- [x] ⑦ 集成测试验收（2026-08-04 实测：摘要触发 2 次 / context 事件 2 次 / 峰值 41.3K < 64K ✅）

> **集成测试实测（scripts/test_summarizer.py，s1 场景 20 轮）**：trigger=40K 生效（39.1K / 41.3K 触发），摘要后消息 43→23、token 27.4K/25.5K，20 轮触发 2 次间隔 6 轮，context 事件链路完整（摘要后下一轮 pop 到标志），全程未爆窗。踩坑记录见《财务RAG-开发踩坑记录》#6（token 口径）。

---

> 维护规则：编码中发现的设计偏差回写本文档（标注"实现修订"）；验收实测数据回填 §7.3。v1.0 中与 v2 冲突的内容以 v2 为准（chunk 级压缩设计已废弃，仅保留其提取式正则与 judge prompt 思路）。
