# 财务 RAG Agent · 前后端对照表

> **用途**：联调时快速定位"前端这边该调哪个接口""后端这个事件前端怎么处理"
> **依据**：`财务RAG-开发注意事项.md` + `财务RAG-后端审查与重构方案.md`（v4 终版）
> **更新**：2026-07-31 — SSE 事件表更新（on_tool_error 改为 thinking 事件，error 事件非致命处理）

---

## 一、接口对照

| 前端操作 | HTTP | 后端路由 | 请求 | 响应 |
|---------|:--:|---------|------|------|
| 对话发送消息 | POST | `/api/chat` | `{message, thread_id}` | SSE 流（7 种事件） |
| 旧版直连问答 | POST | `/chat` | `{query}` | SSE 流（旧格式，token/done/error） |
| 税率计算器提交 | POST | `/api/tax/calculate` | `{annual_income, income_type, social_insurance?, housing_rent?, children_edu?, elderly_support?, bonus?}` | JSON |
| 社保计算器提交 | POST | `/api/social/calculate` | `{salary, employment_type, housing_fund_ratio?, flexible_base_level?}` | JSON |

> **备注**：对话上下文由 Agent 内部管理（`get_user_context` / `update_user_context` @tool），前端不需要传递 `context` 参数。申报表生成已融入 Agent 通路（`fill_tax_form` @tool），无独立 REST 端点。

---

## 二、SSE 事件对照

| 事件类型 | 后端何时发送 | 数据 payload | 前端收到后做什么 |
|---------|------------|-------------|----------------|
| `thinking` | Agent 开始处理 / 工具调用中 / **工具错误（非致命）** | `{"message": "正在为您处理……"}` 或 `{"tool": "工具名"}` 或 `{"tool_error": "..."}` | 显示加载提示 / 工具执行中动画。工具错误不中断流式 |
| `step` | LLM 逐 token 生成 | `{"content": "你好"}` | 追加流式文字到 AI 气泡 content（字符串累加） |
| `result` | 计算/填表完成 | `{"type": "tax_result\|social_result\|form_result", "data": {...}}` | 插入结果卡片（蓝色左边条 + 数据） |
| `source` | RAG 检索返回来源 | `{"title": "...", "url": "...", "tier": "...", "relation": "..."}` | 折叠显示来源链接 |
| `disclaimer` | AI 免责声明 | `{"text": "本结果由 AI 辅助……"}` | 灰色小字追加到回复末尾 |
| `error` | **致命**处理失败（Agent 无法继续） | `{"content": "错误消息"}` | 红色边框气泡 + `[🔄 重试]` 按钮。**若 content 已有文本则不覆盖** |
| `done` | 回复完成 | `{}` | 恢复输入框可用，停止闪烁光标 |

> **关键变更（2026-07-31）**：
> - `on_tool_error` 不再发送 `error` 事件，改为 `thinking` 事件（工具错误非致命，Agent 会自行处理并继续）
> - 前端 `error` 事件处理：若消息已有内容则不覆盖（保留 Agent 已生成的回答），仅空内容时显示错误

> **注意**：原设计中的 `confirm` 事件已降级为 LLM 自然反问（通过 `step` 事件承载），Agent 反问"请问你的收入类型是工资还是劳务报酬？"以普通流式文本呈现。

### SSE 格式

```
event: {event_type}
data: {json_payload}\n\n
```

所有 JSON 使用 `ensure_ascii=False`（中文不被转义）。

---

## 三、数据类型对照

### Message

```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  resultCard?: {
    type: 'tax_result' | 'social_result' | 'form_result';
    data: Record<string, unknown>;
  } | null;
  steps?: string[];
  sources?: Source[];
  isStreaming?: boolean;
  isError?: boolean;
}
```

### Tax Result（`result` 事件 data）

```typescript
// event: result → {"type": "tax_result", "data": {...}}
{
  type: "tax_result",
  data: {
    annual_income: number;       // 年收入
    income_type: string;         // salary|labor_service|manuscript|royalty
    taxable_basis: number;       // 计税基数（比例换算后）
    taxable_income: number;      // 应纳税所得额
    tax_amount: number;          // 应纳税额
    marginal_rate: string;       // 边际税率（如 "3%"）
    bracket_level: number;       // 税率级数
    formula: string;             // 计算公式
    breakdown: {
      annual_deduction: number;  // 起征点 60000
      social_insurance: number;  // 社保年扣除
      special_deductions: number;// 专项附加扣除
    };
    legal_basis: string;         // 法规依据
    bonus?: {                    // 年终奖（如有）
      amount: number;
      separate_tax: number;
      recommendation: string;
      saving: number;
    };
  }
}
```

### Social Result（`result` 事件 data）

```typescript
// event: result → {"type": "social_result", "data": {...}}
{
  type: "social_result",
  data: {
    city: string;                // zhengzhou
    employment_type: string;     // employee | flexible
    salary: number;              // 月工资
    social_insurance: {          // 职工社保
      base: number;
      breakdown: Record<string, {base, rate_company, rate_personal, company, personal}>;
      total_personal: number;
      total_company: number;
    };
    housing_fund: {              // 公积金
      base, ratio, personal, company
    };
    total_personal: number;      // 个人月缴合计
    total_company: number;       // 单位月缴合计
    legal_basis: string;
  }
}
```

### Form Result（`result` 事件 data — fill_tax_form）

```typescript
// event: result → {"type": "form_result", "data": {...}}
{
  type: "form_result",
  data: {
    form_type: string;           // "A表" | "B表"
    file_path: string;           // 生成的 xlsx 文件路径
    filled_fields: number;
    skipped_fields: string[];
  }
}
```

### Source（`source` 事件 data）

```typescript
{
  title: string;     // 文档标题（如 "个人所得税法"）
  url: string;       // 来源文件名
  tier: string;      // 相关性层级
  relation?: string; // 知识图谱关联标记（如 "知识图谱（1跳）"）
}
```

---

## 四、完整请求-响应流程

### 对话流（用户问一个问题）

```
前端                               后端
───                               ───
ChatInput.onSend()                 
  → POST /api/chat               
    {message, thread_id} ────────→ routers/chat.py
                                    → agent.astream_events(version="v2")
                                    → LLM 选工具 → 工具执行 → 生成回答
                                    
      ←─ event: thinking ────────  {"message": "正在为您处理……"}
      ←─ event: step ×N ─────────  LLM 逐 token 流式
      ←─ event: thinking ────────  {"tool": "get_user_context"}
      ←─ event: thinking ────────  {"tool": "calculate_income_tax"}
      ←─ event: result ──────────  {"type":"tax_result","data":{...}}
      ←─ event: disclaimer ──────  {"text": "本结果由 AI 辅助……"}
      ←─ event: step ×N ─────────  LLM 解释说明
      ←─ event: done ────────────  {}
    → ChatMessage 渲染完成
```

### 表单计算流（税率计算器快捷表单）

```
前端                               后端
───                               ───
TaxCalculator.onSubmit()
  → POST /api/tax/calculate ───→ routers/tax.py
    {annual_income, income_type,    → services/tax_engine.calculate()
     housing_rent, ...}               → 读取 JSON 税率表 → 公式计算
  ←── JSON ──────────────────────  {taxable_income, tax_amount, rate, ...}
  
  → ResultCard 渲染结果
```

---

## 五、对话上下文管理（Agent 内部管理）

Agent 通过 `get_user_context` / `update_user_context` 两个 @tool 自动管理对话上下文。前端不需要传递或维护上下文。

```
用户说"工资8000郑州"
  → Agent 调 update_user_context("salary", "8000")
  → Agent 调 update_user_context("city", "zhengzhou")
  → 下一轮对话中 Agent 调 get_user_context → 自动读取已有信息
```

---

## 六、端口与代理

```
开发环境：
  前端 Vite Dev Server  :5173
  后端 FastAPI          :8000
  Qdrant Dashboard      :6333

前端 vite.config.ts 代理配置：
export default defineConfig({
  server: {
    proxy: {
      '/api': 'http://localhost:8000'  // 前端请求 /api/* 自动转发到后端
    }
  }
})
```

---

## 七、联调检查清单

- [ ] **基础联通**：`curl localhost:8000/health` → `{"status": "ok"}`
- [ ] **前端代理**：浏览器 `localhost:5173/api/chat` → POST 请求可达
- [ ] **SSE 流式**：POST `/api/chat` → 看到 `event: thinking` → `event: step` → `event: done`
- [ ] **工具调用**：问"工资 8000 郑州税多少" → Agent 自动调 `calculate_income_tax` → 收到 `result` 事件
- [ ] **结果卡片**：`result` 事件 → 前端渲染蓝色左边条卡片（tax_result / social_result / form_result）
- [ ] **上下文记忆**：先说"我在郑州工资8000" → 再问"我个税多少" → Agent 自动复用信息（不需重复问）
- [ ] **来源引用**：问知识类问题 → 收到 `source` 事件 → 前端可折叠 + 链接可点击
- [ ] **AI 免责**：金额相关回复 → 收到 `disclaimer` 事件 → 回复末尾灰色小字
- [ ] **错误处理**：后端返回 `error` 事件 → 前端红色气泡 + 重试按钮可用
