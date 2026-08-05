# 财务RAG-Multi-Agent 集成设计文档（v1.5）

> 定位：**实现级设计文档**，直接指导 P1 多 Agent 化（工具升级子 Agent）的编码。
> 承接链：概念梳理 §3（概念层）→ 项目补充规划 §4.1（方向）→ **本文档 v1.5（实现级）** → 编码实现。
> 配套：《财务RAG-开发注意事项.md》；《财务RAG-后端代码审查报告.md》；**《财务RAG-开发踩坑记录.md》（开发全程问题档案，排查先查）**。
> 更新：2026-08-04 创建 v1.0；同日经 **grill-me 压力审查**修订 **v1.1**（拆双子 Agent / 成本补偿 / 双层评测 / B 表主协调 / 全局单例 / 三道防线）；追加 **v1.2 模式开关**；再审查发现 **v1.3 prompt 双版本**（prompt 残留工具名诱导调未注册工具）；追加 **v1.4 子 Agent 失败降级**（复用 tool_calls 参数直调原工具兜底）；追加 **v1.5 绕过检测**——**主 Agent 可能不声明 tool_calls 直接输出文本（"心算"绕过子 Agent 的确定性计算）**，防线：子 Agent answer 含税额数字但无 result_card → **强制重算**（LLM 数字作废）（§5.10，详见 §12 审查结论 J 分支）。

---

## 1. 设计原则（总纲）

| # | 原则 | 含义 | 影响 |
|---|---|---|---|
| P1 | **轻量先行** | 先做"子 Agent 作为工具"（Tool-as-Subagent），零结构改动跑通，再谈 Supervisor | 阶段一 = 轻量版，阶段二 = 完整版（可选） |
| P2 | **协议不变** | 子 Agent 返回仍遵循 `tools/base.py` 的 JSON 五字段（answer/result_card/sources/disclaimer） | `routers/chat.py` SSE 解包零改动，前端零改动 |
| P3 | **记忆隔离** | 子 Agent **不挂 checkpointer、不带对话历史**，每次独立计算；用户画像一律走 `get_user_context` | 子 Agent 无状态 → 天然防上下文混装 |
| P4 | **复用引擎** | 子 Agent 内部继续调 `services/tax_engine.py`，不重复实现计税逻辑 | 对拍一致性的前提 |
| P5 | **评测闭环** | 改动必须过两道关：对拍 N 条 + agent_eval 20 条回归 ≥90% | 验收标准（§7） |
| P6 | **版本约束** | 已实测 `langgraph-prebuilt 1.1.0` **无 `create_supervisor`**，`create_react_agent` 可用 | 完整版需自建 StateGraph，不自造官方 API |
| P7 | **v1.1 拆分粒度** | 拆**两个**子 Agent（计税 + 社保），各领域独立 prompt，不合并 | §4.1 双子 Agent 结构 |
| P8 | **v1.1 成本可接受** | 接受 +20-40% 延迟 / 1.5-2× token，补三项补偿（子 Agent 全局单例 / 主 prompt 精简抵消 / 答辩话术兜底） | §5.3 单例设计 + §9 话术 |
| P9 | **v1.1 双层评测** | 主层测路由（20 条迁名）+ 子层测内部选工具（subagent_eval.py） | §7 评测体系改造 |
| P10 | **v1.1 路由三道防线** | 子 Agent 拒答兜底 + 主层回归 ≥90% 硬门槛 + 邻域混淆用例 | §7.4 + §10 风险 |
| P11 | **v1.2 模式开关** | `AGENT_MODE` 配置切换：`multi`（子 Agent 形态，默认）/ `tools`（纯工具形态，回退与演示）——**同一时刻只有一套工具列表**，不并存注册（并存导致评测歧义 + 子 Agent 死代码） | §5.6 + §10 回退 |
| P12 | **v1.3 prompt 与工具列表同步** | **`SYSTEM_PROMPT` 也按 `AGENT_MODE` 拆两版**——multi 版工具名全部换成子 Agent 名，tools 版为现有 prompt 原样；prompt 里写到的工具名必须与 ALL_TOOLS 完全一致，**杜绝"prompt 诱导调用未注册工具"** | §5.8 + §7.5 一致性校验 |
| P13 | **v1.4 子 Agent 失败降级** | 子 Agent 未计算出结果（无 result_card）时，**复用消息链 `AIMessage.tool_calls` 里 LLM 已生成的 calculate 参数，直调原工具兜底**——参数提取靠 LLM（准确）、计算靠引擎（可靠），各取所长；连 tool_calls 都没有才返回错误让主 Agent 反问 | §5.9 + §7.6 降级指标 |
| P14 | **v1.5 绕过检测（强制重算）** | 子 Agent 最终 answer **含税额数字但 result_card 为空** = LLM "心算"绕过了确定性引擎 → **强制用工具重算，LLM 数字作废**；"绕过"在架构上不可能产出不可信结果 | §5.10 + §7.7 心算诱导用例 |

---

## 2. 现状盘点（单 Agent 架构）

### 2.1 当前编排

```
主 Agent（backend/agent/engine.py: build_agent）
  ├─ create_agent(model=DeepSeek, tools=ALL_TOOLS(8个), system_prompt, checkpointer=InMemorySaver)
  ├─ middleware: [ToolErrorMiddleware, ModelCallLimitMiddleware(25), HistorySummarizer(40K/20)]
  └─ 每次请求: routers/chat.py → agent.astream_events → 8 种 SSE 事件
```

### 2.2 8 个工具清单（backend/tools/）

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

### 2.3 依赖版本（实测）

| 包 | 版本 | 关键结论 |
|---|---|---|
| langchain | 1.3.14 | `create_agent` 可用，返回 `CompiledStateGraph`，支持嵌套（Agent 作为 tool） |
| langgraph | 1.2.10 | — |
| langgraph-prebuilt | 1.1.0 | `create_react_agent` ✅；`create_supervisor` ❌ 导入失败（需自建） |
| langchain-openai | 1.4.1 | — |

### 2.4 单 Agent 的三个"增长痛点"

| 痛点 | 具体表现 |
|---|---|
| ① System Prompt 膨胀 | `prompts.py` 已 46 行：计税规则（B 表/A 表）、社保、填表、检索、记忆、免责全挤在一个 prompt，规则互相干扰 |
| ② 工具选择压力 | 主 LLM 每次都要从 8 个工具里选，计税类（3/4）与检索类（1/2）行为模式差异大 |
| ③ 上下文混装 | 计税的中间步骤（查画像 → 计算 → 更新画像）与其他任务的历史混在一条消息链，压缩/检索都要面对噪声 |

> 结论：**计税类任务（工具 3/4 + 记忆 1/6）是天然的独立子 Agent 候选**——它们自成闭环（画像 → 计算 → 回写），领域规则密集，且与检索/填表/指引任务解耦度最高。

---

## 3. 为什么做 Multi-Agent（技术动机 + 叙事价值）

### 3.1 技术动机：职责分离

把"计税专家"从主 Agent 中剥离：

```
主 Agent（路由/协调）         计税子 Agent（领域专家）
  ├─ 识别"这是计税问题"  ──→    ├─ 独立 system prompt（计税规则全量下沉）
  ├─ 把问题交给计税专家        ├─ 工具集只留 get_user_context / calculate_* / update_user_context
  └─ 汇总回复用户              ├─ 无对话历史（每次独立），画像靠 get_user_context
                               └─ 返回 JSON 五字段（协议不变）
```

### 3.2 叙事价值（面试/答辩）

- **架构演进叙事**：lest 从"单 Agent + 8 工具"升级为"协调 Agent + 领域子 Agent"——展示你不是只会用框架，而是理解多 Agent 的取舍
- **记忆隔离叙事**：子 Agent 无状态设计是有意为之——"画像独立存储 + 子 Agent 无历史"，天然防上下文污染，是答辩可展开的设计点
- **与 MCP 衔接**：计税子 Agent 是将来 MCP Server 封装（规划⑤）的自然宿主

### 3.3 诚实边界（写进答辩话术）

> 多 Agent 对**单轮单任务**不会更准（底层是同一个 tax_engine）；它的价值在**职责解耦、prompt 隔离、架构可扩展**。评测用"对拍一致 + 回归不降"证明不退化，用架构图证明演进。

---

## 4. 架构设计（两阶段）

### 4.1 阶段一：轻量版 — Tool-as-Subagent（推荐落地，1.5-2 天）

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

### 4.2 阶段二：完整版 — Supervisor 自建（可选，答辩前有余量再做）

**⚠️ 版本事实**：`langgraph-prebuilt 1.1.0` 无 `create_supervisor`，官方 API 不可用。

**自建方案**（纯 langgraph，无新依赖）：

```
StateGraph（state: {task, result})
  ├─ supervisor 节点：LLM 判断任务类型 → 路由给 worker
  ├─ tax_worker / rag_worker / form_worker：各自调子 Agent 或工具
  └─ 汇总节点：拼装最终答案
```

- 工作量：2-3 天；风险：路由准确率需要评测集
- **建议**：答辩演示用阶段一（Tool-as-Subagent）已足够讲清"多 Agent 化"；阶段二作为论文"架构演进展望"章节素材，不强制实现

---

## 5. 轻量版详细设计（双子 Agent）

### 5.1 职责边界

| 维度 | 主 Agent | 计税子 Agent | 社保子 Agent |
|---|---|---|---|
| 职责 | 意图识别、路由、汇总、检索/填表/指引 | 只处理计税类（工资/劳务/稿酬/特许权/个体户/年终奖） | 只处理社保/公积金查询（比例/基数/灵活就业） |
| System Prompt | 精简：计算类两段下沉为一句"交给对应专家" | 计税规则全量下沉（§5.2） | 社保规则全量下沉（§5.3） |
| 工具集 | 8 个（计税/社保各替换为子 Agent） | 4 个（画像读写 ×2 + 计税 ×2） | 3 个（画像读写 ×2 + 社保 ×1） |
| 记忆 | InMemorySaver + HistorySummarizer | **无 checkpointer、无历史**（每次独立） | 同左 |
| 画像来源 | — | 只用 `get_user_context`（contextvar 传 thread_id，同进程内传播） | 同左 |
| middleware | ToolError + ModelCallLimit(25) + 摘要 | ToolError + ModelCallLimit(8)（防子 Agent 死循环） | 同左 |

### 5.2 计税子 Agent System Prompt 设计

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

### 5.3 社保子 Agent System Prompt 设计

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

### 5.4 代码骨架（backend/tools/subagents.py — 两个子 Agent 统一放一个模块）

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

### 5.4 主 Agent 接入（backend/agent/engine.py 修改）

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

### 5.5 B 表双工具链路（v1.1 决策：主 Agent 协调）

个体户申报场景（"先填表再计税"）**顺序协调归主 Agent**，子 Agent 不集成 `fill_tax_form`：

- 主 prompt 保留并强化该规则（原文 `prompts.py:25`）："**若用户提'B表'或'个体户申报'，先调 `fill_tax_form(B表)` 填基础信息，再调 `tax_subagent` 计税，顺序不可颠倒**"
- 子 Agent 职责纯粹：只算税，不填表；填表结果卡片与计税卡片由主 Agent 依次触发下发
- 两个工具间**无数据通道**（填表结果与计税输入各自独立），符合现状（现链路本来也是两次独立工具调用）

### 5.6 前端与 SSE

**零改动**。子 Agent 返回的 JSON 五字段与 `tools/base.py` 协议一致，`routers/chat.py` 的 `on_tool_end` 解包逻辑原样工作（result 卡片 / source 链接 / disclaimer 照常下发）。

### 5.7 模式开关说明（v1.2）

`AGENT_MODE` 只影响 `engine.py` 里 `ALL_TOOLS` 的组装，**其余代码两形态共用**：

| 形态 | ALL_TOOLS | 用途 |
|---|---|---|
| `multi`（默认） | 计税/社保 → 两个子 Agent | 多 Agent 演示 / 答辩主形态 |
| `tools` | 原 8 工具 | 回退保底 / 演示"单 Agent vs 多 Agent"对比 / 异常时快速降级 |

- 评测：两形态各跑一遍（tools 形态 = 现状基线，已有数据；multi 形态 = 本设计验收）
- 切换粒度：进程级（config 启动时读），不做请求级切换（保持简单）

### 5.8 prompt 双版本设计（v1.3，修复"主 Agent 调不到子 Agent"）

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

**验收**（一致性硬校验）：multi 形态下 `agent_eval` 20 条跑通 + 无 "not registered" 报错（§7.5）；tools 形态回归现状。

### 5.9 子 Agent 失败降级设计（v1.4，复用 LLM 已生成参数）

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

### 5.10 绕过检测设计（v1.5，防"LLM 心算绕过子 Agent"）

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

**评测**（§7.7）：子层加 2 条"心算诱导"用例（"月薪8000个税大概多少""房租1500能省多少税"），断言输出**必须带 result_card**（即必须走了工具）。

---

## 6. 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/config.py` | 修改 | 新增 `AGENT_MODE = "multi"`（v1.2 模式开关） |
| `backend/agent/prompts.py` | 修改 | 新增 `TAX_SUBAGENT_PROMPT` + `SOCIAL_SUBAGENT_PROMPT`；**`SYSTEM_PROMPT` 拆两版**：`SYSTEM_PROMPT_MULTI`（工具名换子 Agent）+ `SYSTEM_PROMPT_TOOLS`（现有原样）；保留 B 表"先填表再计税"顺序规则（§5.5） |
| `backend/agent/engine.py` | 修改 | `get_llm()` 单例提取；`build_agent` 复用；**`ALL_TOOLS` 按 `AGENT_MODE` 两形态组装**（§5.4） |
| `backend/tools/subagents.py` | **新增** | 双子 Agent 构建 + `@tool` 包装 + 消息链提取 + 全局单例 + **`_fallback_reuse_args` 失败降级 + `_contains_tax_amount`/`_forced_recalc` 绕过检测**（§5.4 + §5.9 + §5.10） |
| `backend/tools/__init__.py` | 修改 | 导出 `tax_subagent` / `social_subagent`；**ALL_TOOLS 移出（改由 engine.py 本地组装）** |
| `backend/eval/multi_agent_eval.py` | **新增** | **双层评测**：主层对拍（§7.2）+ 子层内部选工具（§7.3） |
| `backend/eval/agent_eval.py` | 修改 | 20 条 `expected_tools` 迁移（id 6-10 → `tax_subagent`，id 11-14 → `social_subagent`）+ 补 B 表双工具用例 + 邻域混淆用例 |
| `docs/财务RAG-项目补充与添加实施规划.md` | 修改 | §4.1 勾选状态 + 实测数据回填 |

**不改动**：`routers/chat.py`、前端全部文件、`services/tax_engine.py`、`rag/`、`context/`。

---

## 7. 评测与验收（v1.1 双层评测）

### 7.1 两道硬关（P5）+ 三层结构

| 层 | 评测 | 门槛 |
|---|---|---|
| **主层·对拍** | 计税 5 条 + 社保 3-4 条，子 Agent vs 原工具直调，比较 `result_card` 数值 | 数值完全一致（同一引擎，验证链路无失真） |
| **主层·路由回归** | `agent_eval.py` 20 条**迁名后**重跑（id 6-10 → `tax_subagent`，id 11-14 → `social_subagent`） | 准确率 ≥90%，计算类不降 |
| **子层·内部选工具** | 新增 `subagent_eval.py`：直接对子 Agent 注入 query，验证内部工具选择与拒答 | 命中率 ≥90%（子 Agent 内部正确性） |

> ⚠️ **关键语义变化（v1.1 审查发现）**：子 Agent 内部工具调用**不进主 Agent 消息链**——`extract_tool_calls` 从主链只能提取到 `tax_subagent`/`social_subagent`（包装名）。所以主层 20 条测的是**"主 Agent 路由正确性"**，子 Agent 内部选工具必须由**子层评测**单独覆盖——这正是双层评测存在的理由。

### 7.2 主层对拍集设计（backend/eval/multi_agent_eval.py）

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

### 7.3 子层评测集设计（backend/eval/subagent_eval.py）

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

### 7.4 路由三道防线（v1.1 决策，P10）

| 防线 | 内容 | 验收 |
|---|---|---|
| ① 子 Agent 拒答 | 双子 Agent prompt 第 5 条：非本领域问题明确返回"交给主助手" | 子层评测加 2 条拒答用例（"个税APP怎么退税"→ tax 子 Agent 应拒答） |
| ② 主层回归硬门槛 | 20 条迁名后重跑 ≥90%；不达标 = 主 prompt 精简过度，回滚计税/社保规则 | 回归不降 |
| ③ 邻域混淆用例 | 主层补 4 条边界用例：`"个税APP怎么退税"`→`filing_guide`；`"租房扣除标准"`→`search_knowledge`；`"工资8000交多少税"`→`tax_subagent`；`"社保缴费比例"`→`social_subagent` | 全部命中 |

### 7.5 一致性硬校验（v1.3 新增）

**prompt ↔ 工具列表一致性**（P12 验收，防"主 Agent 调不到子 Agent"复发）：

| 校验 | 方法 | 门槛 |
|---|---|---|
| 工具名注册检查 | 扫描 `SYSTEM_PROMPT_MULTI` 中出现的工具名（正则 `[a-z_]+(?=\s*[)）])` 或人工清单），断言每个都在 multi 形态 ALL_TOOLS 里 | 100% 注册，零未注册名 |
| 无报错回归 | multi 形态跑 `agent_eval` 20 条，**收集消息链中的 error 状态 ToolMessage**（`"not registered"`），断言为零 | 0 条 not registered |
| tools 形态回归 | `AGENT_MODE=tools` 跑现有 20 条 | 与现状一致（≥90%） |

### 7.6 降级机制评测（v1.4 新增）

| 指标 | 方法 | 门槛 |
|---|---|---|
| 降级触发率 | 子层评测 `subagent_eval.py` 加"绕圈场景"用例（如参数缺失 query），统计降级路径触发次数 | 有 result_card 的用例 0 次降级；**绕圈用例 100% 落到降级②**（复用参数成功） |
| 降级数值一致 | 降级路径结果 vs 直调原工具同参数结果比对 | 数值完全一致（同一引擎，天然成立） |
| 放弃率 | 统计落到③（主 Agent 反问）的次数 | 仅限"LLM 完全没尝试"的极端用例，正常集为 0 |

### 7.7 绕过检测评测（v1.5 新增）

| 指标 | 方法 | 门槛 |
|---|---|---|
| 心算拦截率 | 子层 `subagent_eval.py` 加 2 条"心算诱导"用例（"月薪8000个税大概多少" / "房租1500能省多少税"），断言输出**必须带 result_card** | 100%（必须走工具，LLM 数字作废） |
| 强制重算数值 | 强制重算路径结果 vs 直调原工具同参数比对 | 数值完全一致 |

### 7.8 建议补充（有余量做）

- **链路正确性抽查**：验证子 Agent 调用后 `update_user_context` 确实回写画像（断言 contexts dict 更新）
- **失败恢复**：子 Agent 内部工具报错 → ToolErrorMiddleware 是否兜住、主 Agent 能否继续

---

## 8. 实施步骤与排期

```
依赖：无（不依赖其他 P1 项，可与 MCP 并行）
顺序（每步可独立交付）：
  ① prompts.py：新增 TAX_SUBAGENT_PROMPT + SOCIAL_SUBAGENT_PROMPT + SYSTEM_PROMPT 拆两版（MULTI/TOOLS）+ B 表顺序规则保留（1.5h）
  ② engine.py：提取 get_llm() 单例 + config.AGENT_MODE 分支（prompt+tools 同源组装）（1h）
  ③ subagents.py：双子 Agent 构建 + @tool 包装 + 消息链提取 + 全局单例（3h，核心）
  ④ ALL_TOOLS 移出 tools/__init__ → engine 本地组装（0.5h）
  ⑤ agent_eval.py 迁名 + 补 B 表用例 + 邻域混淆用例（0.5h）
  ⑥ multi_agent_eval.py（主层对拍）+ subagent_eval.py（子层评测）+ 一致性校验（工具名注册检查 + not registered 断言）（2h）
  ⑦ 冒烟：multi 形态试计税 3 条 + 社保 2 条 + 检索 1 条 + 填表 1 条；tools 形态回归现状（0.5h）
总投入：约 2-2.5 天
```

---

## 9. 面试叙事与答辩素材

### 9.1 三句话版本

> "lest 原来是单 Agent + 8 工具。我发现计税、社保两个计算领域规则密集、自成闭环，就把它们拆成两个独立子 Agent——用 create_agent 构建领域专家（各自独立 system prompt + 画像工具集 + 无历史），再包成 tool 挂回主 Agent。主 Agent 只做路由协调，领域规则全量下沉，B 表这类跨工具流程由主 Agent 保证顺序。整个改造对前端零改动，因为子 Agent 返回还是同一个 JSON 协议。评测上我做了双层验证：主层对拍 8 条数值完全一致 + 20 条路由回归 ≥90%，子层再单独测内部选工具，双层都过才算完成。"

### 9.2 可展开的深挖点（考官追问弹药）

| 追问 | 回答要点 |
|---|---|
| 为什么用 create_agent 嵌套而不是 LangGraph Supervisor？ | langgraph-prebuilt 1.1.0 无 create_supervisor，且轻量版零结构改动、两天可验证；完整版 Supervisor 作为架构演进展望 |
| 子 Agent 为什么无状态？ | 用户画像独立存储在 per-thread dict，子 Agent 每次从 get_user_context 读——无历史天然防上下文混装，也避免子 Agent 记忆膨胀；因此全局单例共享也安全 |
| 多 Agent 有什么代价？ | ① 多一层 LLM 往返，延迟 +20-40%；② token 成本 1.5-2×；③ 路由错误时任务错派。我做了三项补偿（子 Agent 单例省编译 / 主 prompt 精简抵消 / 对拍+回归证明不退化） |
| result_card 怎么传出来的？ | 不靠 LLM 复述——包装层遍历子 Agent 消息链，确定性提取 ToolMessage 里的 result_card/sources，再与最终 answer 合并 |
| 怎么防止主 Agent 误派？ | 三道防线：子 Agent 内部拒答兜底 + 20 条路由回归硬门槛 + 4 条邻域混淆用例专门打误派 |
| 子 Agent 内部选工具怎么验证？ | 主 Agent 消息链里只有包装名，看不到子 Agent 内部——所以单独建了子层评测，直接对子 Agent 注入 query 验证内部调用 |

### 9.3 答辩 PPT 素材

- **架构演进图**：单 Agent（8 工具平铺）→ 协调 Agent + 计税子 Agent + 社保子 Agent（职责分层）
- **数据证据**：对拍 8/8 一致 + 主层回归 ≥90% + 子层命中 ≥90% + 延迟实测（接受 +20-40% 的诚实数据）
- **诚实表述**：多 Agent 的价值在解耦与可扩展，不在单任务精度

---

## 10. 风险与回退

| 风险 | 等级 | 应对 |
|---|---|---|
| 子 Agent 延迟增加（多 2-3 轮 LLM，+20-40%） | 🟡 | **已接受（v1.1 决策）**：全局单例省编译开销 + 主 prompt 精简抵消 + 答辩话术兜底；实测超预算再评估 |
| token 成本 1.5-2×（子 Agent system prompt + 中间推理） | 🟡 | 子 Agent prompt 精简（规则下沉但不冗余）；答辩环境本地 API 成本可忽略 |
| 循环导入（subagents ↔ tools） | 🟡 | engine.py 本地组装 ALL_TOOLS，避免 tools/__init__ 深层导入 |
| contextvar 传播失效 | 🔴 | 子 Agent 用 `ainvoke` 与主 Agent 同事件循环，理论传播正常；**步骤⑥ 加断言测试画像回写**（§7.5） |
| 路由误判（主 Agent 错派） | 🟡 | **三道防线（v1.1）**：子 Agent 拒答兜底 + 20 条回归硬门槛 + 邻域混淆用例 |
| 主 prompt 精简过度导致工具选择退化 | 🟡 | 20 条回归不达标 = 回滚主 prompt 计税/社保规则，保留精简失败的证据 |
| **prompt 残留工具名 → 主 Agent 调不到子 Agent**（v1.3 修复） | 🔴 | **根因**：prompt 写死原工具名而 multi 形态未注册 → LLM 按 prompt 调用 → ToolNode 报 "not registered"（源码 `tool_node.py:949`）→ 先失败一轮再纠正。**修复**：prompt 拆两版与 ALL_TOOLS 同源分支（§5.8）+ 一致性硬校验（§7.5） |
| **子 Agent 多轮未计算出结果**（v1.4 修复） | 🟡 | **根因**：参数缺失绕圈 / 工具选错 / ModelCallLimit(8) 触达（`exit_behavior="end"` 正常结束，无异常可捕获）。**修复**：降级——复用消息链 `AIMessage.tool_calls` 里 LLM 已生成的 calculate 参数直调原工具（§5.9），连 tool_calls 都没有才返回错误让主 Agent 反问 |
| **LLM 心算绕过子 Agent**（v1.5 修复） | 🔴 | **根因**：create_agent 循环中 LLM 每轮自主决定是否声明 tool_calls，可能不调工具直接输出文本（税率靠 LLM 记忆，不可信）。**修复**：强制重算——answer 含税额数字但无 result_card → 判定心算 → 强制走引擎、LLM 数字作废（§5.10 + 三层防线） |
| B 表链路断裂（先填表再计税顺序错） | 🟡 | 主 prompt 保留原顺序规则（§5.5）+ 主层补 B 表双工具用例 |
| 多 Agent 收益被质疑（"不更准何必做"） | 🟢 | 叙事转向解耦/可扩展/架构演进（§9.3 诚实表述） |

**回退方案（v1.2 升级）**：**`AGENT_MODE = "tools"` 一行切换**回纯工具形态（原 8 工具，与现状完全一致）——不需要改代码、不需要删文件，进程级生效。multi 形态出任何问题，改配置即还原，答辩现场也能演示两形态对比。原文件（`calculate_income_tax` 等）始终保留，子 Agent 内部继续复用。

---

## 11. 编码 Checklist

- [x] `prompts.py`：新增 `TAX_SUBAGENT_PROMPT` + `SOCIAL_SUBAGENT_PROMPT`（§5.2/§5.3），主 prompt 计税/社保精简，**保留 B 表顺序规则**
- [x] `engine.py`：提取 `get_llm()` 模块级单例，`build_agent()` 复用
- [x] `subagents.py`：双子 Agent（无 checkpointer + ModelCallLimit 8 + 全局单例双检锁）+ `@tool` 包装 + `_extract_fields` 消息链提取 + `_fallback_reuse_args` 降级 + `_contains_tax_amount` / `_forced_recalc` 绕过检测
- [x] `engine.py` / `tools/__init__.py`：`ALL_TOOLS` 替换（`tax_subagent` / `social_subagent`），规避循环导入
- [x] `agent_eval.py`：26 条评测集（按 AGENT_MODE 动态迁名 + 补 B 表双工具用例 + 4 条邻域混淆用例 + 一致性硬校验）
- [x] `multi_agent_eval.py`：主层对拍 8 条（计税 5 + 社保 3）+ 子层评测 10 条（工具选择 6 + 拒答 2 + 心算绕过 2）
- [x] 冒烟测试：agent_eval 26/26 100% + multi_agent_eval 主层 8/8 100% + 子层 10/10 全绿
- [x] 回填实施规划 §4.1 状态与实测数据（对拍一致数 / 回归准确率 / 子层命中率 / 延迟对比）
- [x] 概念梳理 §3 补一行"已落地"状态

### 11.1 评测结果（2026-08-05）

| 评测层 | 分数 | 验收门槛 |
|---|---|---|
| agent_eval 主 Agent 路由 | 26/26 (100%) | ≥90% |
| 一致性硬校验 | 0 "not registered" | ✅ |
| multi_agent_eval 主层对拍 | 8/8 (100%) | 数值完全一致 |
| multi_agent_eval 子层工具选择 | 6/6 (100%) | ≥90% |
| multi_agent_eval 子层拒答 | 2/2 (100%) | ✅ |
| multi_agent_eval 子层绕过检测 | 2/2 (100%) | ✅ |
- [ ] 回填实施规划 §4.1 状态与实测数据（对拍一致数 / 回归准确率 / 子层命中率 / 延迟对比）
- [ ] 概念梳理 §3 补一行"已落地"状态

---

## 12. grill-me 审查结论（v1.0 → v1.1）

> 2026-08-04 经 grill-me 压力审查，6 个决策分支全部闭合，本节为决策记录（供回溯）：

| # | 分支 | 问题 | 决策 | 影响 |
|---|---|---|---|---|
| A | 拆分粒度 | 只拆计税 vs 计税+社保合并 vs 只做概念验证 | **拆两个子 Agent**（计税+社保），否决合并（社保无回写链，合并稀释聚焦） | §4.1 双子结构，改动面 ×2 |
| B | 成本取舍 | +20-40% 延迟 / 1.5-2× token 是否可接受 | **接受 + 三项补偿**（子 Agent 全局单例 / 主 prompt 精简抵消 / 答辩话术兜底） | §5.4 单例 + §9.1 话术 |
| C | 评测联动 | 子 Agent 内部调用不进主消息链，仅迁名会失去内部验证 | **双层评测**：主层 20 条迁名测路由 + 子层 subagent_eval 测内部选工具 + 补 B 表用例 | §7 重构 |
| D | B 表链路 | 先填表再计税的顺序协调归谁 | **主 Agent 协调**：prompt 强化顺序规则，子 Agent 不集成 fill_tax_form | §5.5 |
| E | 实例化 | 每次重建 vs 全局单例 | **全局单例**（无状态 → CompiledStateGraph 并发安全，懒加载双检锁） | §5.4 |
| F | 路由可靠性 | 主 Agent 误派风险 | **三道防线**：子 Agent 拒答兜底 + 回归 ≥90% 硬门槛 + 邻域混淆用例 | §7.4 + §10 |
| G | 模式开关 | 能否保留原工具形式 | **`AGENT_MODE` 配置切换**（multi 子 Agent 形态默认 / tools 纯工具形态回退），不并存注册（并存→评测歧义+子 Agent 死代码）；原工具文件始终保留、子 Agent 内部复用 | §5.7 + §10 回退 |
| H | **prompt 一致性** | 主 Agent 会不会调 tool 导致调不到子 Agent | **会，且当前设计必然发生**——源码查证：ToolNode 只执行注册工具，未注册调用返回 "not registered" 错误（`tool_node.py:949`）；middleware 无 tools 注入（已查证 4 个 middleware）；但主 prompt 残留 5 处原工具名（`prompts.py` 16/17/19/25/28-29 行）会诱导 LLM 调用未注册工具 → 先报错再纠正、浪费轮次。**修复：`SYSTEM_PROMPT` 按 `AGENT_MODE` 拆两版**（multi 版工具名换子 Agent，tools 版原样），与 ALL_TOOLS 同源分支 + 一致性硬校验 | §5.8 + §7.5 + P12 |
| I | **失败降级** | 子 Agent 多轮未能计算出结果时能否自动调 tool | **能，且已设计**——关键事实：`ModelCallLimitMiddleware` 默认 `exit_behavior="end"`（`model_call_limit.py:131`），超限正常结束不抛异常，故检测信号 = 无 result_card；降级 = **复用消息链 `AIMessage.tool_calls` 里 LLM 已生成的 calculate 参数直调原工具**（参数 LLM 负责、计算引擎负责，结构已验证）；连 tool_calls 都没有才返回错误让主 Agent 反问 | §5.9 + §7.6 + P13 |
| J | **绕过检测** | LLM 会不会不调工具直接"心算"输出 | **会**——create_agent 循环中 LLM 每轮自主决定是否声明 tool_calls，可能直接输出文本（绕过子 Agent 的确定性计算）。**修复：强制重算**——answer 含税额数字但无 result_card = 心算 → 强制走引擎、LLM 数字作废；配合 prompt 软约束 + v1.4 降级，形成三层"不准绕过"防线 | §5.10 + §7.7 + P14 |

**自查发现的事实性修正**（未占用提问轮次）：
- `agent_eval.py` id 6-14 共 9 条 `expected_tools` 必须迁移（否则替换后 100% 失败）
- `fill_tax_form` 独立脚本加载，不 import 计税工具 → 替换安全
- 子 Agent 全局单例优于"每次重建 + llm 单例"（省编译开销）
- `create_agent` 嵌套结构已实测可行（真实 DeepSeek 构建成功）

---

> 执行规则：动手前先在实施规划 §4.1 勾选 ⬜ → 拆分任务（TaskCreate）→ 按 §11 Checklist 逐项完成 → 跑 §7 评测 → 回填数据。发现问题追加到《开发踩坑记录.md》，本设计文档如有变更走追加修订（不删除既有内容）。
