import { cn } from '@/lib/utils';

interface SkeletonProps {
  className?: string;
  lineCount?: number;
}

export function Skeleton({ className, lineCount = 1 }: SkeletonProps) {
  if (lineCount > 1) {
    return (
      <div className={cn('flex flex-col gap-2', className)}>
        {Array.from({ length: lineCount }).map((_, i) => (
          <div
            key={i}
            className="h-4 animate-pulse rounded bg-[var(--color-border)]"
            style={{ width: i === lineCount - 1 ? '60%' : '100%' }}
          />
        ))}
      </div>
    );
  }
  return <div className={cn('h-4 w-3/4 animate-pulse rounded bg-[var(--color-border)]', className)} />;
}
