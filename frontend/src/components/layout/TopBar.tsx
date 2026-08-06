import { useEffect, useState, type ChangeEvent } from 'react';
import { useApp } from '@/context/AppContext';
import type { ActiveView } from '@/lib/types';
import { getModels } from '@/lib/sse';
import { loadProviders } from '@/lib/provider';
import { SettingsDialog } from '@/components/shared/SettingsDialog';
import { cn } from '@/lib/utils';

/** 顶栏 4 个功能 tab（2026-08-06 设计稿落地：导航从侧边栏移到顶栏）
 *  新建会话/历史记录已集成到左侧会话栏，顶栏不再放操作按钮 */
const NAV_TABS: { view: ActiveView; label: string }[] = [
  { view: 'chat', label: '智能问答' },
  { view: 'calculator', label: '税率计算' },
  { view: 'guide', label: '申报指引' },
  { view: 'form', label: '材料生成' },
];

export function TopBar() {
  const { activeView, setActiveView, activeProviderId, setActiveProviderId } = useApp();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toolIncompatHint, setToolIncompatHint] = useState(false);

  // 模板加载：预热 getModels（设置页打开时复用缓存）
  useEffect(() => {
    getModels().catch(() => {});
  }, []);

  // 切换模型时：非默认 provider 提示工具兼容性（Agent 依赖 function calling）
  function handleModelChange(e: ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value || null;
    setActiveProviderId(id);
    if (id) {
      // 自定义模型未经验证工具调用 → 提示；默认 DeepSeek 无需提示
      setToolIncompatHint(true);
      setTimeout(() => setToolIncompatHint(false), 4000);
    }
  }

  return (
    <header
      className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-surface)] px-6"
      role="banner"
    >
      {/* 左侧：Logo + 产品名（设计稿：lest 财税助手，深色 Bold） */}
      <div className="flex shrink-0 items-center gap-3">
        <img src="/icons/logo.svg" alt="财税助手" className="h-8 w-8" />
        <span className="text-lg font-bold text-[var(--color-text-primary)]">
          lest 财税助手
        </span>
      </div>

      {/* 中部：4 个功能 tab（铺满顶栏中间区域，均分宽度） */}
      <nav className="flex min-w-0 flex-1 items-stretch justify-center gap-2 px-4" aria-label="功能导航">
        {NAV_TABS.map(({ view, label }) => {
          const isActive = activeView === view;
          return (
            <button
              key={view}
              type="button"
              onClick={() => setActiveView(view)}
              aria-current={isActive ? 'page' : undefined}
              className={cn(
                'min-w-0 flex-1 max-w-[200px] rounded-lg px-4 py-2 text-sm transition-colors duration-150',
                isActive
                  ? 'bg-[var(--color-primary)] font-medium text-white'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-primary-light)] hover:text-[var(--color-primary)]',
              )}
            >
              {label}
            </button>
          );
        })}
      </nav>

      {/* 右侧：用户栏（模型切换器 2026-08-06 启用原预留区）— 模型下拉 + 设置入口 */}
      <div className="flex shrink-0 items-center gap-2">
        <div className="relative">
          <select
            aria-label="选择模型"
            value={activeProviderId ?? ''}
            onChange={handleModelChange}
            className="h-9 max-w-[160px] cursor-pointer rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] px-2 text-xs text-[var(--color-text-primary)] focus:border-[var(--color-primary)] focus:outline-none"
            title="切换模型（设置页可配置）"
          >
            <option value="">DeepSeek（默认）</option>
            {loadProviders().map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          {toolIncompatHint && (
            <div className="absolute right-0 top-10 z-20 w-56 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-2 text-xs text-[var(--color-text-secondary)] shadow-lg">
              当前模型未经验证支持工具调用。若计算类问题返回异常，请切回默认 DeepSeek。
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          aria-label="模型设置"
          title="模型设置"
          className="rounded-lg p-2 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-primary-light)] hover:text-[var(--color-primary)]"
        >
          ⚙
        </button>
      </div>

      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </header>
  );
}
