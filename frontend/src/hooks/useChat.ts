import { useState, useCallback, useRef } from 'react';
import type { Message, SSEEvent, Source, ResultCardData } from '@/lib/types';
import { streamChat } from '@/lib/sse';

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const threadIdRef = useRef<string>(crypto.randomUUID());

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isLoading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
    };
    const aiMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      isStreaming: true,
    };
    setMessages((prev) => [...prev, userMsg, aiMsg]);
    setIsLoading(true);

    try {
      for await (const event of streamChat(content, threadIdRef.current) as AsyncGenerator<SSEEvent>) {
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== aiMsg.id) return m;
            switch (event.type) {
              case 'step':
                return {
                  ...m,
                  content: m.content + (event.data.content as string),
                };
              case 'result':
                return {
                  ...m,
                  resultCard: event.data as unknown as ResultCardData,
                };
              case 'source':
                return {
                  ...m,
                  sources: [...(m.sources || []), event.data as unknown as Source],
                };
              case 'disclaimer':
                return {
                  ...m,
                  disclaimer: event.data.text as string,
                };
              case 'thinking':
                return m;
              case 'error':
                // 非致命错误（内容已有文本时不覆盖，让 Agent 继续回答）
                if (m.content.length > 0) {
                  return { ...m, isStreaming: false };
                }
                return {
                  ...m,
                  content: (event.data.message as string) || (event.data.content as string) || '处理失败，请重试',
                  isError: true,
                  isStreaming: false,
                };
              case 'done':
                return { ...m, isStreaming: false };
              default:
                return m;
            }
          }),
        );
      }
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsg.id
            ? { ...m, content: '网络请求失败，请重试', isError: true, isStreaming: false }
            : m,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  }, [isLoading]);

  const clearMessages = useCallback(() => {
    threadIdRef.current = crypto.randomUUID();
    setMessages([]);
  }, []);

  return { messages, isLoading, sendMessage, clearMessages };
}
