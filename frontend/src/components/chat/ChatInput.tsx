import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import { SendSvg, LoadingSvg } from '@/components/icons';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
}

export function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 自动撑高
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [value]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="sticky bottom-0 flex items-end gap-3 border-t border-[var(--color-border)] bg-[var(--color-bg-surface)] px-6 py-4">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isLoading}
        placeholder="输入你的问题……（Enter 发送，Shift+Enter 换行）"
        rows={1}
        className={cn(
          'flex-1 resize-none rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-page)] px-4 py-3 text-base transition-all duration-[var(--transition-fast)]',
          'placeholder:text-[var(--color-text-tertiary)]',
          'focus:border-[var(--color-primary)] focus:ring-[3px] focus:ring-[var(--color-primary-light)] focus:outline-none',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
        aria-label="消息输入框"
        style={{ maxHeight: '120px' }}
      />
      <button
        onClick={handleSend}
        disabled={isLoading || !value.trim()}
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] transition-all duration-[var(--transition-fast)]',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]',
          isLoading || !value.trim()
            ? 'cursor-not-allowed bg-[var(--color-border)]'
            : 'bg-[var(--color-primary)] hover:bg-[var(--color-primary-dark)] hover:-translate-y-px',
        )}
        aria-label={isLoading ? '正在发送' : '发送消息'}
      >
        {isLoading ? (
          <LoadingSvg className="icon-spinning h-5 w-5 text-white" />
        ) : (
          <SendSvg className="h-5 w-5 text-white" />
        )}
      </button>
    </div>
  );
}
