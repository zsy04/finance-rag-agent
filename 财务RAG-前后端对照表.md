# 财务 RAG Agent · 前后端对照表

> **用途**：联调时快速定位"前端这边该调哪个接口""后端这个事件前端怎么处理"
> **依据**：`财务RAG-开发注意事项.md` + `财务RAG-后端开发路线图.md` + `财务RAG-UI设计方案.md`

---

## 一、接口对照

| 前端操作 | HTTP | 后端路由 | 请求 | 响应 |
|---------|:--:|---------|------|------|
| 对话发送消息 | POST | `/api/chat` | `{message, context, thread_id}` | SSE 流 |
| 税率计算器提交 | POST | `/api/calculate/tax` | `{income_type, annual_income, city, deductions}` | JSON |
| 社保计算器提交 | POST | `/api/calculate/social` | `{city, employment_type, salary}` | JSON |
| 申报表生成 | POST | `/api/form/generate` | `{form_type, user_profile}` | JSON |
| 下载空白原表 | GET | `/api/form/download/{form_type}` | — | PDF 文件 |
| 获取城市列表 | GET | `/api/cities` | — | `["郑州"]` |

---

## 二、SSE 事件对照

| 事件类型 | 后端何时发送 | 前端收到后做什么 | 前端组件 |
|---------|------------|----------------|---------|
| `thinking` | Agent 开始处理 | 显示"正在为您计算……"加载提示 | `ChatView` → 输入框 `disabled` + 旋转圈 |
| `step` | 计算每一步 / LLM 逐 token | 追加流式文字到 AI 气泡末尾 | `ChatMessage` → `isStreaming` 时末尾闪烁光标 |
| `confirm` | 需要用户确认关键参数 | 暂停流式，显示 `[✅ 确认] [✏️ 自己填]` 按钮 | `ChatMessage` → `confirmPrompt` 渲染交互 |
| `result` | 计算完成 | 插入结果卡片（蓝色左边条 + 金额 + 折叠推导） | `ResultCard` 组件 |
| `source` | RAG 检索来源 | 折叠显示来源链接 | `ChatMessage` → sources 折叠区 |
| `disclaimer` | AI 免责声明 | 灰色小字追加到回复末尾 | `ChatMessage` → 固定底部灰字 |
| `error` | 处理失败 | 红色边框气泡 + "回答失败" + `[🔄 重试]` 按钮 | `ChatMessage` → `isError` 样式 + 重试按钮 |
| `done` | 回复完成 | 恢复输入框可用，停止闪烁光标 | `ChatView` → 输入框恢复 |

---

## 三、数据类型对照

### Message

| 后端来源 | 前端 TypeScript |
|---------|----------------|
| Agent `messages` 数组 + SSE 事件 | `Message` interface |

```typescript
// 前端
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  resultCard?: { type: string; data: Record<string, unknown> } | null;
  steps?: string[];
  sources?: { title: string; url: string }[];
  confirmPrompt?: { question: string; options: string[] } | null;
  isStreaming?: boolean;
  isError?: boolean;
}
```

### Tax Result

| 后端 `calculate_income_tax` 返回 | 前端 `ResultCard` 渲染 |
|----------------------------------|------------------------|
| `{taxable_income, tax_amount, rate, level, legal_basis}` | 卡片标题 + 金额（`font-mono`）+ 可折叠推导 + 法规引用链接 |

### Social Result

| 后端 `query_social_insurance` 返回 | 前端 `ResultCard` 渲染 |
|-----------------------------------|------------------------|
| `{breakdown: {养老:{employer,employee},...}, total_personal, total_employer}` | 逐险种分行展示 + 个人/单位合计 |

### User Context（对话上下文）

| 后端 `context` 参数 | 前端 `UserContext` | 同步方向 |
|--------------------|-------------------|:--:|
| `city` | `useApp().userContext.city` | 双向 |
| `salary` | `useApp().userContext.salary` | 双向 |
| `incomeType` | `useApp().userContext.incomeType` | 双向 |
| `deductions` | `useApp().userContext.deductions` | 双向 |

---

## 四、完整请求-响应流程

### 对话流（用户问一个问题）

```
前端                               后端
───                               ───
ChatInput.onSend()                 
  → useChat.sendMessage()          
    → streamChat(message, ctx)     
      → POST /api/chat ──────────→ routers/chat.py
                                    → agent.engine.agent.astream_events()
                                    → LLM 选工具 → 工具执行 → 生成回答
                                    
      ←─ SSE event: thinking ────  "正在为您处理……"
      ←─ SSE event: step ─────────  "月薪 8000 × 12 = 96,000 元"
      ←─ SSE event: step ─────────  "起征点 60,000 元……"
      ←─ SSE event: confirm ──────  "租房扣除按 1500 元？"
      
      用户点击 [✅ 确认]
      → POST /api/chat (带 confirm=yes)
      ←─ SSE event: step ─────────  继续计算
      ←─ SSE event: result ───────  {taxable_income: 8112, ...}
      ←─ SSE event: source ───────  {title: "个人所得税法", url: "..."}
      ←─ SSE event: disclaimer ────  "本结果由 AI 辅助……"
      ←─ SSE event: done ──────────  结束
    → setMessages 更新状态
    → ChatMessage 渲染完成
```

### 表单计算流（税率计算器）

```
前端                               后端
───                               ───
TaxCalculator.onSubmit()
  → POST /api/calculate/tax ────→ routers/calculate.py
    {income_type, annual_income,      → services/tax_engine.calculate()
     city, deductions}                  → 读取 JSON 税率表 → 公式计算
  ←── JSON ──────────────────────  {taxable_income, tax_amount, rate, ...}
  
  → ResultCard 渲染结果
  → updateUserContext({salary, city, deductions})  // 同步到上下文
```

---

## 五、对话上下文的双向同步

```
[对话模式] ←──────────────────→ [税率计算器] ←──────────────────→ [申报表单]
    │                                │                                │
    │  用户说"工资8000郑州"            │  用户填表计算                   │  用户填表生成
    │  Agent 提取并存入 context       │  结果存入 context               │  复用 context 预填
    │                                │                                │
    └────────────── AppContext.userContext ─────────────────────────────┘
                    {city, salary, incomeType, deductions}
```

- 对话中 Agent 提取的信息 → `updateUserContext()` → 表单自动预填
- 表单中填入的信息 → `updateUserContext()` → 切回对话时 Agent 无需再问
- `useApp()` hook 是唯一的数据源，三视图共享同一份 context

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

这样前端代码里直接写 `fetch('/api/chat', ...)`，不需要写 `http://localhost:8000`，也不会有 CORS 问题。

---

## 七、联调检查清单

按开发顺序逐项验证：

- [ ] **基础联通**：`curl localhost:8000/health` → `{"status": "ok"}`
- [ ] **前端代理**：浏览器 `localhost:5173/api/cities` → `["郑州"]`
- [ ] **SSE 流式**：前端发消息 → 看到逐字流式输出（Step 7 联调）
- [ ] **工具调用**：问"工资 8000 郑州税多少" → Agent 自动调 `calculate_income_tax` → 收到 `result` 事件
- [ ] **结果卡片**：`result` 事件 → 前端渲染蓝色左边条卡片
- [ ] **确认交互**：`confirm` 事件 → 前端暂停流式 + 显示按钮 → 点确认 → 继续
- [ ] **上下文记忆**：对话说"工资 8000 郑州" → 切到计算器 → 字段预填 → 切回对话 → Agent 记得
- [ ] **来源引用**：`source` 事件 → 前端可折叠 + 链接可点击
- [ ] **AI 免责**：`disclaimer` 事件 → 回复末尾灰色小字
- [ ] **错误处理**：后端返回 `error` → 前端红色气泡 + 重试按钮可用
- [ ] **空白表下载**：申报表单点"下载空白原表" → PDF 正确下载
