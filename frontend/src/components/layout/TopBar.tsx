import { LocationSvg } from '@/components/icons';

export function TopBar() {
  return (
    <header
      className="sticky top-0 z-10 flex h-12 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-surface)] px-6"
      role="banner"
    >
      {/* 左侧：Logo + 产品名 */}
      <div className="flex items-center gap-2">
        <img src="/icons/logo.svg" alt="财税助手" className="h-8 w-8" />
        <span className="text-base font-semibold text-[var(--color-primary)]">
          财税助手
        </span>
      </div>

      {/* 右侧：城市标识（MVP 仅展示，不可切换） */}
      <div className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)]">
        <LocationSvg className="h-4 w-4" />
        <span>郑州</span>
      </div>
    </header>
  );
}
