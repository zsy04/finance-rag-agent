import { useRef, useEffect } from 'react';
import type { Message } from '@/lib/types';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { WelcomeScreen } from './WelcomeScreen';

interface ChatViewProps {
  messages: Message[];
  isLoading: boolean;
  onSend: (message: string) => void;
  onStop: () => void;
}

export function ChatView({ messages, isLoading, onSend, onStop }: ChatViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // 新消息自动滚动到底部
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, [messages]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col px-9 py-7">
      {/* 页头：面包屑 + 标题 + 状态徽标（新建会话/历史记录已集成到左侧会话栏） */}
      <div className="mb-5">
        <p className="text-xs text-[var(--color-text-tertiary)]">工作台 / 智能问答</p>
        <div className="mt-1 flex items-center gap-3">
          <h2 className="text-[26px] font-bold leading-tight text-[var(--color-text-primary)]">
            智能问答
          </h2>
          <span className="flex items-center gap-1.5 rounded-full bg-[#E8F7F1] px-3 py-1 text-xs font-medium text-[#059669]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#10B981]" />
            RAG 检索已就绪
          </span>
        </div>
      </div>

      {/* 问答卡片（设计稿：白底 16px 圆角 + 轻阴影 + 24px 内边距） */}
      <div className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[var(--color-border)] bg-white p-6 shadow-[0_4px_20px_rgba(2,8,23,0.04)]">
        {/* 消息列表 */}
        <div
          ref={scrollRef}
          className="flex-1 space-y-5 overflow-y-auto"
          role="log"
          aria-live="polite"
          aria-label="对话消息列表"
        >
          {isEmpty ? (
            <WelcomeScreen onSuggestionClick={onSend} />
          ) : (
            messages.map((msg, idx) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onRetry={
                  msg.role === 'assistant' && msg.isError
                    ? () => {
                        // 重试：找到对应的用户消息
                        const prevUserMsg = messages
                          .slice(0, idx)
                          .reverse()
                          .find((m) => m.role === 'user');
                        if (prevUserMsg) onSend(prevUserMsg.content);
                      }
                    : undefined
                }
              />
            ))
          )}
        </div>

        {/* 加载提示 */}
        {isLoading && messages.length > 0 && (
          <div className="py-1 text-center text-xs text-[var(--color-text-tertiary)]">
            正在为您计算……
          </div>
        )}

        {/* 底部输入 */}
        <ChatInput onSend={onSend} isLoading={isLoading} onStop={onStop} />
      </div>
    </div>
  );
}
