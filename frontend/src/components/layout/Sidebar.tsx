import { useApp } from '@/context/AppContext';
import { ChatSvg, DocumentSvg, BenchmarkSvg } from '@/components/icons';
import type { ThreadMeta } from '@/lib/types';
import { cn } from '@/lib/utils';

interface SidebarProps {
  threads: ThreadMeta[];
  currentThreadId: string;
  /** 流式回答中禁用新建/删除/切换 */
  disabled?: boolean;
  onSelectThread: (threadId: string) => void;
  onCreateThread: () => void;
  onDeleteThread: (threadId: string) => void;
}

/** 折叠态 3 个关键图标（2026-08-06 设计稿落地：仅保留会话/政策法规/行业基准，申报记录已删） */
const FOLD_ICONS: { view: 'documents' | 'benchmark'; label: string; Icon: typeof ChatSvg }[] = [
  { view: 'documents', label: '政策法规', Icon: DocumentSvg },
  { view: 'benchmark', label: '行业基准', Icon: BenchmarkSvg },
];

/** 消息数 + 时间元信息（按 updated_at 分档：今天/昨天/MM-DD） */
function formatMeta(count: number, updatedAt?: string): string {
  const meta = `${count} 条消息`;
  if (!updatedAt) return meta;
  const d = new Date(updatedAt);
  if (Number.isNaN(d.getTime())) return meta;
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dayDiff = Math.round((startOfToday.getTime() - startOfDay.getTime()) / 86400000);
  if (dayDiff === 0) {
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${meta} · 今天 ${hh}:${mm}`;
  }
  if (dayDiff === 1) return `${meta} · 昨天`;
  const MM = String(d.getMonth() + 1).padStart(2, '0');
  const DD = String(d.getDate()).padStart(2, '0');
  return `${meta} · ${MM}-${DD}`;
}

export function Sidebar({
  threads,
  currentThreadId,
  disabled,
  onSelectThread,
  onCreateThread,
  onDeleteThread,
}: SidebarProps) {
  const { setActiveView, activeView } = useApp();

  return (
    <nav
      className="group flex h-full w-16 flex-col overflow-y-auto border-r border-[var(--color-border)] bg-[var(--color-bg-surface)] py-4 transition-all duration-200 delay-50 hover:w-[300px] focus-within:w-[300px]"
      aria-label="主导航"
    >
      {/* ── 会话区（独立分区，展开时完整显示） ── */}
      <div className="flex w-full items-center justify-between px-4">
        <span className="hidden text-xs text-[var(--color-text-tertiary)] group-hover:inline">
          会话
        </span>
        <button
          type="button"
          onClick={onCreateThread}
          disabled={disabled}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[var(--color-primary)] text-white transition-colors hover:bg-[var(--color-primary-dark)] disabled:cursor-not-allowed disabled:opacity-50"
          title="新建会话"
          aria-label="新建会话"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </div>

      {/* 会话列表（仅展开时可见；不撑满，资料库紧贴其后自然挪移） */}
      <div className="mt-2 hidden flex-col group-hover:flex">
        {threads.map((t) => {
          const isCurrent = t.thread_id === currentThreadId;
          return (
            <div key={t.thread_id} className="thread-item group/item flex w-full items-center rounded-lg">
              <button
                type="button"
                onClick={() => onSelectThread(t.thread_id)}
                disabled={disabled}
                className={cn(
                  'animate-drop-in flex h-10 min-w-0 flex-1 flex-col items-start justify-center gap-0.5 rounded-lg px-3 text-left transition-colors',
                  'hover:bg-[var(--color-primary-light)]',
                  isCurrent
                    ? 'border border-[var(--color-primary)]/25 bg-[var(--color-primary-light)]'
                    : 'border border-transparent bg-transparent',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
                title={t.title || '新会话'}
              >
                <span
                  className={cn(
                    'w-full truncate text-sm',
                    isCurrent
                      ? 'font-medium text-[var(--color-primary)]'
                      : 'text-[var(--color-text-primary)]',
                  )}
                >
                  {t.title || '新会话'}
                </span>
                <span className="w-full truncate text-[11px] text-[var(--color-text-tertiary)]">
                  {formatMeta(t.message_count ?? 0, t.updated_at)}
                </span>
              </button>
              <button
                type="button"
                onClick={() => onDeleteThread(t.thread_id)}
                disabled={disabled}
                className="mr-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-error)]/10 hover:text-[var(--color-error)] disabled:cursor-not-allowed disabled:opacity-50"
                title="删除会话"
                aria-label={`删除会话 ${t.title || '新会话'}`}
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
          );
        })}
      </div>

      {/* 分隔线（展开时显示，紧贴会话列表下方） */}
      <div className="mx-4 mt-3 hidden border-t border-[var(--color-border)] group-hover:block" />

      {/* ── 资料库区（展开显示，紧贴会话区；折叠态只留图标） ── */}
      <div className="mt-3 hidden w-full flex-col group-hover:flex">
        <span className="px-4 text-xs text-[var(--color-text-tertiary)]">资料库</span>
        {FOLD_ICONS.map(({ view, label, Icon }) => {
          const isActive = activeView === view;
          return (
            <button
              key={view}
              type="button"
              onClick={() => setActiveView(view)}
              className={cn(
                'thread-item animate-drop-in flex h-10 w-full items-center gap-3 rounded-md px-4 text-sm',
                'hover:bg-[var(--color-primary-light)]',
                isActive
                  ? 'bg-[var(--color-primary-light)] font-medium text-[var(--color-primary)]'
                  : 'text-[var(--color-text-secondary)]',
              )}
            >
              <Icon className="h-5 w-5 shrink-0" />
              <span className="whitespace-nowrap">{label}</span>
            </button>
          );
        })}
      </div>

      {/* 折叠态图标行（窄条时显示，点击展开对应视图） */}
      <div className="flex w-full flex-col items-center gap-2 group-hover:hidden">
        <button
          type="button"
          onClick={onCreateThread}
          disabled={disabled}
          className="flex h-10 w-10 items-center justify-center rounded-md text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-primary-light)] disabled:cursor-not-allowed disabled:opacity-50"
          title="会话"
          aria-label="会话"
        >
          <ChatSvg className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={() => setActiveView('documents')}
          className={cn(
            'flex h-10 w-10 items-center justify-center rounded-md transition-colors',
            activeView === 'documents'
              ? 'bg-[var(--color-primary-light)] text-[var(--color-primary)]'
              : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-primary-light)]',
          )}
          title="政策法规"
          aria-label="政策法规"
        >
          <DocumentSvg className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={() => setActiveView('benchmark')}
          className={cn(
            'flex h-10 w-10 items-center justify-center rounded-md transition-colors',
            activeView === 'benchmark'
              ? 'bg-[var(--color-primary-light)] text-[var(--color-primary)]'
              : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-primary-light)]',
          )}
          title="行业基准"
          aria-label="行业基准"
        >
          <BenchmarkSvg className="h-5 w-5" />
        </button>
      </div>
    </nav>
  );
}
