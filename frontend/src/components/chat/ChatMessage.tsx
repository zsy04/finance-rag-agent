import type { Message } from '@/lib/types';
import { ResultCard } from './ResultCard';
import { MarkdownRenderer } from './MarkdownRenderer';
import { WarningSvg, RetrySvg, DownloadSvg, AiSvg } from '@/components/icons';
import { cn } from '@/lib/utils';

interface ChatMessageProps {
  message: Message;
  onRetry?: () => void;
}

export function ChatMessage({ message, onRetry }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const hasContent = message.content.length > 0;
  const hasSources = message.sources && message.sources.length > 0;

  return (
    <div
      className={cn(
        'fade-in-up flex w-full',
        isUser ? 'justify-end' : 'justify-start',
      )}
    >
      {/* AI 头像 + 名称标签（2026-08-06：浅蓝底 + 小机器人图标 + 「已检索 N 份」） */}
      {!isUser && (
        <div className="mr-3 flex w-9 shrink-0 flex-col items-center">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
            <AiSvg className="h-5 w-5" />
          </div>
          <span className="mt-1 hidden text-center text-[10px] leading-tight text-[var(--color-text-tertiary)] lg:block">
            {hasSources
              ? `已检索 ${message.sources!.length} 份`
              : '财税助手'}
          </span>
        </div>
      )}

      <div
        className={cn(
          'px-4 py-3',
          isUser
            ? 'ml-auto max-w-[70%] rounded-[16px_16px_4px_16px] bg-[var(--color-primary)] text-white'
            : 'max-w-[85%] rounded-[16px_16px_16px_4px] bg-[var(--color-bg-page)] text-[var(--color-text-primary)]',
          message.isError && 'border-l-4 border-l-[var(--color-error)] rounded-[16px_16px_16px_4px]',
        )}
      >
        {/* 0. 历史摘要提示（SSE context 事件） */}
        {message.contextNotice && (
          <div className="mb-2 flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--color-primary-light)] px-2.5 py-1.5 text-xs text-[var(--color-primary)]">
            <span className="shrink-0">📦</span>
            <span>{message.contextNotice}</span>
          </div>
        )}

        {/* 1. 结果卡片 */}
        {message.resultCard && <ResultCard resultCard={message.resultCard} />}

        {/* 3. 正文 */}
        {hasContent && (
          <div className="break-words">
            {isUser ? (
              <div className="whitespace-pre-wrap text-sm leading-relaxed">
                {message.content}
              </div>
            ) : (
              <MarkdownRenderer content={message.content} />
            )}
            {/* 流式光标 */}
            {message.isStreaming && (
              <span className="cursor-blink ml-0.5 inline-block h-4 w-0.5 align-middle bg-[var(--color-primary)]" />
            )}
          </div>
        )}

        {/* 空内容 + 流式中 */}
        {!hasContent && message.isStreaming && (
          <div className="flex items-center gap-2 text-sm text-[var(--color-text-tertiary)]">
            <span className="cursor-blink inline-block h-4 w-0.5 bg-[var(--color-text-tertiary)]" />
            正在为您处理……
          </div>
        )}

        {/* 4. 来源引用 */}
        {hasSources && (
          <details className="mt-2 border-t border-[var(--color-border)]/50 pt-2">
            <summary className="cursor-pointer text-xs text-[var(--color-primary)] hover:underline">
              查看信息来源（{message.sources!.length}）
            </summary>
            <div className="mt-2 space-y-1">
              {message.sources!.map((src, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-[var(--color-text-secondary)]">📎</span>
                  <span className="text-[var(--color-text-primary)]">{src.title}</span>
                  {src.tier && (
                    <span className="rounded-full bg-[var(--color-primary-light)] px-2 py-0.5 text-[10px] text-[var(--color-primary)]">
                      {src.tier}
                    </span>
                  )}
                  {src.relation && (
                    <span className="text-[10px] text-[var(--color-text-tertiary)]">{src.relation}</span>
                  )}
                </div>
              ))}
            </div>
          </details>
        )}

        {/* 5. 免责声明 */}
        {message.disclaimer && (
          <div className="mt-2 flex items-start gap-1 border-t border-[var(--color-border)]/30 pt-2 text-xs text-[var(--color-text-tertiary)]">
            <WarningSvg className="mt-0.5 h-3 w-3 shrink-0" />
            <span>{message.disclaimer}</span>
          </div>
        )}

        {/* 6. 错误重试 */}
        {message.isError && onRetry && (
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={onRetry}
              className="flex items-center gap-1 rounded-[var(--radius-sm)] px-2 py-1 text-xs text-[var(--color-error)] transition-colors hover:bg-red-50"
            >
              <RetrySvg className="h-4 w-4" />
              重试
            </button>
          </div>
        )}

        {/* 7. 申报表下载 */}
        {message.resultCard?.type === 'form_result' && (
          <div className="mt-3 flex gap-2">
            <a
              href={`/api/form/download?path=${encodeURIComponent(
                (message.resultCard.data as { file_path: string }).file_path,
              )}`}
              className="flex items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--color-primary)] px-3 py-1.5 text-xs text-white transition-colors hover:bg-[var(--color-primary-dark)]"
            >
              <DownloadSvg className="h-4 w-4" />
              下载填好的表
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
