# 前端开发规范 — AI 编码上下文

你是一个 React + TypeScript 前端工程师。请严格遵循以下规范生成代码，不得偏离。

---

## 0. 项目概览

**产品**：财税助手 — 面向零财务基础用户的 AI 财税问答 Web 应用。
**三个视图**：智能对话（chat） / 税率计算器（calculator） / 申报材料生成（form），通过左侧导航切换。
**仅桌面端**（≥768px），不做移动端。

## 0.1 技术约束

```
框架: React 18 + TypeScript
构建: Vite
UI: shadcn/ui (最新) + Tailwind CSS v4
图标: lucide-react
状态: React Context + useReducer，不引入第三方状态库
```

初始化：
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npx shadcn@latest init -d
npx shadcn@latest add button input select card textarea
npm install lucide-react
```

## 0.2 CSS 令牌

全局样式文件（`src/index.css`）必须包含以下变量。所有组件必须使用这些变量，不得硬编码颜色值。

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --color-primary: #014DB2;
    --color-primary-light: #EBF2FD;
    --color-primary-dark: #001645;
    --color-text-primary: #0A1628;
    --color-text-secondary: #6B7280;
    --color-text-tertiary: #9CA3AF;
    --color-bg-page: #F5F6F8;
    --color-bg-surface: #FFFFFF;
    --color-border: #E5E7EB;
    --color-success: #15803D;
    --color-warning: #B45309;
    --color-error: #B91C1C;
    --color-info: #014DB2;
    --font-primary: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
    --font-mono: 'JetBrains Mono', 'Courier New', monospace;
    --radius-sm: 4px; --radius-md: 6px; --radius-lg: 8px; --radius-full: 9999px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.06); --shadow-md: 0 2px 4px rgba(0,0,0,0.08);
    --transition-fast: 120ms ease; --transition-base: 200ms ease;
  }
  * { font-family: var(--font-primary); }
}
```

## 0.3 Vite 代理

```typescript
// vite.config.ts
export default defineConfig({
  server: { proxy: { '/api': 'http://localhost:8000' } }
})
```

---

## 1. TypeScript 类型定义

文件：`src/lib/types.ts`

```typescript
export type ActiveView = 'chat' | 'calculator' | 'form';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  resultCard?: { type: string; data: Record<string, unknown> } | null;
  steps?: string[];
  sources?: { title: string; url: string }[];
  isStreaming?: boolean;
  isError?: boolean;
}

// 注意：对话上下文由 Agent 内部管理（get_user_context / update_user_context @tool），
// 前端不需要传递 context。以下 UserContext 仅用于快捷表单间数据预填。
export interface UserContext {
  city: string;
  salary?: number;
  incomeType?: string;
  deductions: Record<string, number>;
}
```

---

## 2. 组件文件树

所有文件必须严格按以下路径创建：

```
frontend/src/
├── App.tsx
├── main.tsx
├── index.css
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx         # 左导航 64px→hover 200px
│   │   └── TopBar.tsx          # 顶栏 Logo+城市
│   ├── chat/
│   │   ├── ChatView.tsx        # 对话容器
│   │   ├── ChatMessage.tsx     # 单条消息
│   │   ├── ChatInput.tsx       # 底部输入框
│   │   ├── WelcomeScreen.tsx   # 空态欢迎
│   │   └── ResultCard.tsx      # 计算卡片
│   ├── calculator/
│   │   └── TaxCalculator.tsx   # 税率计算器
│   ├── form/
│   │   └── FilingForm.tsx      # 申报表单
│   └── shared/
│       ├── Skeleton.tsx
│       └── ErrorBanner.tsx
├── hooks/
│   ├── useChat.ts
│   └── useUserContext.tsx
├── lib/
│   ├── types.ts
│   └── sse.ts
└── context/
    └── AppContext.tsx
```

---

## 3. SSE 流式消费

文件：`src/lib/sse.ts`

```typescript
export async function* streamChat(
  message: string,
  threadId: string
): AsyncGenerator<{ type: string; data: Record<string, unknown> }> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!res.ok) {
    yield { type: 'error', data: { message: `请求失败 ${res.status}` } };
    return;
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent: string | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEvent) {
        try {
          yield { type: currentEvent, data: JSON.parse(line.slice(6)) };
        } catch { /* skip unparseable */ }
        currentEvent = null;
      }
    }
  }
}
```

**SSE 事件处理表**：

| 事件类型 | 触发时机 | 前端行为 |
|---------|---------|---------|
| `thinking` | Agent 开始处理 / 工具调用 / **工具错误（非致命）** | 输入框 disabled，发送按钮旋转圈，显示"正在为您计算……"。工具错误不中断流式 |
| `step` | 计算每步 / LLM 逐 token | 流式追加文字到 AI 气泡 content（字符串累加） |
| `result` | 计算/填表完成 | 在气泡内插入 `<ResultCard />` 组件 |
| `source` | RAG 检索来源 | 气泡底部折叠区，显示来源标题+链接 |
| `disclaimer` | AI 免责声明 | 气泡末尾追加灰色小字 |
| `error` | **致命**处理失败（Agent 无法继续） | 气泡红色左边框 + 错误文案 + `[🔄重试]` 按钮。**若 content 已有文本则不覆盖** |
| `done` | 回复完成 | 恢复输入框可用，停止闪烁光标 |

> **注意**：`confirm` 事件已移除。Agent 反问用户以自然语言通过 `step` 事件承载（如"请问你的收入类型是工资还是劳务报酬？"以普通流式文本呈现）。
>
> **关键变更（2026-07-31）**：`on_tool_error` 不再发送 `error` 事件，改为 `thinking` 事件（工具错误非致命，Agent 会自行处理并继续）。AI 回复内容用 `<MarkdownRenderer />` 渲染（react-markdown + remark-gfm）。

---

## 4. 核心 Hook

文件：`src/hooks/useChat.ts`

```typescript
import { useState, useCallback } from 'react';
import type { Message } from '@/lib/types';
import { streamChat } from '@/lib/sse';

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = useCallback(async (content: string) => {
    const userMsg: Message = {
      id: crypto.randomUUID(), role: 'user', content,
    };
    const aiMsg: Message = {
      id: crypto.randomUUID(), role: 'assistant', content: '', isStreaming: true,
    };
    setMessages(prev => [...prev, userMsg, aiMsg]);
    setIsLoading(true);

    for await (const event of streamChat(content, threadId)) {
      setMessages(prev => prev.map(m => {
        if (m.id !== aiMsg.id) return m;
        switch (event.type) {
          case 'step':    return { ...m, steps: [...(m.steps || []), event.data.content as string] };
          case 'result':  return { ...m, resultCard: event.data as Message['resultCard'] };
          case 'source':  return { ...m, sources: [...(m.sources || []), event.data as Message['sources'][number]] };
          case 'error':   return { ...m, content: event.data.message as string, isError: true, isStreaming: false };
          case 'done':    return { ...m, isStreaming: false };
          default:        return m;
        }
      }));
    }
    setIsLoading(false);
  }, []);

  return { messages, isLoading, sendMessage };
}
```

---

## 5. 全局上下文

文件：`src/context/AppContext.tsx`

```typescript
import { createContext, useContext, useState, type ReactNode } from 'react';
import type { ActiveView, UserContext } from '@/lib/types';

interface AppState {
  activeView: ActiveView;
  setActiveView: (v: ActiveView) => void;
  userContext: UserContext;
  updateUserContext: (partial: Partial<UserContext>) => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeView, setActiveView] = useState<ActiveView>('chat');
  const [userContext, setUserContext] = useState<UserContext>({
    city: '郑州', deductions: {},
  });
  const updateUserContext = (p: Partial<UserContext>) =>
    setUserContext(prev => ({ ...prev, ...p }));

  return (
    <AppContext.Provider value={{ activeView, setActiveView, userContext, updateUserContext }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be inside AppProvider');
  return ctx;
}
```

---

## 6. 根组件

文件：`src/App.tsx`

```tsx
import { AppProvider, useApp } from '@/context/AppContext';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { ChatView } from '@/components/chat/ChatView';
import { TaxCalculator } from '@/components/calculator/TaxCalculator';
import { FilingForm } from '@/components/form/FilingForm';

function AppContent() {
  const { activeView } = useApp();
  return (
    <div className="flex h-screen bg-[var(--color-bg-page)]">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          {activeView === 'chat' && <ChatView />}
          {activeView === 'calculator' && <TaxCalculator />}
          {activeView === 'form' && <FilingForm />}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return <AppProvider><AppContent /></AppProvider>;
}
```

---

## 7. 组件详细规范

### 7.1 Sidebar — 左侧导航

- 默认宽度 `64px`，hover 时扩至 `200px`（`transition: width var(--transition-base); transition-delay: 50ms`）
- 三个导航项，使用 lucide-react 图标：
  - `MessageCircle` → `activeView='chat'`
  - `Calculator` → `activeView='calculator'`
  - `FileText` → `activeView='form'`
- 每个 `nav-item`：`display:flex; align-items:center; gap:12px; padding:0 16px; height:48px; border-radius:6px; cursor:pointer`
- 选中态：`background: var(--color-primary-light); color: var(--color-primary)`
- 未展开时只显示图标，展开后显示图标+文字标签

### 7.2 TopBar — 顶部栏

- 全宽，`position: sticky; top: 0; z-index: 10; height: 48px`
- 左侧：产品名 `🧾 财税助手`（`font-weight: 600; color: var(--color-primary)`）
- 右侧：城市标识 `📍 郑州 ▼`（下拉框，MVP 仅展示不可切换）

### 7.3 ChatView — 对话视图

- 聊天消息列表（`flex-1 overflow-y-auto`）+ 底部输入框（`sticky bottom-0`）
- 空态渲染 `<WelcomeScreen />`
- 加载中：输入框 `disabled`，发送按钮显示 `<Loader2 className="animate-spin" />`，聊天流底部轻提示"正在为您计算……"

### 7.4 ChatMessage — 消息气泡

- `role === 'user'`：深藏蓝底白字，右对齐，`max-width:70%`，`border-radius: 16px 16px 4px 16px`
- `role === 'assistant'`：浅灰底近黑字，左对齐，`max-width:85%`，`border-radius: 16px 16px 16px 4px`
- 内容渲染顺序（从上到下）：
  1. 有 `steps` → 先渲染步骤列表（`font-mono text-sm`）
  2. 有 `resultCard` → 渲染 `<ResultCard />`
  3. 正文 `content`
  4. 有 `sources` → 底部折叠"📎 查看信息来源"
  5. 有 `disclaimer` → 灰色小字
  6. `isStreaming` → 末尾闪烁光标
  7. `isError` → 红色左边框 + `[🔄 重试]` 按钮
- 所有金额数字必须使用 `font-mono`（等宽字体）

### 7.5 ResultCard — 计算结果卡片

- 白底 + 左侧 4px 深藏蓝装饰条：`border-l-4 border-l-[var(--color-primary)] rounded-[8px] p-4`
- 标题行：`📊` 图标 + 文字（`text-lg font-semibold`）
- 数值区：金额用 `font-mono text-3xl`
- 可折叠"展开计算过程"（`<details>`，默认折叠）
- 底部法规引用（`text-sm text-[var(--color-text-tertiary)]`），可点击跳转

### 7.6 WelcomeScreen — 空态欢迎

- 居中布局
- 大标题：`🧾 欢迎使用财税助手`
- 副标题：`👋 我是你的 AI 财税顾问，可以帮你：计算个税和社保 · 解答财税问题 · 生成申报材料`
- 3 个示例问题按钮（`suggestion-chip`），点击填入输入框并自动发送：
  - `"工资 8000 在郑州交多少税？"`
  - `"租房能扣多少税？"`
  - `"帮我生成个税申报表"`

### 7.7 TaxCalculator — 税率计算器

- 表单字段（从上到下）：
  - 收入类型：`<Select>` 下拉（综合所得/经营所得/劳务报酬）
  - 税前月薪：`<Input type="number">` + "元"
  - 所在城市：`<Select>` 下拉（默认"郑州"）
  - 分隔线 + "扣除项" 标题
  - 7 项扣除：每题 `<Checkbox>` + `<Input type="number">` 元/月
- 每个字段右侧 `❓` 图标，hover 弹出 `<Tooltip>` 解释字段含义
- 底部 `[🧮 开始计算]` 主按钮，点击 → `POST /api/tax/calculate`
- 按钮点击后变灰 + "计算中……"，结果区显示骨架屏
- 计算结果渲染 `<ResultCard />`
- 结果下方链接："💡 想了解更多？切换到对话模式"
- 计算结果自动调用 `updateUserContext`

### 7.8 FilingForm — 申报材料生成

- 表单分三区，每区有标题分隔：
  - **基本信息**：申报表类型下拉 / 姓名 / 身份证号
  - **收入信息**：任职单位 / 年收入 / 已预缴税额
  - **扣除信息**（与 TaxCalculator 扣除区样式复用）
- 如果对话中已提供个人信息，表单自动预填（读取 `userContext`）
- 底部两个按钮：
  - `[💾 保存草稿]`（次按钮）→ 写入 `localStorage`
  - `[📋 生成申报表]`（主按钮）→ 通过 Agent 对话通路生成（`fill_tax_form` @tool），无需独立 REST 端点
- 生成结果区：Markdown 表格预览 + `[📥 下载填好的表]` + `[📄 下载空白原表]`

---

## 8. 样式速查表

| 元素 | Tailwind Class（直接使用） |
|------|---------------------------|
| 主按钮 | `bg-[var(--color-primary)] text-white h-10 px-4 rounded-[6px] font-medium hover:bg-[var(--color-primary-dark)] hover:-translate-y-px transition-all duration-[120ms] disabled:opacity-50` |
| 次按钮 | `bg-white text-[var(--color-primary)] border border-[var(--color-primary)] h-10 px-4 rounded-[6px] font-medium hover:bg-[var(--color-primary-light)] transition-all` |
| 输入框 | `h-10 border border-[var(--color-border)] rounded-[6px] px-3 text-base focus:border-[var(--color-primary)] focus:ring-[3px] focus:ring-[var(--color-primary-light)] outline-none transition-all` |
| 用户气泡 | `bg-[var(--color-primary)] text-white rounded-[16px_16px_4px_16px] max-w-[70%] px-4 py-3 ml-auto` |
| AI 气泡 | `bg-[var(--color-bg-page)] text-[var(--color-text-primary)] rounded-[16px_16px_16px_4px] max-w-[85%] px-4 py-3` |
| 结果卡片 | `bg-white border border-[#E2E8F0] border-l-4 border-l-[var(--color-primary)] rounded-[8px] p-4` |
| 示例问题 | `bg-[var(--color-bg-page)] border border-[#E2E8F0] rounded-[8px] p-3 text-sm cursor-pointer hover:bg-[var(--color-primary-light)] hover:border-[#93C5FD] transition-all` |
| 骨架屏 | `animate-pulse bg-gray-200 rounded` |
| 金额数字 | `font-mono` |
| 加载图标 | `<Loader2 className="animate-spin" />` |
| 导航项 | `w-full h-12 flex items-center gap-3 px-4 rounded-[6px] text-sm cursor-pointer transition-all` |
| 导航项-选中 | `bg-[var(--color-primary-light)] text-[var(--color-primary)]` |

---

## 9. 后端 API 接口

| 前端操作 | 方法 | 路由 | 请求 | 响应类型 |
|---------|:--:|------|------|:--:|
| 发送消息 | POST | `/api/chat` | `{message, thread_id}` | SSE 流（7 种事件） |
| 税率计算（快捷表单） | POST | `/api/tax/calculate` | `{annual_income, income_type, social_insurance?, housing_rent?, children_edu?, elderly_support?, bonus?}` | JSON |
| 社保计算（快捷表单） | POST | `/api/social/calculate` | `{salary, employment_type, housing_fund_ratio?, flexible_base_level?}` | JSON |

> **备注**：对话上下文由 Agent 内部管理，前端不需要传递 `context`。申报表生成已融入 Agent 通路（`fill_tax_form` @tool），无独立 REST 端点。

---

## 10. 无障碍规范

生成每个组件时必须满足：

- 交互元素使用语义标签（`<button>` 而非 `<div onclick>`）
- 输入框有关联 `<label>` 或 `aria-label`
- 所有可点击元素最小触摸区域 44×44px
- `:focus-visible` 时显示 `outline: 2px solid var(--color-primary); outline-offset: 2px`
- 消息列表容器：`role="log" aria-live="polite"`
- 错误消息：`role="alert"`
- 动画包裹在 `@media (prefers-reduced-motion: no-preference)` 内
