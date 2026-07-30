import { WarningSvg, RetrySvg } from '@/components/icons';

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div
      className="flex items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-warning)]/30 bg-amber-50 px-4 py-3"
      role="alert"
    >
      <WarningSvg className="h-5 w-5 shrink-0 text-[var(--color-warning)]" />
      <span className="flex-1 text-sm text-[var(--color-text-primary)]">{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-1 rounded-[var(--radius-sm)] px-2 py-1 text-xs text-[var(--color-primary)] transition-colors hover:bg-[var(--color-primary-light)]"
        >
          <RetrySvg className="h-4 w-4" />
          重试
        </button>
      )}
    </div>
  );
}
