import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import { SendSvg } from '@/components/icons';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
  onStop: () => void;
}

export function ChatInput({ onSend, isLoading, onStop }: ChatInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 自动撑高
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 96)}px`;
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
    /* 设计稿输入区：白底 + 1.5px 边框 + 圆角 12px，内嵌 textarea + 渐变发送按钮 */
    <div className="mt-4 flex items-center gap-3 rounded-xl border-[1.5px] border-[#99A3B8] bg-white py-1.5 pl-4 pr-1.5">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isLoading}
        placeholder="输入你的财税问题，例如：个税专项附加扣除有哪些…"
        rows={1}
        className={cn(
          'flex-1 resize-none border-none bg-transparent py-2 text-[13px] leading-normal text-[var(--color-text-primary)] outline-none',
          'placeholder:text-[var(--color-text-tertiary)]',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
        aria-label="消息输入框"
        style={{ maxHeight: '96px' }}
      />
      <button
        onClick={isLoading ? onStop : handleSend}
        disabled={!isLoading && !value.trim()}
        className={cn(
          'flex h-9 w-[88px] shrink-0 items-center justify-center rounded-lg text-[13px] font-medium text-white transition-opacity',
          'bg-gradient-to-r from-[#014DB2] to-[#002A6B]',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]',
          !isLoading && !value.trim()
            ? 'cursor-not-allowed opacity-50'
            : 'hover:opacity-90',
        )}
        aria-label={isLoading ? '停止生成' : '发送消息'}
      >
        {isLoading ? (
          <>
            {/* 停止图标（方块），2026-08-13：生成中可随时中止 */}
            <svg className="mr-1 h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <rect x="6" y="6" width="12" height="12" rx="1.5" />
            </svg>
            停止
          </>
        ) : (
          <>
            <SendSvg className="mr-1 h-4 w-4" />
            发送
          </>
        )}
      </button>
    </div>
  );
}
