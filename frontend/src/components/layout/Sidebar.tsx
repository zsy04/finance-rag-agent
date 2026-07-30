import { useApp } from '@/context/AppContext';
import { ChatSvg, CalculatorSvg, DocumentSvg } from '@/components/icons';
import type { ActiveView } from '@/lib/types';
import { cn } from '@/lib/utils';

const NAV_ITEMS: { view: ActiveView; label: string; Icon: typeof ChatSvg }[] = [
  { view: 'chat', label: '智能对话', Icon: ChatSvg },
  { view: 'calculator', label: '税率计算', Icon: CalculatorSvg },
  { view: 'form', label: '申报材料', Icon: DocumentSvg },
];

export function Sidebar() {
  const { activeView, setActiveView } = useApp();

  return (
    <nav
      className="group flex h-full flex-col items-center gap-2 border-r border-[var(--color-border)] bg-[var(--color-bg-surface)] py-4 transition-all duration-[var(--transition-base)] delay-50 w-16 hover:w-[200px]"
      aria-label="主导航"
    >
      {NAV_ITEMS.map(({ view, label, Icon }) => {
        const isActive = activeView === view;
        return (
          <button
            key={view}
            onClick={() => setActiveView(view)}
            className={cn(
              'flex h-12 w-full items-center gap-3 rounded-[var(--radius-md)] px-4 text-sm transition-all duration-[var(--transition-fast)]',
              'hover:bg-[var(--color-primary-light)]',
              isActive
                ? 'bg-[var(--color-primary-light)] text-[var(--color-primary)] font-medium'
                : 'text-[var(--color-text-secondary)]',
            )}
            aria-current={isActive ? 'page' : undefined}
          >
            <Icon className="h-6 w-6 shrink-0" />
            <span className="hidden whitespace-nowrap group-hover:inline">
              {label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
