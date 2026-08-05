# 财务 RAG Agent · 开发注意事项

> **文档类型**：前后端开发规范 | **依据**：`财务RAG-技术架构与Agent方案.md` + `财务RAG-UI设计方案.md` | **日期**：2026-07-26
> **本文定位**：编码阶段的唯一规范参考。前端复制 CSS 令牌、使用组件样式。后端参照 SSE 事件格式、API 协议。

---

## 一、设计令牌（CSS Variables）

前端直接复制到 `globals.css`：

```css
:root {
  /* ═══ 主色调 — 深藏蓝 ═══ */
  --color-primary: #1E3A8A;
  --color-primary-light: #DBEAFE;
  --color-primary-dark: #172554;

  /* ═══ 中性色 ═══ */
  --color-text-primary: #0F172A;
  --color-text-secondary: #475569;
  --color-text-tertiary: #94A3B8;
  --color-bg-page: #F1F5F9;
  --color-bg-surface: #FFFFFF;
  --color-border: #CBD5E1;

  /* ═══ 语义色 ═══ */
  --color-success: #15803D;
  --color-warning: #B45309;
  --color-error: #B91C1C;
  --color-info: #1E40AF;

  /* ═══ 字体 ═══ */
  --font-primary: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-mono: 'JetBrains Mono', 'Courier New', monospace;

  /* ═══ 字号 ═══ */
  --text-xs: 0.75rem; --text-sm: 0.875rem; --text-base: 1rem;
  --text-lg: 1.125rem; --text-xl: 1.25rem; --text-2xl: 1.5rem; --text-3xl: 1.875rem;

  /* ═══ 间距（4px基准） ═══ */
  --space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem;
  --space-4: 1rem; --space-6: 1.5rem; --space-8: 2rem; --space-12: 3rem;

  /* ═══ 圆角 ═══ */
  --radius-sm: 4px; --radius-md: 6px; --radius-lg: 8px; --radius-full: 9999px;

  /* ═══ 阴影 ═══ */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.06);
  --shadow-md: 0 2px 4px rgba(0,0,0,0.08);

  /* ═══ 过渡 ═══ */
  --transition-fast: 120ms ease;
  --transition-base: 200ms ease;
}
```

---

## 二、前端开发注意

### 2.1 组件样式（基于 shadcn/ui 定制）

**按钮**：
```css
.btn-primary { background: var(--color-primary); color: #FFF; height: 40px; border-radius: 6px; font-weight: 500; }
.btn-primary:hover { background: var(--color-primary-dark); transform: translateY(-1px); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary { background: var(--color-bg-surface); color: var(--color-primary); border: 1px solid var(--color-primary); height: 40px; border-radius: 6px; }
.btn-secondary:hover { background: var(--color-primary-light); }
```

**输入框**：
```css
.input { height: 40px; border: 1px solid var(--color-border); border-radius: 6px; padding: 0 12px; font-size: 16px; }
.input:focus { border-color: var(--color-primary); box-shadow: 0 0 0 3px rgba(30,58,138,0.15); outline: none; }
```

**结果卡片**：
```css
.result-card { background: #FFF; border: 1px solid #E2E8F0; border-left: 4px solid var(--color-primary); border-radius: 8px; padding: 16px; }
```

**消息气泡**：
```css
.bubble-user { background: var(--color-primary); color: #FFF; border-radius: 16px 16px 4px 16px; max-width: 70%; padding: 12px 16px; margin-left: auto; }
.bubble-ai   { background: var(--color-bg-page); color: var(--color-text-primary); border-radius: 16px 16px 16px 4px; max-width: 85%; padding: 12px 16px; }
```

**示例问题**：
```css
.suggestion-chip { background: var(--color-bg-page); border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 16px; cursor: pointer; }
.suggestion-chip:hover { background: var(--color-primary-light); border-color: #93C5FD; }
```

**导航项**：
```css
.nav-item { width: 100%; height: 48px; display: flex; align-items: center; gap: 12px; padding: 0 16px; border-radius: 6px; font-size: 14px; color: var(--color-text-secondary); cursor: pointer; }
.nav-item.active { background: var(--color-primary-light); color: var(--color-primary); }
```

### 2.2 布局约束

| 区域 | 约束 |
|------|------|
| 左侧导航栏 | 默认 64px → hover 扩至 200px；`transition: width 200ms ease; transition-delay: 50ms` |
| 顶部栏 | 全宽 + `sticky top-0 z-10`，高度 48px |
| 主内容区 | `overflow-y: auto` |
| 输入框区域 | 底部固定，`sticky bottom-0` |

> ⚠️ **MVP 仅桌面端（≥768px）**，移动端 Phase 2。布局最小宽度 `min-width: 768px`。

### 2.3 SSE 消费方式

```javascript
// 前端消费 SSE 流（9 种事件，2026-08-04 更新：+context，-confirm）
const eventSource = new EventSource('/api/chat?message=...');

eventSource.addEventListener('thinking',   (e) => { /* 加载提示 / 工具执行动画 */ });
eventSource.addEventListener('step',       (e) => { /* 追加流式文字到 AI 气泡 */ });
eventSource.addEventListener('result',     (e) => { /* 插入结果卡片 */ });
eventSource.addEventListener('source',     (e) => { /* 折叠展示来源 */ });
eventSource.addEventListener('disclaimer', (e) => { /* 灰字免责 */ });
eventSource.addEventListener('context',    (e) => { /* 📦 历史摘要归档提示条（Message.contextNotice） */ });
eventSource.addEventListener('error',      (e) => { /* 红色错误气泡 + 重试（已有内容不覆盖） */ });
eventSource.addEventListener('done',       (e) => { /* 恢复输入框 */ });
```

### 2.4 状态处理

| 状态 | 实现 |
|------|------|
| 对话加载中 | 发送按钮变旋转圈，输入框 `disabled`，聊天流底部显示"正在为您计算……" |
| 表单计算中 | 按钮变灰 + "计算中……"，结果区显示骨架屏 |
| 空态 | 居中欢迎语 + 3 个示例问题按钮（点击填入并发送） |
| API 错误 | AI 气泡红色边框 + "回答失败了，请重试" + [🔄 重试] 按钮 |
| 网络断开 | 顶部黄色横幅 "网络连接异常，请检查网络" |

### 2.5 无障碍检查清单

- [ ] 所有可点击元素 ≥ 44×44px
- [ ] 全部交互元素支持 Tab + Enter
- [ ] `:focus-visible` 时 2px 深藏蓝 outline
- [ ] 结果卡片 `role="region"` + `aria-label`
- [ ] 输入框关联 `<label>` 或 `aria-label`
- [ ] 错误消息 `role="alert"`
- [ ] 动效尊重 `prefers-reduced-motion`

---

## 三、后端开发注意

### 3.1 SSE 事件格式（前后端接口契约）

| 事件 | 触发 | JSON 数据 | 前端行为 |
|------|------|----------|---------|
| `thinking` | Agent 开始 | `{"message":"正在为您计算……"}` | 显示加载提示 |
| `step` | 计算每步 | `{"content":"月薪8000×12=年收入96000元"}` | 追加到 AI 气泡 |
| `confirm` | 需确认 | `{"question":"租房扣除按1500元?", "options":["确认","自己填"]}` | 暂停流式，显示按钮 |
| `result` | 计算完成 | `{"type":"tax_result", "data":{taxable_income, tax_amount, ...}}` | 插入结果卡片 |
| `source` | RAG 来源 | `{"title":"...", "url":"..."}` | 折叠展示来源 |
| `disclaimer` | 免责 | `{"content":"本结果由AI辅助计算……"}` | 灰色小字 |
| `error` | 失败 | `{"message":"回答失败了，请重试"}` | 错误气泡 + 重试 |
| `done` | 结束 | `{}` | 恢复输入框 |

### 3.2 FastAPI SSE 实现模板

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json, asyncio

app = FastAPI()

async def generate_sse(user_message: str):
    # 1. thinking
    yield f"event: thinking\ndata: {json.dumps({'message': '正在为您计算……'})}\n\n"

    # 2. steps — 模拟计算过程
    steps = [
        "月薪 8000 × 12 = 年收入 96,000 元",
        "起征点：60,000 元，剩余 36,000 元",
        "社保扣除：养老 640 + 医疗 160 + 失业 24 = 月扣 824，年扣 9,888 元",
        "应纳税所得额 = 96,000 - 60,000 - 9,888 - 18,000 = 8,112 元",
    ]
    for step in steps:
        yield f"event: step\ndata: {json.dumps({'content': step})}\n\n"
        await asyncio.sleep(0.3)

    # 3. result
    result = {"taxable_income": 8112, "tax_amount": 243.36, "rate": "3%"}
    yield f"event: result\ndata: {json.dumps({'type': 'tax_result', 'data': result})}\n\n"

    # 4. source
    yield f"event: source\ndata: {json.dumps({'title': '个人所得税法 附表一', 'url': '...'})}\n\n"

    # 5. disclaimer
    yield f"event: disclaimer\ndata: {json.dumps({'content': '本结果由AI辅助计算，仅供参考...'})}\n\n"

    # 6. done
    yield f"event: done\ndata: {json.dumps({})}\n\n"

@app.get("/api/chat")
async def chat(message: str):
    return StreamingResponse(
        generate_sse(message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
```

### 3.3 Agent 工具调度规范

| 规则 | 说明 |
|------|------|
| **信息不足时反问** | 缺少计算所需字段（收入类型、金额、城市）→ 先反问 1-2 个问题，不要猜测 |
| **计算走代码** | `calculate_income_tax` 和 `query_social_insurance` 必须读取 JSON + 公式，不走 LLM 推理 |
| **申报材料走字段映射** | `fill_tax_form` 是 key-value 填表，不是 LLM 生成 |
| **对话上下文** | 工具返回时附带 `user_context`，后续调用自动复用 |
| **白名单搜索** | `search_tax_website` 仅允许 7 个 gov.cn 域名 |

### 3.4 System Prompt 约束

```
你是"财税助手"，一个面向零财务基础大众的 AI 财税顾问。

规则：
1. 信息不足时，先反问 1-2 个问题收集信息，不要猜测
2. 税率计算走代码，不要自己推算
3. 每个计算结果附带分步推导和法规引用
4. 涉及金额的回复末尾必须附加 AI 免责声明
5. 使用简洁易懂的语言，避免专业术语，或在使用术语时附加解释
```

### 3.5 API 路由设计

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | GET | SSE 流式对话（query 参数：message） |
| `/api/chat` | POST | 同上（body：{message, context}） |
| `/api/calculate/tax` | POST | 税率计算（非流式，返回 JSON） |
| `/api/calculate/social` | POST | 社保计算 |
| `/api/form/generate` | POST | 申报表生成 |
| `/api/form/download/{form_type}` | GET | 下载空白原表 PDF |
| `/api/cities` | GET | 城市列表（MVP 返回 ["郑州"]） |

---

## 四、前后端协作检查清单

- [ ] 前端 CSS 变量与设计令牌一致
- [ ] SSE 事件类型前后端命名一致
- [ ] `confirm` 事件的 `options` 数组与前端的交互按钮一一对应
- [ ] `result` 事件的 `data` 字段结构前端能正确渲染为结果卡片
- [ ] 前端 `EventSource` 正确处理重连（后端断线后自动重连）
- [ ] 对话上下文（城市/工资/扣除项）在切回对话模式后自动恢复
- [ ] 表单数据与对话上下文双向同步（表单填的 → 对话能用；对话说的 → 表单预填）
