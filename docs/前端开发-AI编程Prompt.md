# 前端开发 · AI 编码 Prompt

> **用法**：将本文全部内容粘贴到 AI 对话中，然后说"请按此规范生成前端代码"
> **来源**：`docs/财务RAG-UI设计方案.md` + `docs/财务RAG-开发注意事项.md` + `docs/财务RAG-前后端对照表.md`

---

## 1. 技术选型

```
框架: React 18 + TypeScript
构建: Vite
UI库: shadcn/ui (最新)
样式: Tailwind CSS v4
图标: lucide-react
状态: React Context + useReducer (不用第三方库)
桌面: 仅开发桌面端 ≥768px，不做移动端
```

初始化：
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npx shadcn@latest init -d
npx shadcn@latest add button input select card textarea
npm install lucide-react
```

---

## 2. CSS 令牌 — 复制到 `globals.css`

```css
@layer base {
  :root {
    --color-primary: #1E3A8A;       --color-primary-light: #DBEAFE;
    --color-primary-dark: #172554;  --color-text-primary: #0F172A;
    --color-text-secondary: #475569;--color-text-tertiary: #94A3B8;
    --color-bg-page: #F1F5F9;      --color-bg-surface: #FFFFFF;
    --color-border: #CBD5E1;        --color-success: #15803D;
    --color-warning: #B45309;       --color-error: #B91C1C;
    --color-info: #1E40AF;
    --font-primary: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
    --font-mono: 'JetBrains Mono', 'Courier New', monospace;
    --radius-sm: 4px; --radius-md: 6px; --radius-lg: 8px; --radius-full: 9999px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.06); --shadow-md: 0 2px 4px rgba(0,0,0,0.08);
    --transition-fast: 120ms ease; --transition-base: 200ms ease;
  }
  * { font-family: var(--font-primary); }
}
```

---

## 3. TypeScript 类型

```typescript
// ====== 导航 ======
export type ActiveView = 'chat' | 'calculator' | 'form';

// ====== 消息 ======
export interface Message {
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

// ====== 上下文 ======
export interface UserContext {
  city: string;
  salary?: number;
  incomeType?: string;
  deductions: Record<string, number>;
}
```

---

## 4. 组件文件树

```
frontend/src/
├── App.tsx                    # 根：navigation + view switch
├── main.tsx
├── index.css                  # CSS tokens
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx        # 左侧导航 64px → hover 200px
│   │   └── TopBar.tsx         # 顶部栏：Logo + 城市标识
│   ├── chat/
│   │   ├── ChatView.tsx       # 对话容器
│   │   ├── ChatMessage.tsx    # 单条消息（气泡 + 卡片 + 步骤）
│   │   ├── ChatInput.tsx      # 底部输入框
│   │   ├── WelcomeScreen.tsx  # 空态欢迎页
│   │   └── ResultCard.tsx     # 计算卡片组件
│   ├── calculator/
│   │   └── TaxCalculator.tsx  # 税率计算器表单
│   ├── form/
│   │   └── FilingForm.tsx     # 申报表单
│   └── shared/
│       ├── Skeleton.tsx       # 骨架屏
│       └── ErrorBanner.tsx    # 错误横幅
├── hooks/
│   ├── useChat.ts             # 对话逻辑
│   └── useUserContext.tsx     # 上下文 Provider
├── lib/
│   ├── types.ts               # 类型定义
│   └── sse.ts                 # SSE 工具
└── context/
    └── AppContext.tsx          # 全局状态
```

---

## 5. SSE 流式消费 (`lib/sse.ts`)

```typescript
export async function* streamChat(
  message: string, context: Record<string, unknown> = {}
): AsyncGenerator<{type: string; data: Record<string, unknown>}> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context }),
  });
  if (!res.ok) { yield { type: 'error', data: { message: `请求失败 ${res.status}` } }; return; }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '', currentEvent: string | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    for (const line of buffer.split('\n')) {
      buffer = buffer.includes('\n') ? '' : line;
      if (line.startsWith('event: ')) currentEvent = line.slice(7).trim();
      else if (line.startsWith('data: ') && currentEvent) {
        try { yield { type: currentEvent, data: JSON.parse(line.slice(6)) }; } catch {}
        currentEvent = null;
      }
    }
  }
}
```

## 6. SSE 事件 → 前端行为

| 事件 | 后端何时发 | 前端行为 |
|------|-----------|---------|
| `thinking` | 开始处理 | 输入框 disabled + 旋转圈 + "正在为您计算……" |
| `step` | 计算每步 / LLM token | 流式追加到 AI 气泡末尾 |
| `confirm` | 需用户确认参数 | 暂停流式，显示 `[✅ 确认] [✏️ 自己填]` |
| `result` | 计算完成 | 插入 ResultCard 组件 |
| `source` | RAG 来源 | 折叠"查看信息来源" |
| `disclaimer` | AI 免责 | 回复末尾灰字"本结果由 AI 辅助……" |
| `error` | 失败 | 红色边框气泡 + `[🔄 重试]` |
| `done` | 结束 | 恢复输入框 |

## 7. 核心 Hook (`hooks/useChat.ts`)

```typescript
import { useState, useCallback } from 'react';
import type { Message, UserContext } from '@/lib/types';
import { streamChat } from '@/lib/sse';

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = useCallback(async (content: string, ctx: UserContext) => {
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content };
    const aiMsg: Message = { id: crypto.randomUUID(), role: 'assistant', content: '', isStreaming: true };
    setMessages(prev => [...prev, userMsg, aiMsg]);
    setIsLoading(true);

    for await (const event of streamChat(content, ctx)) {
      setMessages(prev => prev.map(m => {
        if (m.id !== aiMsg.id) return m;
        switch (event.type) {
          case 'step':   return { ...m, steps: [...(m.steps||[]), event.data.content as string] };
          case 'result': return { ...m, resultCard: event.data as any };
          case 'source': return { ...m, sources: [...(m.sources||[]), event.data as any] };
          case 'confirm':return { ...m, confirmPrompt: event.data as any, isStreaming: false };
          case 'error':  return { ...m, content: event.data.message as string, isError: true, isStreaming: false };
          case 'done':   return { ...m, isStreaming: false };
          default:       return m;
        }
      }));
    }
    setIsLoading(false);
  }, []);

  return { messages, isLoading, sendMessage };
}
```

## 8. 全局上下文 (`context/AppContext.tsx`)

```typescript
const AppContext = createContext<{activeView, setActiveView, userContext, updateUserContext} | null>(null);
export function AppProvider({ children }) {
  const [activeView, setActiveView] = useState<ActiveView>('chat');
  const [userContext, setUserContext] = useState<UserContext>({ city: '郑州', deductions: {} });
  return <AppContext.Provider value={{
    activeView, setActiveView,
    userContext,
    updateUserContext: (p) => setUserContext(prev => ({ ...prev, ...p })),
  }}>{children}</AppContext.Provider>;
}
export const useApp = () => useContext(AppContext)!;
```

## 9. 根组件 (`App.tsx`)

```tsx
function AppContent() {
  const { activeView } = useApp();
  return (
    <div className="flex h-screen bg-[var(--color-bg-page)]">
      <Sidebar />
      <div className="flex-1 flex flex-col">
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
```

## 10. 组件规范

### Sidebar
- 宽度 64px → hover 200px（`transition: 200ms ease; transition-delay: 50ms`）
- 三个 nav-item：`MessageCircle` 💬 对话 / `Calculator` 📊 计算 / `FileText` 📄 申报
- 选中态 `bg-[var(--color-primary-light)] text-[var(--color-primary)]`
- icon + 文字，hover 展开时显示文字标签

### TopBar
- 全宽，`sticky top-0 z-10`，高度 48px
- 左：`🧾 财税助手` + 右：`📍 郑州 ▼`

### ChatView
- 消息列表 + 底部输入框（`sticky bottom-0`）
- 空态：居中欢迎语 + 3 个示例问题卡片
- 加载中：输入框 disabled，发送按钮 `Loader2 animate-spin`

### ChatMessage
- `role=user`：深藏蓝底白字 右对齐 `max-w-[70%]` `rounded-[16px_16px_4px_16px]`
- `role=assistant`：浅灰底近黑字 左对齐 `max-w-[85%]` `rounded-[16px_16px_16px_4px]`
- 有 `steps` 时：气泡内先渲染步骤（`font-mono` `text-sm`）
- 有 `resultCard`：气泡内渲染 `<ResultCard />`
- 有 `confirmPrompt`：气泡底部按钮 `[确认] [自己填]`
- 有 `sources`：底部可折叠来源区
- `isStreaming` 时末尾闪烁光标
- `isError` 时红色左边框 + 底部 `[🔄 重试]`
- 金额数字必须 `font-mono`

### ResultCard
- 白底 `border-l-4 border-l-[var(--color-primary)]` `rounded-[8px] p-4`
- 标题：📊 + 文字
- 数值：`font-mono` `text-3xl`
- 可折叠"展开计算过程"（默认折叠）
- 底部法规引用可点击链接

### WelcomeScreen
- 居中 `🧾 欢迎使用财税助手`
- 副标题描述三个功能
- 3 个示例问题卡片：`"工资8000郑州交税"` `"租房能扣多少"` `"帮我生成申报表"`
- 点击填入输入框并发送

### TaxCalculator
- 字段：收入类型下拉 / 月薪 / 城市 / 7 项扣除 checkbox + 金额
- 每字段右侧 `❓` hover tooltip 解释
- 底部 `[🧮 开始计算]` → 调用 `/api/calculate/tax`
- 结果区：`<ResultCard />` + "💡 切换到对话模式"
- 计算结果自动 `updateUserContext`

### FilingForm
- 三区分组：基本信息 / 收入 / 扣除
- `[💾 保存草稿]` → localStorage
- `[📋 生成申报表]` → `/api/form/generate`
- 结果：Markdown 预览 + `[📥 下载]` + `[📄 空白原表]`
- 对话中已提供的信息自动预填

## 11. 样式速查

| 元素 | Tailwind class |
|------|---------------|
| 主按钮 | `bg-[var(--color-primary)] text-white h-10 px-4 rounded-[6px] font-medium hover:bg-[var(--color-primary-dark)] hover:-translate-y-px transition-all disabled:opacity-50` |
| 次按钮 | `bg-white text-[var(--color-primary)] border border-[var(--color-primary)] h-10 px-4 rounded-[6px]` |
| 输入框 | `h-10 border border-[var(--color-border)] rounded-[6px] px-3 text-base focus:border-[var(--color-primary)] focus:ring-[3px] focus:ring-[var(--color-primary-light)] outline-none` |
| 用户气泡 | `bg-[var(--color-primary)] text-white rounded-[16px_16px_4px_16px] max-w-[70%] px-4 py-3 ml-auto` |
| AI 气泡 | `bg-[var(--color-bg-page)] text-[var(--color-text-primary)] rounded-[16px_16px_16px_4px] max-w-[85%] px-4 py-3` |
| 结果卡片 | `bg-white border border-[#E2E8F0] border-l-4 border-l-[var(--color-primary)] rounded-[8px] p-4` |
| 骨架屏 | `animate-pulse bg-gray-200 rounded` |
| 金额 | `font-mono` |
| 加载 | `<Loader2 className="animate-spin" />` |

## 12. 后端 API

| 前端操作 | 方法 | 路由 | 请求体 |
|---------|:--:|------|--------|
| 发消息 | POST | `/api/chat` | `{message, context, thread_id}` → SSE |
| 税率计算 | POST | `/api/calculate/tax` | `{income_type, annual_income, city, deductions}` → JSON |
| 社保计算 | POST | `/api/calculate/social` | `{city, employment_type, salary}` → JSON |
| 申报表 | POST | `/api/form/generate` | `{form_type, user_profile}` → JSON |
| 下载原表 | GET | `/api/form/download/{type}` | → PDF |
| 城市列表 | GET | `/api/cities` | → `["郑州"]` |

## 13. Vite 代理配置

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: { '/api': 'http://localhost:8000' }
  }
})
```

## 14. 无障碍

- 按钮用 `<button>`，输入框关联 `<label>`
- 可点击元素 ≥ 44×44px
- `:focus-visible` → `outline: 2px solid #1E3A8A`
- 消息列表 `role="log" aria-live="polite"`
- 错误 `role="alert"`
- 动画包裹 `prefers-reduced-motion`
