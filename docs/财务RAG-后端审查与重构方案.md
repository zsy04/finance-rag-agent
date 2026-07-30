# 财务 RAG Agent · 后端审查与重构方案

> **生成日期**：2026-07-30 | **版本**：v3（终版，两轮审查修订全部落实）
> **来源**：grill-me 深度审查（对照 4 份设计文档 + 实际代码 + 两轮技术可行性审查）
> **关联文档**：`财务RAG-技术架构与Agent方案.md` / `财务RAG-后端开发路线图.md` / `财务RAG-前后端对照表.md` / `财务RAG-产品定义与答辩策略.md`
> **本文定位**：审查结论 + 重构蓝图。不做编码，只定义"改什么、为什么、怎么改"。
>
> **修订记录**：
> - v1：初版，10 章蓝图
> - v2：一审 14 项修订（E1–E14）全部应用
> - v3：二审 10 项修订（N1–N10）全部应用 + PoC 验证通过
> - v4：对齐 LangChain v1 标准（2026-07-30）：`InMemorySaver` / `create_agent` / 中间件系统 / `args_schema` / `response_format`
>
> **PoC 验证结果**：
> - ✅ contextvar 传播：成功
> - ✅ on_tool_end 解包：output 为 `ToolMessage`，JSON 在 `.content` 字段
>
> **v1 对齐要点**（参照 lc-13/lc-14 学习笔记）：
> - `MemorySaver` → `InMemorySaver`（LangGraph v1 重命名）
> - `create_react_agent` → `from langchain.agents import create_agent`（v1 新标准）
> - 加入 `ToolErrorMiddleware` + `ModelCallLimitMiddleware`（16 个预构建中间件体系）
> - `@tool` 使用 `args_schema` + `Field(description=...)` 提升 LLM 参数准确度

---

## 一、审查结论：设计与实现的三大差距

| # | 差距 | 设计文档要求 | 代码实际 | 影响 |
|:--:|------|-------------|---------|------|
| 1 | **Agent 调度缺失** | `create_agent` + `MemorySaver` + 7 `@tool` 自动路由 | `AsyncOpenAI` 裸调，零 Agent | LLM 无法自主选择工具、无法多轮记忆 |
| 2 | **SSE 事件不匹配** | 8 种事件（thinking/step/confirm/result/source/disclaimer/error/done） | 3 种（token/done/error） | 前端无法实现引导式追问、结果卡片、确认交互 |
| 3 | **工具集缺失** | 7 个独立 `@tool` 函数 | 0 个；RAG 内嵌在 generator，计算引擎是独立 REST 路由 | 用户问"税多少社保多少"只会做 RAG 检索，不会自动调用计算引擎 |

### 已对齐的部分（无需改动）

| 模块 | 状态 | 备注 |
|------|:--:|------|
| RAG 检索链（三层分层召回 + 知识图谱扩展） | ✅ | 完全按设计 |
| Query 改写层 | ✅ | 完全按设计 |
| 个税/社保计算引擎 | ✅ | 核心逻辑按设计；2026-07-30 已修复 5 项实现缺陷（见下方），@tool 封装基于修复后版本 |
| 评测体系（40 条 + 4 指标） | ✅ | 完全按设计 |
| `fill_tax_form.py` 脚本 + `form_field_map.json` | ✅ | 代码就绪，需包 @tool 装饰器 |

> **引擎修复记录**（2026-07-30 已完成）：
> - `tax_engine.py`：年终奖对比计税 bonus 按收入类型 ratio 换算；`_find_bracket` 未排序校验；模块级 `open()` 加错误处理
> - `social_engine.py`：灵活就业费率从数据文件读取（不再硬编码）；`calculate_flexible_social` 修复 `salary` 与 `base_level` 参数忽略问题；模块级 `open()` 加错误处理

---

## 二、架构决策速查

| # | 决策项 | 结论 |
|:--:|--------|------|
| 1 | Agent 框架 | **LangChain `create_agent` + `InMemorySaver`**（v1 标准，`langchain.agents`） |
| 2 | SSE 事件 | **8 种**，严格按 `前后端对照表` 格式（`event: xxx\ndata: {...}\n\n`） |
| 3 | 工具优先级 | **MVP 5 个先做**，答辩闭环 2 个跟进，辅助 2 个后补 |
| 4 | 对话上下文记忆 | **方案 C**：`get_user_context` / `update_user_context` 两个 @tool + per-thread dict（加锁） |
| 5 | 安全 | `.gitignore` 已屏蔽 `.env`，毕设不做认证/限流，答辩后轮换 API Key |
| 6 | 代码规范散落 | 答辩后统一修（路径计算、键名混用、常量散落等） |
| 7 | 延迟权衡 | Agent 路径比直连路径多 1 次 LLM 推理（约 +1-3s），毕设可接受；后期可对纯 RAG 问答保留旧 `/chat` 直连通路作为快速路径 |
| 8 | 模型名 | 统一从 `config.py` 读取 `DEEPSEEK_MODEL`（当前值为 `deepseek-chat`），不在代码中硬编码 |
| 9 | API 路由前缀 | 统一切到 `/api/` 前缀，与前后端对照表对齐：`/api/chat`、`/api/tax/calculate`、`/api/social/calculate` |

---

## 三、重构目标架构

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

### 关键机制：工具结构化返回 + Router 解包

`@tool` 函数是纯函数，只能 `return`，不能 `yield` 中间事件。采用以下方案：

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

---

## 四、工具集实现路线

### 4.1 MVP 必需（第一批）

> **`@tool` 编写规范**（v1 最佳实践）：使用 `args_schema` + Pydantic `Field(description=...)` 提升 LLM 参数生成准确度。每个工具的 docstring 第一句说明"何时使用"，帮助 LLM 做工具选择。

| 工具 | 输入 | 数据源/逻辑 | 迁移来源 | 注意 |
|------|------|------------|---------|------|
| `search_knowledge(query)` | 用户问题原文 | `rag/retriever.py` → `retriever.retrieve()` | 现有 RAG 链路，包 @tool | ⚠️ `async def` + `asyncio.to_thread()` 包装，避免阻塞事件循环 |
| `calculate_income_tax(annual_income, income_type, social_insurance, deductions, city, bonus)` | 收入、扣除、城市 | `services/tax_engine.py` → JSON 税率表公式计算 | 现有引擎（已修复版），包 @tool | `deductions` 为 `dict[str, float]`，如 `{"housing_rent": 1500}`（元/月）；`income_type` 为 `str`，docstring 声明枚举值 `"salary"|"labor_service"|"manuscript"|"royalty"` |
| `query_social_insurance(city, employment_type, salary, housing_fund_ratio, flexible_base_level)` | 城市、就业类型、工资 | `services/social_engine.py` → JSON 社保数据查表 | 现有引擎（已修复版），包 @tool | 从数据文件读取费率，非硬编码；`flexible_base_level` 支持灵活就业档次选择 |
| `get_user_context()` | 无（读 `contexts[thread_id]`） | per-thread dict `{city, salary, income_type, deductions}` | **新建** | `thread_id` 通过 `contextvars.ContextVar` 传递（PoC 必须先验证传播） |
| `update_user_context(key, value)` | key + value | 写入 `contexts[thread_id]` | **新建** | key 合法值: `city`/`salary`/`income_type`/`housing_rent`/`children_edu`/`elderly_support`；内部白名单校验 |

#### 工具返回结构 schema

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

### 4.2 答辩闭环（第二批）

| 工具 | 输入 | 数据源/逻辑 | 迁移来源 |
|------|------|------------|---------|
| `fill_tax_form(form_type, user_data)` | A表/B表 + 用户字段 | `scripts/fill_tax_form.py` → openpyxl 填表 | 脚本迁移到 `backend/tools/`，包 @tool |
| `filing_guide(scenario)` | 申报场景（汇算/个体户/小规模） | RAG 检索 `operations/` 目录操作指引 | RAG 链路复用 + 专用检索过滤 |

### 4.3 答辩后补充（第三批）

| 工具 | 数据源 |
|------|--------|
| `search_industry_benchmark(industry_name, metric?)` | `industry_benchmark.json`（97 行业 × 10 指标），精确匹配 |
| `search_tax_website(query)` | 白名单域名 Web Search（7 个 gov 域名） |

---

## 五、文件结构变化

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

### 变量命名约定

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
> - 毕设阶段接受内存存储；答辩后可换 `SqliteSaver` + JSON 文件持久化
> - **注意**：`contexts` dict 无 TTL 清理机制，毕设 demo 时长有限不影响；若长期运行需加 TTL（如 30 分钟未访问即删除）

---

## 六、SSE 事件映射表

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

> **`confirm` 事件说明**：Agent 反问以 LLM 自然语言形式通过 `step` 事件承载。不单独发 `confirm` 事件。原因：`@tool` 无法中途暂停等用户确认，且 LLM 自然反问（"请问你的收入类型是工资还是劳务报酬？"）的效果更自然。

### SSE 格式

```
event: {event_type}
data: {json_payload}\n\n
```

所有 JSON 使用 `ensure_ascii=False`，避免中文被转义为 `\uXXXX`。

---

## 七、对话上下文记忆（方案 C 详解）

### 存储

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

### Agent 行为逻辑（由 System Prompt 驱动）

```
规则：回答问题涉及个税或社保计算时：
  1. 先调 get_user_context 检查已知信息
  2. 缺少关键字段（收入类型、金额、城市）→ 反问 1-2 个问题，不猜测
  3. 信息齐全 → 调 calculate_income_tax / query_social_insurance
  4. 计算结果出来后 → 调 update_user_context 保存城市、工资等信息
```

### thread_id 传递

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

---

## 八、System Prompt 设计要点

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

---

## 九、实施顺序（按依赖关系）

```
Phase 1: 基础文件搭建
  ├─ 创建 backend/agent/__init__.py + prompts.py
  ├─ 创建 backend/tools/__init__.py + base.py + user_context.py
  └─ 不破坏现有代码，新文件独立存在

Phase 2: MVP 工具（第一批 5 个 @tool）
  ├─ search_knowledge.py     ← 包 rag/retriever.py（async def + asyncio.to_thread）
  ├─ calculate_income_tax.py ← 包 services/tax_engine.py（deductions 为 dict，docstring 声明枚举值）
  ├─ query_social_insurance.py ← 包 services/social_engine.py
  ├─ user_context.py（含 contexts dict + threading.Lock + contextvar）
  └─ 单元验证：每个 @tool.invoke() 返回正确结构化 JSON

Phase 3: Agent 大脑
  ├─ agent/engine.py：from langchain.agents import create_agent
  │   create_agent(model=llm, tools=ALL_TOOLS, system_prompt=SYSTEM_PROMPT,
  │                 checkpointer=InMemorySaver(),
  │                 middleware=[ToolErrorMiddleware(), ModelCallLimitMiddleware(25)])
  ├─ 单轮调用验证：Agent 自动选工具 → 返回正确回答
  └─ 确认 on_tool_end 能拿到 ToolMessage.content 解包

Phase 3.5: Agent 工具选择评测
  ├─ 构造 20 条 query（每类工具 4-5 条），标注期望调用的工具
  ├─ 运行 Agent，统计工具选择准确率
  ├─ 目标：≥ 90% 后再进入 Phase 4
  └─ 失败 case 分析 System Prompt / docstring 是否需要调优

Phase 4: SSE 流式上线
  ├─ routers/chat.py 重构：Pydantic ChatRequest + agent.astream_events + SSE 事件映射
  │   ├─ on_tool_end 解包 → 按顺序发 result → source → disclaimer
  │   └─ on_tool_error → error 事件
  ├─ 统一路由前缀为 /api/chat（与前后端对照表对齐）
  ├─ curl -N 验证：event: thinking → event: step → ... → event: done
  └─ 旧版 POST /chat 和 POST /chat/with-search 保留为 legacy 直连通路（纯 RAG + LLM，快速路径），
     新版 POST /api/chat 为 Agent 通路（工具调度，完整功能）。前端默认用 /api/chat。
     Phase 6 清理时再决定是否移除 legacy。

Phase 5: 答辩闭环工具（第二批）
  ├─ fill_tax_form.py ← scripts/ 迁移 + @tool 装饰器
  └─ filing_guide.py  ← RAG 检索 operations/ 目录

Phase 6: 清理与收尾
  ├─ 移除或重命名 services/generator.py（→ legacy_generator.py）
  ├─ 更新 requirements.txt：保留实际使用的 langgraph/langchain-openai/langchain-core，
  │   移除确实未用的 sse-starlette（已被 StreamingResponse 取代）
  ├─ 统一 config 路径计算基准（全部走 config.PROJECT_ROOT）
  └─ 轮换 DeepSeek API Key
```

---

## 十、不影响的重构原则

1. **不破坏现有 REST 端点**：`/api/tax/calculate` 和 `/api/social/calculate` 保留，作为快捷表单的独立通路。Agent 通路和表单通路并存。
2. **不修改 RAG 链路**：`rag/retriever.py` 和 `rag/query_rewriter.py` 不动，只新增 `@tool` 封装调用它们。
3. **计算引擎已修复，重构期间不再改引擎逻辑**：`services/tax_engine.py` 和 `services/social_engine.py` 已修复 5 项缺陷并验证通过，仅在 `tools/` 中封装调用。`calculate_income_tax` @tool 的入参含 `bonus`，内部继承 ratio 换算逻辑。
4. **新文件独立存在**：`agent/` 和 `tools/` 是新目录，不影响现有代码运行。改 `routers/chat.py` 是唯一会动到旧文件的地方。

---

## 十一、前置验证 PoC（Phase 2 前必须执行）

以下 PoC 验证两个关键假设。通过后再进入 Phase 2 编码。

```python
"""
PoC: 验证 LangGraph @tool 两大关键假设
假设①：contextvar 在 LangGraph 调度 sync @tool 时能传播
假设②：on_tool_end 的 output 是工具返回的 JSON 字符串，可 json.loads 解包

文件：backend/agent/poc_test.py（临时，验证通过后可删）
运行：python backend/agent/poc_test.py
"""

import json
import asyncio
from contextvars import ContextVar
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

# ── 假设①：contextvar 传播验证 ──
_test_var: ContextVar[str] = ContextVar("test_ctx")

@tool
def contextvar_test(s: str = "") -> str:
    """测试 contextvar 是否在 @tool 内部可读"""
    try:
        val = _test_var.get()
        return json.dumps({"answer": f"contextvar 传播成功: {val}", "ctx_ok": True}, ensure_ascii=False)
    except LookupError:
        return json.dumps({"answer": "contextvar 传播失败: LookupError", "ctx_ok": False}, ensure_ascii=False)

# ── 假设②：结构化返回 + on_tool_end 解包验证 ──
@tool
def structured_return(x: int, y: int) -> str:
    """测试工具返回结构化 JSON，验证 on_tool_end 能解包"""
    return json.dumps({
        "answer": f"计算结果: {x} + {y} = {x + y}",
        "result_card": {"type": "test", "data": {"sum": x + y}},
        "disclaimer": "test disclaimer",
        "sources": [{"title": "test source", "url": "https://test.example.com"}]
    }, ensure_ascii=False)

async def main():
    # 创建 Agent（用真实 DeepSeek，需 .env 配置）
    import os; from dotenv import load_dotenv
    load_dotenv("backend/.env")
    
    llm = ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com/v1",
        temperature=0,
    )
    agent = create_react_agent(llm, [contextvar_test, structured_return], checkpointer=MemorySaver())
    
    # 验证①：contextvar 传播
    _test_var.set("hello_from_router")
    config = {"configurable": {"thread_id": "poc-1"}}
    
    print("=== 验证①：contextvar 传播 ===")
    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": "调用 contextvar_test 工具"}]},
        config=config, version="v2"
    ):
        if event["event"] == "on_tool_end":
            output = event["data"]["output"]
            print(f"  contextvar_test 返回: {output}")
            print(f"  → 预期: ctx_ok=true, 实际: 看上方输出")
    
    # 验证②：结构化返回
    _test_var.set("poc-2")
    config2 = {"configurable": {"thread_id": "poc-2"}}
    
    print("\n=== 验证②：结构化返回 + on_tool_end 解包 ===")
    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": "计算 3+5"}]},
        config=config2, version="v2"
    ):
        if event["event"] == "on_tool_end":
            output = event["data"]["output"]
            # ⚠️ output 是 ToolMessage 对象（PoC 已验证），JSON 在 .content 字段
            raw = output.content if hasattr(output, 'content') else str(output)
            print(f"  on_tool_end output 类型: {type(output).__name__}")
            print(f"  on_tool_end .content: {raw}")
            parsed = json.loads(raw)
            print(f"  ✓ 解包成功: answer={parsed['answer']}")
            print(f"  ✓ result_card={parsed.get('result_card')}")
            print(f"  ✓ disclaimer={parsed.get('disclaimer')}")
            print(f"  ✓ sources={parsed.get('sources')}")

if __name__ == "__main__":
    asyncio.run(main())
```

### PoC 通过标准

| 验证项 | 通过条件 | PoC 结果 |
|--------|---------|:--:|
| ① contextvar 传播 | `contextvar_test` 返回 `"ctx_ok": true` | ✅ 通过 |
| ② 结构化返回解包 | `on_tool_end` 的 output 为 `ToolMessage`，`.content` 字段可 `json.loads` 解包 | ✅ 通过 |

> **①② 均已通过**。contextvar 传播正常，on_tool_end 解包确认 direct 为 `.content` 属性而非字符串本身。
> 备选方案不再需要。Phase 2 可以进入。

验证通过后，Phase 2–6 的编码基准就全部确认了。
