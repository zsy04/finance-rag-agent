import { useRef, useEffect } from 'react';
import type { Message } from '@/lib/types';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { WelcomeScreen } from './WelcomeScreen';

interface ChatViewProps {
  messages: Message[];
  isLoading: boolean;
  onSend: (message: string) => void;
  lastUserMessage: string | null;
}

export function ChatView({ messages, isLoading, onSend, lastUserMessage }: ChatViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const initialRef = useRef<string | undefined>(undefined);

  // 新消息自动滚动到底部
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, [messages]);

  // 如果有外部传入的初始消息（示例问题点击），触发发送
  useEffect(() => {
    if (lastUserMessage && lastUserMessage !== initialRef.current) {
      initialRef.current = lastUserMessage;
      onSend(lastUserMessage);
    }
  }, [lastUserMessage, onSend]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      {/* 消息列表 */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-4 overflow-y-auto px-6 py-4"
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
        <div className="px-6 pb-1 text-center text-xs text-[var(--color-text-tertiary)]">
          正在为您计算……
        </div>
      )}

      {/* 底部输入 */}
      <ChatInput onSend={onSend} isLoading={isLoading} />
    </div>
  );
}
