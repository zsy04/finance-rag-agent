# 财税助手 · 图标资源清单

> **生成日期**：2026-07-26
> **图标总数**：20 枚（17 SVG + 3 Favicon PNG）
> **存放路径**：`frontend/public/icons/`
> **风格**：扁平化 · 线性图标 · 2px stroke · 深藏蓝 `#1E3A8A` · 圆角端点 · 透明背景

---

## 文件清单

| # | 文件名 | 中文名称 | 尺寸 | 格式 | 用途 |
|---|--------|----------|------|------|------|
| 1 | `logo.svg` | Logo | 64×64 | SVG | TopBar(48px)、WelcomeScreen(64px) |
| 2 | `icon-chat.svg` | 对话 | 24×24 | SVG | 左侧导航栏、Tab Bar |
| 3 | `icon-calculator.svg` | 税率计算 | 24×24 | SVG | 导航栏、结果卡片标题 |
| 4 | `icon-document.svg` | 申报材料 | 24×24 | SVG | 左侧导航栏 |
| 5 | `icon-help.svg` | 帮助提示 | 24×24 | SVG | 表单字段 tooltip |
| 6 | `icon-warning.svg` | 警告/免责 | 24×24 | SVG | 免责声明、错误横幅 |
| 7 | `icon-location.svg` | 城市位置 | 24×24 | SVG | TopBar 城市标识 |
| 8 | `icon-loading.svg` | 加载中 | 24×24 | SVG | 发送按钮加载态（CSS spin） |
| 9 | `icon-send.svg` | 发送 | 24×24 | SVG | 聊天输入框发送按钮 |
| 10 | `icon-confirm.svg` | 确认 | 24×24 | SVG | Agent 确认操作按钮 |
| 11 | `icon-edit.svg` | 编辑/自定义 | 24×24 | SVG | "自己填"按钮 |
| 12 | `icon-retry.svg` | 重试 | 24×24 | SVG | 错误气泡重试按钮 |
| 13 | `icon-save.svg` | 保存草稿 | 24×24 | SVG | 表单保存按钮 |
| 14 | `icon-generate.svg` | 生成/创建 | 24×24 | SVG | "生成申报表"按钮 |
| 15 | `icon-download.svg` | 下载 | 24×24 | SVG | "下载已填表"按钮 |
| 16 | `icon-blank-doc.svg` | 空白文档 | 24×24 | SVG | "下载空白原表"按钮 |
| 17 | `favicon.svg` | Logo/Favicon | 64×64 | SVG | 内嵌 favicon（可选） |
| 18 | `favicon-16.png` | Favicon 小 | 16×16 | PNG | 浏览器标签页图标 |
| 19 | `favicon-32.png` | Favicon 标准 | 32×32 | PNG | 浏览器标签页图标（标准） |
| 20 | `favicon-180.png` | Apple Touch Icon | 180×180 | PNG | iOS 主屏幕图标 |

---

## 前端接入方式

### 方式一：React 组件导入（推荐 ✅）

```tsx
import ChatIcon from '/icons/icon-chat.svg?react';

<ChatIcon className="w-6 h-6 text-[var(--color-primary)]" />
```

### 方式二：img 标签引用

```tsx
<img src="/icons/icon-chat.svg" alt="对话" className="w-6 h-6" />
```

### 方式三：CSS 背景图

```css
.nav-icon {
  width: 24px;
  height: 24px;
  background-image: url('/icons/icon-chat.svg');
  background-size: contain;
  background-repeat: no-repeat;
}
```

### 方式四：动态变色（currentColor）

所有 SVG 的 stroke 使用硬编码 `#1E3A8A`。如需通过 CSS 控制颜色，可将 SVG 中 `stroke="#1E3A8A"` 替换为 `stroke="currentColor"`：

```tsx
<div style={{ color: 'var(--color-primary)' }}>
  <img src="/icons/icon-chat.svg" alt="" style={{ width: 24 }} />
</div>
```

或使用 CSS mask 方式（完全由 CSS 控制颜色）：

```css
.icon-mask {
  mask: url('/icons/icon-chat.svg') no-repeat center / contain;
  -webkit-mask: url('/icons/icon-chat.svg') no-repeat center / contain;
  background-color: currentColor;
  width: 24px;
  height: 24px;
}
```

---

## 各功能模块图标速查

### 导航栏图标（24×24px）

| 图标 | 文件名 | 用途 |
|------|--------|------|
| 💬 对话 | `icon-chat.svg` | 智能问答入口 |
| 🔢 计算 | `icon-calculator.svg` | 税率计算入口 |
| 📄 材料 | `icon-document.svg` | 申报材料入口 |

### 操作按钮图标（可缩放）

| 图标 | 文件名 | 场景 |
|------|--------|------|
| ❓ 帮助 | `icon-help.svg` | 字段 tooltip（缩放至 16px） |
| ⚠️ 警告 | `icon-warning.svg` | 免责声明 / 错误提示 |
| 📍 位置 | `icon-location.svg` | 城市选择器（16px） |
| ⏳ 加载 | `icon-loading.svg` | 加载动画（需 CSS spin） |
| ➤ 发送 | `icon-send.svg` | 发送消息（20px） |
| ✓ 确认 | `icon-confirm.svg` | Agent 确认操作（16px） |
| ✏️ 编辑 | `icon-edit.svg` | 自定义输入模式（16px） |
| 🔄 重试 | `icon-retry.svg` | 错误重试（16px） |
| 💾 保存 | `icon-save.svg` | 保存草稿（16px） |
| ✨ 生成 | `icon-generate.svg` | 生成申报表（16px） |
| ⬇ 下载 | `icon-download.svg` | 下载已填表单（16px） |
| 📋 空白文档 | `icon-blank-doc.svg` | 下载空白模板（16px） |

---

## Favicon 配置

在 `index.html` 的 `<head>` 中添加：

```html
<link rel="icon" type="image/svg+xml" href="/icons/favicon.svg" />
<link rel="icon" type="image/png" sizes="32x32" href="/icons/favicon-32.png" />
<link rel="icon" type="image/png" sizes="16x16" href="/icons/favicon-16.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/icons/favicon-180.png" />
```

---

## CSS 动画：Loading 旋转

`icon-loading.svg` 是带缺口的圆环，通过 CSS 实现旋转效果：

```css
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.icon-spinning {
  animation: spin 1s linear infinite;
}
```

```tsx
<img src="/icons/icon-loading.svg" alt="加载中" className="w-5 h-5 icon-spinning" />
```

---

## 颜色规范

| 属性 | 值 |
|------|-----|
| 主色 | `#1E3A8A`（深藏蓝） |
| CSS 变量 | `var(--color-primary, #1E3A8A)` |
| Tailwind | `text-[#1E3A8A]` 或自定义 `text-primary` |

---

## 生成信息

- **方案**：手写 SVG 代码（方案 A）
- **工具**：Python 批量脚本 `scripts/gen_icons.py`
- **Favicon PNG**：由 sharp (Node.js) 从 logo.svg 缩放导出
