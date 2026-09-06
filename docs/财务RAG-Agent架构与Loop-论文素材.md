# 财务 RAG Agent：架构与 Agent Loop 讲解（论文/面试素材）

> 用途：毕业论文技术章节素材 + Agent 面试概念表述
> 配套：`财务RAG-Agent面试话术卡-v1.0.md`（怎么讲）/ 本文档（讲什么）
> 三张架构图均为 SVG，可直接在浏览器打开导出 PNG 用于论文插图

---

## 1. Agent 本质（四要素）

**定义**：如果说 LLM 是一颗"大脑"，那么 Agent 就是这颗大脑加上了眼睛、手、记忆，以及一个能让它自己循环工作的身体。

**四要素**：

| 要素 | 是什么 | 开发者要做吗 |
|------|--------|------------|
| 大脑（LLM） | 推理与决策 | 唯一不用自己做的部分 |
| 手（工具） | 与外部世界交互（检索/计算/读写文件） | 要做 |
| 记忆（状态） | 短期（任务上下文）/ 长期（跨会话画像） | 要做 |
| 循环（Agent Loop） | 感知→思考→行动→感知，模型自己决定下一步 | 要做（灵魂） |

**Agent 与 Chatbot 的本质区别**：Chatbot 核心是"对话"——问一句答一句；Agent 核心是"完成任务"——模型在循环里自主决定要不要查资料、调工具、下一步干什么。**自主循环是灵魂**：不是"每次调用一次 LLM"，而是"模型自己决定下一步"。

<svg viewBox="0 0 680 330" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">
<title>Agent 四要素结构图</title>
<desc>Agent 由大脑 LLM、工具、记忆和自主循环四要素组成</desc>
<defs>
<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
<path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
</marker>
</defs>
<g>
<rect x="60" y="50" width="170" height="90" rx="12" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="145" y="74" text-anchor="middle" dominant-baseline="central" font-size="13" font-weight="500" fill="#0C447C">大脑（LLM）</text>
<text x="145" y="96" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#185FA5">推理与决策</text>
<text x="145" y="112" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#185FA5">唯一不用自己做的部分</text>
</g>
<g>
<rect x="255" y="50" width="170" height="90" rx="12" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text x="340" y="74" text-anchor="middle" dominant-baseline="central" font-size="13" font-weight="500" fill="#085041">手（工具）</text>
<text x="340" y="96" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#0F6E56">检索 / 计算 / 读写文件</text>
<text x="340" y="112" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#0F6E56">Function Calling / MCP</text>
</g>
<g>
<rect x="450" y="50" width="170" height="90" rx="12" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text x="535" y="74" text-anchor="middle" dominant-baseline="central" font-size="13" font-weight="500" fill="#3C3489">记忆（状态）</text>
<text x="535" y="96" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#534AB7">短期：任务上下文</text>
<text x="535" y="112" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#534AB7">长期：跨会话画像</text>
</g>
<g>
<rect x="90" y="200" width="500" height="90" rx="12" fill="#FAEEDA" stroke="#BA7517" stroke-width="0.5"/>
<text x="340" y="220" text-anchor="middle" dominant-baseline="central" font-size="12" font-weight="500" fill="#633806">循环（Agent Loop）— 灵魂</text>
<rect x="120" y="238" width="96" height="36" rx="8" fill="#FFFFFF" stroke="#EF9F27" stroke-width="0.5"/>
<text x="168" y="256" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#854F0B">感知</text>
<line x1="216" y1="256" x2="248" y2="256" stroke="#854F0B" stroke-width="1.5" marker-end="url(#arrow)"/>
<rect x="250" y="238" width="96" height="36" rx="8" fill="#FFFFFF" stroke="#EF9F27" stroke-width="0.5"/>
<text x="298" y="256" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#854F0B">思考</text>
<line x1="346" y1="256" x2="378" y2="256" stroke="#854F0B" stroke-width="1.5" marker-end="url(#arrow)"/>
<rect x="380" y="238" width="96" height="36" rx="8" fill="#FFFFFF" stroke="#EF9F27" stroke-width="0.5"/>
<text x="428" y="256" text-anchor="middle" dominant-baseline="central" font-size="12" fill="#854F0B">行动</text>
<line x1="428" y1="274" x2="428" y2="284" stroke="#854F0B" stroke-width="1.5"/>
<line x1="428" y1="284" x2="168" y2="284" stroke="#854F0B" stroke-width="1.5"/>
<line x1="168" y1="284" x2="168" y2="274" stroke="#854F0B" stroke-width="1.5" marker-end="url(#arrow)"/>
</g>
</svg>

---

## 2. 本系统架构：Tool-as-Subagent 层级子代理

### 2.1 概念

本系统采用**分层 Agent（Tool-as-Subagent）**架构：主 Agent（Supervisor，LangChain `create_agent`）负责理解、调度与汇总；计税、社保两个子 Agent（`tax_subagent` / `social_subagent`）同为 `create_agent` 构建的完整 Agent（拥有独立 system prompt、工具集与自主循环），但**对外接口被封装为 `@tool`，作为工具挂入主 Agent 的工具列表**。

**要点**：子 Agent 本身是完整的 Agent，但它不是"单独建一个 Agent 再通过外部消息/协议连接主 Agent"（那是 A2A 的做法），而是**直接作为一个工具挂进主 Agent 的工具列表**——调用即启动，返回即结束。一句话：**工具是 Agent，Agent 也是工具**。

### 2.2 挂载结构

<svg viewBox="0 0 680 400" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">
<title>Tool-as-Subagent 挂载结构图</title>
<desc>主 Agent 通过工具列表调用普通工具和子 Agent 工具，子 Agent 内部有独立循环并返回结果</desc>
<defs>
<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
<path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
</marker>
</defs>
<g>
<rect x="190" y="40" width="300" height="56" rx="12" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="340" y="60" text-anchor="middle" dominant-baseline="central" font-size="13" font-weight="500" fill="#0C447C">主 Agent（Supervisor）</text>
<text x="340" y="78" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#185FA5">create_agent 循环 · 理解/调度/汇总</text>
</g>
<line x1="340" y1="96" x2="340" y2="120" stroke="#185FA5" stroke-width="1.5" marker-end="url(#arrow)"/>
<text x="352" y="110" dominant-baseline="central" font-size="11" fill="#444441">工具调用（ToolNode）</text>
<line x1="340" y1="120" x2="170" y2="150" stroke="#0F6E56" stroke-width="1.5" marker-end="url(#arrow)"/>
<line x1="340" y1="120" x2="510" y2="150" stroke="#534AB7" stroke-width="1.5" marker-end="url(#arrow)"/>
<rect x="40" y="150" width="260" height="110" rx="12" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text x="170" y="168" text-anchor="middle" dominant-baseline="central" font-size="11" font-weight="500" fill="#085041">普通工具（8 个 @tool）</text>
<rect x="56" y="180" width="112" height="30" rx="6" fill="#FFFFFF" stroke="#5DCAA5" stroke-width="0.5"/>
<text x="112" y="195" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#085041">search_knowledge</text>
<rect x="176" y="180" width="112" height="30" rx="6" fill="#FFFFFF" stroke="#5DCAA5" stroke-width="0.5"/>
<text x="232" y="195" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#085041">calculate_income_tax</text>
<rect x="56" y="218" width="112" height="30" rx="6" fill="#FFFFFF" stroke="#5DCAA5" stroke-width="0.5"/>
<text x="112" y="233" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#085041">query_social_insurance</text>
<rect x="176" y="218" width="112" height="30" rx="6" fill="#FFFFFF" stroke="#5DCAA5" stroke-width="0.5"/>
<text x="232" y="233" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#085041">fill_tax_form …</text>
<rect x="340" y="150" width="300" height="110" rx="12" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text x="490" y="168" text-anchor="middle" dominant-baseline="central" font-size="11" font-weight="500" fill="#3C3489">子 Agent（对外也是 @tool）</text>
<rect x="356" y="180" width="130" height="64" rx="8" fill="#FFFFFF" stroke="#AFA9EC" stroke-width="0.5"/>
<text x="421" y="194" text-anchor="middle" dominant-baseline="central" font-size="11" font-weight="500" fill="#3C3489">tax_subagent</text>
<text x="421" y="210" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#534AB7">内部：独立 LLM 循环</text>
<text x="421" y="224" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#534AB7">专属工具：计算/画像</text>
<rect x="494" y="180" width="130" height="64" rx="8" fill="#FFFFFF" stroke="#AFA9EC" stroke-width="0.5"/>
<text x="559" y="194" text-anchor="middle" dominant-baseline="central" font-size="11" font-weight="500" fill="#3C3489">social_subagent</text>
<text x="559" y="210" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#534AB7">内部：独立 LLM 循环</text>
<text x="559" y="224" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#534AB7">专属工具：社保/画像</text>
<line x1="490" y1="260" x2="340" y2="300" stroke="#534AB7" stroke-width="1.5" marker-end="url(#arrow)"/>
<line x1="170" y1="260" x2="340" y2="300" stroke="#0F6E56" stroke-width="1.5" marker-end="url(#arrow)"/>
<text x="310" y="285" text-anchor="end" dominant-baseline="central" font-size="11" fill="#444441">返回 JSON 五字段协议</text>
<rect x="190" y="300" width="300" height="44" rx="10" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="340" y="322" text-anchor="middle" dominant-baseline="central" font-size="12" font-weight="500" fill="#0C447C">主 Agent 汇总 → SSE 流式输出</text>
<rect x="40" y="360" width="600" height="30" rx="8" fill="#FAEEDA" stroke="#BA7517" stroke-width="0.5"/>
<text x="340" y="375" text-anchor="middle" dominant-baseline="central" font-size="11" fill="#633806">子 Agent = 完整 Agent，但对外接口是 @tool —— 调用即启动，返回即结束，不需要外部连接</text>
</svg>

### 2.3 为什么这么设计（三个理由）

1. **领域隔离**：计税/社保各自有独立 system prompt 和工具集，避免 prompt 互相污染（单 Agent 全做实测会串）。
2. **容错设计**：
   - **降级机制（v1.4）**：子 Agent 未计算出结果卡时，复用 LLM 已生成的 `tool_calls` 参数直调确定性引擎——功能不因子 Agent 失败而不可用；
   - **绕过检测（v1.5）**：检测到 LLM 在回答中"心算"税额（`_contains_tax_amount` 正则）但无结果卡时，强制重算——数字必须来自确定性引擎，绝不用 LLM 心算数字。
3. **可回退验证**：`AGENT_MODE=tools` 一键回退纯工具形态，用对拍评测（8/8）验证拆分确实有收益——不是为架构而架构。

### 2.4 与其它多 Agent 形态的区分

| 形态 | 特征 | 适用 |
|------|------|------|
| Workflow | 固定流程，Router 分发，无自主决策 | 流程固定 |
| **Tool-as-Subagent（本系统）** | 主 Agent 将子 Agent 作为工具调用，信息汇聚回流 | 子任务边界清晰 |
| 自由通信 Multi-Agent（A2A） | Agent 对等通信、互相协商 | 任务需多轮交叉协商 |

> A2A 是谷歌推出的**对等通信协议**（MCP 管 Agent-工具，A2A 管 Agent-Agent）。本系统子 Agent 是"被调用的工具"，不是对等体。

---

## 3. Agent Loop 详解（本系统循环如何工作）

### 3.1 循环机制

本系统 Agent Loop 由 LangChain `create_agent` 实现（ReAct 模式）。LLM 每次被调用，输出只有两种：

| 输出类型 | 含义 | 说明 |
|---------|------|------|
| `tool_calls` | 模型"思考后"决定调用哪个工具、参数是什么 | **思考的产物**——隐式完成"要不要查、查什么、参数是什么"的判断 |
| 最终回答 | 模型认为不需要再调工具，可以回答了 | 循环的出口 |

<svg viewBox="0 0 680 380" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">
<title>主 Agent 问答循环流程图</title>
<desc>用户提问后，主 Agent 循环执行 LLM 决策与工具调用，直到输出最终答案</desc>
<defs>
<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
<path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
</marker>
</defs>
<rect x="230" y="30" width="220" height="40" rx="10" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="340" y="50" text-anchor="middle" dominant-baseline="central" font-size="12" font-weight="500" fill="#0C447C">用户提问（SSE）</text>
<line x1="340" y1="70" x2="340" y2="92" stroke="#185FA5" stroke-width="1.5" marker-end="url(#arrow)"/>
<rect x="40" y="92" width="600" height="170" rx="14" fill="#F1EFE8" stroke="#888780" stroke-width="0.5"/>
<text x="60" y="110" dominant-baseline="central" font-size="11" font-weight="500" fill="#444441">主 Agent 循环（LangChain create_agent 内部）</text>
<rect x="70" y="124" width="160" height="60" rx="10" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="150" y="142" text-anchor="middle" dominant-baseline="central" font-size="12" font-weight="500" fill="#0C447C">LLM 调用</text>
<text x="150" y="160" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#185FA5">隐式思考（决策）</text>
<text x="150" y="174" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#185FA5">输出 tool_calls 或答案</text>
<rect x="280" y="124" width="320" height="56" rx="10" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text x="440" y="142" text-anchor="middle" dominant-baseline="central" font-size="12" font-weight="500" fill="#085041">工具执行（可见动作）</text>
<text x="440" y="160" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#0F6E56">search_knowledge / tax_subagent / 确定性引擎</text>
<line x1="230" y1="154" x2="278" y2="154" stroke="#0F6E56" stroke-width="1.5" marker-end="url(#arrow)"/>
<text x="254" y="144" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#444441">调用</text>
<path d="M440 180 C440 210 560 210 560 180 L560 164 C560 150 520 140 440 140 L440 122" fill="none" stroke="#0F6E56" stroke-width="1.5" marker-end="url(#arrow)"/>
<text x="545" y="168" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#444441">结果回填</text>
<path d="M150 184 C150 230 60 230 60 270 L60 300" fill="none" stroke="#185FA5" stroke-width="1.5" marker-end="url(#arrow)"/>
<text x="68" y="262" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#444441">无 tool_calls</text>
<text x="68" y="276" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#444441">（直接回答）</text>
<rect x="60" y="300" width="220" height="40" rx="10" fill="#FAEEDA" stroke="#BA7517" stroke-width="0.5"/>
<text x="170" y="320" text-anchor="middle" dominant-baseline="central" font-size="12" font-weight="500" fill="#633806">最终回答（循环出口）</text>
<rect x="360" y="292" width="260" height="56" rx="10" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text x="490" y="308" text-anchor="middle" dominant-baseline="central" font-size="11" font-weight="500" fill="#3C3489">SSE 事件：答案 + 结果卡片 + 溯源</text>
<text x="490" y="326" text-anchor="middle" dominant-baseline="central" font-size="10" fill="#534AB7">前端只渲染这层 · 中间过程隐藏</text>
<line x1="280" y1="320" x2="358" y2="320" stroke="#534AB7" stroke-width="1.5" marker-end="url(#arrow)"/>
</svg>

### 3.2 一次真实问答的完整循环（"我工资 8000 交多少税"）

| 步骤 | 发生什么 | 界面可见？ |
|------|---------|----------|
| ① LLM 第 1 次调用 | 输入 = system prompt + 画像 + 问题 → 隐式思考：这是计算题 → 输出 `tool_calls: tax_subagent("工资8000，算个税")` | ✗ |
| ② 工具执行 | 主 Agent 调用 `tax_subagent` 工具 → **子 Agent 内部跑自己的循环**（子 LLM 决策 → 调 `calculate_income_tax(8000)` → 确定性引擎算出应纳税额与明细）→ 打包 result_card 返回 | 只看到结果卡片的"结果" |
| ③ 结果回填 | 工具返回值写回主 Agent 消息历史（`tool` 消息） | ✗ |
| ④ LLM 第 2 次调用 | 看到工具结果 → 组织自然语言 + 附税率表溯源 → 输出最终答案（无 tool_calls）→ 循环出口 | ✓ 答案 + 卡片 + 溯源 |

### 3.3 为什么界面上看不到"思考环节"

1. **模型默认不输出思考文本**：`create_agent` 只消费 `tool_calls` 与最终文本，不暴露推理过程。思考不是没发生，而是**没有可见形态**——`tool_calls` 本身就是思考的产物。
2. **前端只渲染头与尾**：SSE 事件仅有答案/结果卡片/溯源/摘要提示，工具调用中间过程在产品层隐藏——这是 UX 决策（界面干净），不是循环不存在。

**循环的可见证据**：一次问答的后端日志 `messages` 序列为 `user → ai(tool_calls) → tool → ai(tool_calls) → tool → ai(最终答案)`。**工具调用 = 思考的可见证据**——看到模型主动调对工具、用对参数，就是思考在发生。

### 3.4 观测规划（trace）

现状：有评测（批量对比），缺单次执行 trace。规划：`backend/context/trace.py` 轻量 trace logger，每轮执行写一行 JSONL——模型调用输入输出、工具调用参数/返回值/耗时、每步 token、失败重试。**改 Prompt 是猜，读 trace 是查。**

---

## 4. Multi-Agent 选型评估（为什么不需要自由通信）

### 4.1 结论

**不需要自由通信 Multi-Agent（A2A）。Tool-as-Subagent 是正确终点（"验证过的少量拆分"）。**

### 4.2 三标准逐项对照（全不满足）

| 自由通信的判断标准 | 本系统场景 | 判定 |
|------------------|-----------|------|
| 天然可并行（同时查 20 家公司） | 用户一次只问一个问题，无并行需求 | ✗ |
| 信息量超单个上下文窗口 | 单问题信息量小，一个 Agent 轻松装下 | ✗ |
| 任务价值高、付得起数倍 token | 单用户场景，成本敏感 | ✗ |

### 4.3 四大功能全景判断

| 功能 | 当前实现 | 需要 Agent？ | 需要自由通信？ |
|------|---------|-------------|--------------|
| 智能问答 | 主 Agent + `search_knowledge`（RAG） | 主 Agent 本身就是 | 不需要 |
| 税率计算 | 计税子 Agent → 确定性引擎 | 已有（领域隔离） | 不需要 |
| 社保查询 | 社保子 Agent → 确定性引擎 | 已有（领域隔离） | 不需要 |
| 申报指引 | `filing_guide` 工具 + 静态页面 | 工具足够 | 不需要 |
| 材料生成 | `fill_tax_form` 字段映射填表 | 工具足够（**纯确定性，最不该上 Agent**） | 不需要 |

### 4.4 4 类"伪 Multi-Agent"信号澄清

| 信号 | 它其实是什么问题 | 正解 |
|------|----------------|------|
| 用户多、并发大 | 并发/性能问题 | 任务队列 + 异步，不是加 Agent |
| 批量生成 50 份申报表 | 批量执行问题 | 队列 + 批处理，不是加 Agent |
| 上下文太长 | 上下文工程问题 | 压缩/摘要/分层检索（已有 guard + 摘要） |
| 一个任务结果反复喂给另一任务 | 可能真需要协商 | 唯一值得升级的信号，但先从单 Agent + 多工具试起 |

---

## 5. 关键表述摘录（论文/答辩可直接引用）

1. **Agent 定义**：LLM 是大脑，Agent = 大脑 + 工具 + 记忆 + 自主循环；Agent 开发 = 做"模型以外的一切"（Harness）。
2. **自主循环是灵魂**：不是"每次调用一次 LLM"，而是"模型自己决定下一步"。
3. **工具调用 = 思考的可见证据**：`tool_calls` 是模型隐式决策的产物。
4. **工具是 Agent，Agent 也是工具**：Tool-as-Subagent 的本质。
5. **用确定性的基础设施，包住非确定性的模型**：本系统金额计算全部走纯代码引擎，LLM 只负责理解与调度（零幻觉设计哲学）。
6. **按需演进，不提前堆复杂度**：Multi-Agent 选型原则——先问"要不要拆"，再问"怎么拆"。
