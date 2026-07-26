# 财务 RAG 前端 · AI 开发上下文

> **面向**：AI 编码助手（Claude / GPT / Copilot） | **依据**：`财务RAG-UI设计方案.md` + `财务RAG-开发注意事项.md`
> **用法**：将本文内容粘贴到 AI 对话开头，作为开发上下文，AI 将遵循本文全部规范生成前端代码

---

## 1. 项目技术选型

```yaml
框架: React 18+ (TypeScript)
构建: Vite
UI库: shadcn/ui (最新版)
样式: Tailwind CSS v4
图标: lucide-react
状态管理: React Context + useReducer (不引入第三方库)
```

初始化命令：
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npx shadcn@latest init -d
npx shadcn@latest add button input select card textarea
npm install lucide-react
```

---

## 2. 设计令牌（复制到 `src/index.css` 或 `globals.css`）

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --color-primary: #1E3A8A;
    --color-primary-light: #DBEAFE;
    --color-primary-dark: #172554;
    --color-text-primary: #0F172A;
    --color-text-secondary: #475569;
    --color-text-tertiary: #94A3B8;
    --color-bg-page: #F1F5F9;
    --color-bg-surface: #FFFFFF;
    --color-border: #CBD5E1;
    --color-success: #15803D;
    --color-warning: #B45309;
    --color-error: #B91C1C;
    --color-info: #1E40AF;
    --font-primary: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
    --font-mono: 'JetBrains Mono', 'Courier New', monospace;
    --radius-sm: 4px;
    --radius-md: 6px;
    --radius-lg: 8px;
    --radius-full: 9999px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.06);
    --shadow-md: 0 2px 4px rgba(0,0,0,0.08);
    --transition-fast: 120ms ease;
    --transition-base: 200ms ease;
  }
  * { font-family: var(--font-primary); }
}
```

---

## 3. TypeScript 类型定义 (`src/lib/types.ts`)

```typescript
// ====== 视图导航 ======
export type ActiveView = 'chat' | 'calculator' | 'form';

// ====== 对话消息 ======
export type MessageRole = 'user' | 'assistant' | 'system';

export interface Source {
  title: string;
  url: string;
}

export interface TaxResult {
  taxable_income: number;
  tax_amount: number;
  rate: string;
  monthly_tax?: number;
  breakdown?: string[];
}

export interface SocialResult {
  breakdown: Record<string, { employer: number; employee: number }>;
  total_personal: number;
  total_employer: number;
}

export interface ConfirmPrompt {
  question: string;
  options: string[];
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  // 计算结果卡片（税率 or 社保）
  resultCard?: { type: 'tax_result' | 'social_result'; data: TaxResult | SocialResult } | null;
  // 计算过程步骤
  steps?: string[];
  // RAG 来源引用
  sources?: Source[];
  // 需要用户确认的交互
  confirmPrompt?: ConfirmPrompt | null;
  // 状态标记
  isStreaming?: boolean;
  isError?: boolean;
}

// ====== 对话上下文（跨视图共享） ======
export interface UserContext {
  city: string;
  salary?: number;
  incomeType?: string;
  deductions: Record<string, number>;
}

// ====== SSE 事件 ======
export type SSEEventType =
  | 'thinking'
  | 'step'
  | 'confirm'
  | 'result'
  | 'source'
  | 'disclaimer'
  | 'error'
  | 'done';

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}
```

---

## 4. 组件文件树

```
frontend/src/
├── App.tsx                      # 根组件：整体布局
├── main.tsx                     # 入口
├── index.css                    # CSS 令牌 + Tailwind
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx          # 左侧导航栏
│   │   └── TopBar.tsx           # 顶部栏
│   ├── chat/
│   │   ├── ChatView.tsx         # 对话视图容器
│   │   ├── ChatMessage.tsx      # 单条消息（气泡 + 卡片 + 步骤）
│   │   ├── ChatInput.tsx        # 底部输入框
│   │   ├── WelcomeScreen.tsx    # 对话空态欢迎页
│   │   └── ResultCard.tsx       # 计算结果卡片组件
│   ├── calculator/
│   │   └── TaxCalculator.tsx    # 税率计算器表单
│   ├── form/
│   │   └── FilingForm.tsx       # 申报材料生成表单
│   └── shared/
│       ├── Skeleton.tsx         # 骨架屏
│       └── ErrorBanner.tsx      # 错误横幅
├── hooks/
│   ├── useChat.ts               # 对话核心逻辑（SSE + 消息状态）
│   └── useUserContext.tsx       # 上下文记忆 + 跨视图同步
├── lib/
│   ├── types.ts                 # 所有 TypeScript 类型
│   └── sse.ts                   # fetch + ReadableStream SSE 封装
└── context/
    └── AppContext.tsx            # 全局状态 Provider（视图 + 上下文）
```

---

## 5. SSE 工具函数 (`src/lib/sse.ts`)

```typescript
import type { SSEEvent } from './types';

/**
 * 使用 fetch + ReadableStream 消费 SSE 流
 * EventSource 不支持 POST 和自定义 headers，因此用本函数替代
 */
export async function* streamChat(
  message: string,
  context: Record<string, unknown> = {}
): AsyncGenerator<SSEEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context }),
  });

  if (!response.ok) {
    yield { type: 'error', data: { message: `请求失败: ${response.status}` } };
    return;
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let currentEvent: string | null = null;

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEvent) {
        try {
          const data = JSON.parse(line.slice(6));
          yield { type: currentEvent as SSEEvent['type'], data };
        } catch {
          // 跳过无法解析的行
        }
        currentEvent = null;
      }
    }
  }
}
```

---

## 6. 核心 Hook (`src/hooks/useChat.ts`)

```typescript
import { useState, useCallback, useRef } from 'react';
import type { Message, UserContext } from '@/lib/types';
import { streamChat } from '@/lib/sse';

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (content: string, context: UserContext) => {
    // 1. 添加用户消息
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
    };
    setMessages(prev => [...prev, userMsg]);

    // 2. 创建 AI 占位消息
    const assistantMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      isStreaming: true,
    };
    setMessages(prev => [...prev, assistantMsg]);
    setIsLoading(true);

    try {
      // 3. 流式消费 SSE
      for await (const event of streamChat(content, context)) {
        setMessages(prev =>
          prev.map(msg => {
            if (msg.id !== assistantMsg.id) return msg;
            switch (event.type) {
              case 'step':
                return { ...msg, steps: [...(msg.steps || []), event.data.content as string] };
              case 'result':
                return { ...msg, resultCard: event.data as Message['resultCard'] };
              case 'source':
                return { ...msg, sources: [...(msg.sources || []), event.data as any] };
              case 'confirm':
                return { ...msg, confirmPrompt: event.data as any, isStreaming: false };
              case 'thinking':
                return msg;
              case 'done':
                return { ...msg, isStreaming: false };
              case 'error':
                return { ...msg, content: event.data.message as string, isError: true, isStreaming: false };
              default:
                return msg;
            }
          })
        );
      }
    } catch {
      setMessages(prev =>
        prev.map(msg =>
          msg.id === assistantMsg.id
            ? { ...msg, content: '网络请求失败，请重试', isError: true, isStreaming: false }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  const retry = useCallback((messageId: string) => {
    // 移除失败消息，重新发送上一条用户消息
    setMessages(prev => {
      const idx = prev.findIndex(m => m.id === messageId);
      const userMsg = prev.slice(0, idx).reverse().find(m => m.role === 'user');
      if (userMsg) {
        return prev.filter(m => m.id !== messageId);
      }
      return prev;
    });
  }, []);

  return { messages, isLoading, sendMessage, retry };
}
```

---

## 7. 全局上下文 (`src/context/AppContext.tsx`)

```typescript
import { createContext, useContext, useState, ReactNode } from 'react';
import type { ActiveView, UserContext } from '@/lib/types';

interface AppState {
  activeView: ActiveView;
  setActiveView: (view: ActiveView) => void;
  userContext: UserContext;
  updateUserContext: (partial: Partial<UserContext>) => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeView, setActiveView] = useState<ActiveView>('chat');
  const [userContext, setUserContext] = useState<UserContext>({
    city: '郑州',
    deductions: {},
  });

  const updateUserContext = (partial: Partial<UserContext>) => {
    setUserContext(prev => ({ ...prev, ...partial }));
  };

  return (
    <AppContext.Provider value={{ activeView, setActiveView, userContext, updateUserContext }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
```

---

## 8. 根组件结构 (`src/App.tsx`)

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
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}
```

---

## 9. 关键组件规范

### Sidebar — 左侧导航栏

- 默认宽度 64px，hover 时扩至 200px
- 三个导航项：💬 智能对话 / 📊 税率计算 / 📄 申报材料
- 使用 lucide-react 的 `MessageCircle`, `Calculator`, `FileText` 图标
- `transition: width 200ms ease; transition-delay: 50ms` 防止误触
- 选中态：`background: var(--color-primary-light); color: var(--color-primary)`

### ChatView — 对话视图

- 占据整个 main 区域
- 消息列表 `overflow-y-auto flex-1`，底部输入框 `sticky bottom-0`
- 空态渲染 `<WelcomeScreen />`
- 加载中时输入框 `disabled`，发送按钮显示旋转图标
- 错误消息气泡红色左边框，底部 `[重试]` 按钮

### ChatMessage — 消息气泡

- `role === 'user'`：深藏蓝底白字，右对齐，`max-width: 70%`，圆角 `16px 16px 4px 16px`
- `role === 'assistant'`：浅灰蓝底近黑字，左对齐，`max-width: 85%`，圆角 `16px 16px 16px 4px`
- 如果有 `steps`，在气泡内先渲染步骤列表（小号等宽字体）
- 如果有 `resultCard`，在气泡内渲染 `<ResultCard />`
- 如果有 `confirmPrompt`，气泡底部渲染交互按钮
- 如果有 `sources`，气泡底部渲染折叠来源区
- `isStreaming` 时在内容末尾显示闪烁光标

### WelcomeScreen — 空态

- 居中显示 "🧾 欢迎使用财税助手"
- 副标题："👋 我是你的 AI 财税顾问，可以帮你：计算个税和社保 / 解答财税问题 / 生成申报材料"
- 3 个示例问题按钮（点击填入输入框并发送）
- 示例问题："工资 8000 在郑州交多少税？" "租房能扣多少税？" "帮我生成个税申报表"

### ResultCard — 计算卡片

- 白底 + 左侧 4px 深藏蓝装饰条 + `border-radius: 8px` + `padding: 16px`
- 标题行：📊 图标 + 标题文字
- 数值区：`font-mono` 等宽字体显示金额
- 可折叠的"展开计算过程"区域（默认折叠）
- 底部法规引用链接

### TaxCalculator — 税率计算器

- 表单字段：收入类型下拉、月薪输入、城市下拉、7 项扣除 checkbox + 金额输入
- 每个字段右侧 `❓` 图标，hover 显示 tooltip 解释
- 底部"开始计算"按钮（`btn-primary`）
- 结果区初始隐藏，提交后显示 `<ResultCard />`
- 底部"💡 想了解更多？切换到对话模式"链接

### FilingForm — 申报表单

- 表单字段分成三区：基本信息 / 收入信息 / 扣除信息
- 扣除信息区与 TaxCalculator 复用样式
- 底部两个按钮：`[💾 保存草稿]`（btn-secondary）+ `[📋 生成申报表]`（btn-primary）
- "保存草稿"写入 localStorage
- 结果区渲染 Markdown 表格预览 + `[📥 下载填好的表]` + `[📄 下载空白原表]` 按钮

---

## 10. 组件样式速查

| 场景 | Tailwind Class / CSS |
|------|---------------------|
| 主按钮 | `bg-[var(--color-primary)] text-white h-10 px-4 rounded-[6px] font-medium hover:bg-[var(--color-primary-dark)] hover:-translate-y-px transition-all disabled:opacity-50` |
| 次按钮 | `bg-white text-[var(--color-primary)] border border-[var(--color-primary)] h-10 px-4 rounded-[6px] font-medium hover:bg-[var(--color-primary-light)] transition-all` |
| 输入框 | `h-10 border border-[var(--color-border)] rounded-[6px] px-3 text-base focus:border-[var(--color-primary)] focus:ring-[3px] focus:ring-[var(--color-primary-light)] outline-none` |
| 用户气泡 | `bg-[var(--color-primary)] text-white rounded-[16px_16px_4px_16px] max-w-[70%] px-4 py-3 ml-auto` |
| AI 气泡 | `bg-[var(--color-bg-page)] text-[var(--color-text-primary)] rounded-[16px_16px_16px_4px] max-w-[85%] px-4 py-3` |
| 结果卡片 | `bg-white border border-[#E2E8F0] border-l-4 border-l-[var(--color-primary)] rounded-[8px] p-4` |
| 骨架屏 | `animate-pulse bg-gray-200 rounded` |
| 金额数字 | `font-mono` |
| 加载旋转 | lucide-react `<Loader2 className="animate-spin" />` |
| 错误气泡 | `border-l-4 border-l-[var(--color-error)]` |

---

## 11. 移动端适配

> ⚠️ **MVP 仅开发桌面端（≥768px）**。移动端列入 Phase 2，当前阶段不需要编写移动端样式或组件。

```css
/* MVP 最低宽度约束 */
.app-container { min-width: 768px; }
```

如未来扩展到移动端，预留方案：
- <768px 时导航改底部 Tab Bar
- 表单扣除项默认折叠
- 消息气泡放宽至 85%

---

## 12. 无障碍检查清单（AI 生成每段代码时自查）

- [ ] 按钮/链接使用 `<button>` / `<a>` 语义标签
- [ ] 输入框有关联 `<label>` 或 `aria-label`
- [ ] 可点击元素 ≥ 44×44px 触摸区域
- [ ] `:focus-visible` 时 2px 深藏蓝 outline
- [ ] 消息列表使用 `role="log"` + `aria-live="polite"`
- [ ] 错误消息使用 `role="alert"`
- [ ] 动画使用 `prefers-reduced-motion` 包裹

---

## AI 编码提示

> 将本文内容作为上下文提供给 AI 时，使用以下 prompt 开头：

```
你是一个 React + TypeScript 前端开发专家。请严格按照以下规范生成代码：

- 框架：Vite + React 18 + TypeScript
- UI 库：shadcn/ui + Tailwind CSS v4
- 图标：lucide-react
- 状态管理：React Context + useReducer
- 设计令牌：见附录 CSS 变量
- 组件规范：见"关键组件规范"章节
- SSE 通信：使用 fetch + ReadableStream（不用 EventSource）
- 无障碍：WCAG AA 标准

生成代码时，文件名和目录结构严格遵循"组件文件树"章节。
```
