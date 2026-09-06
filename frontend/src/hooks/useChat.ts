import { useState, useCallback, useRef, useEffect } from 'react';
import type { Message, Source, ResultCardData, ThreadMeta } from '@/lib/types';
import { streamChat, getHistory, deleteHistory, getThreads } from '@/lib/sse';
import { getActiveProviderConfig } from '@/lib/provider';

// 多会话模型：浏览器内可新建/删除/切换多个会话（持久化 §5.1 升级）
// localStorage 只存"当前会话"thread_id；会话列表由后端 GET /api/chat/threads 提供。
// 登录体系落地后扩展为 user_id + 会话归属（thread_id 存服务端）。
const THREAD_STORAGE_KEY = 'lest_thread_id';

function loadThreadId(): string {
  try {
    const saved = localStorage.getItem(THREAD_STORAGE_KEY);
    if (saved) return saved;
  } catch {
    // localStorage 不可用（隐私模式等）→ 退化为内存随机 ID（不持久化）
  }
  const tid = crypto.randomUUID();
  try {
    localStorage.setItem(THREAD_STORAGE_KEY, tid);
  } catch {
    // 忽略写入失败，本次会话仍可用
  }
  return tid;
}

function saveThreadId(tid: string) {
  try {
    localStorage.setItem(THREAD_STORAGE_KEY, tid);
  } catch {
    // 忽略写入失败
  }
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isHydrating, setIsHydrating] = useState(true); // 历史回显加载中（防 WelcomeScreen 闪烁）
  const [threads, setThreads] = useState<ThreadMeta[]>([]);
  const [threadId, setThreadId] = useState<string>(loadThreadId);

  // 同步 ref：sendMessage / deleteThread 闭包内读取最新 thread_id（避免重复重建回调）
  const currentThreadRef = useRef(threadId);
  currentThreadRef.current = threadId;

  // 当前请求的 AbortController（「停止生成」/ 主动取消，2026-08-13）
  const abortRef = useRef<AbortController | null>(null);

  const stopGeneration = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // 挂载：拉会话列表 + 当前会话历史（本地 SQLite，毫秒级；失败不影响新会话）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const tid = currentThreadRef.current;
      try {
        const list = await getThreads();
        if (cancelled) return;

        // 校验当前 thread_id 是否仍存在（可能已被删除/后端重置）
        // 若不存在：有剩余会话则切到最新的，否则新建空会话 —— 避免用已删 tid 发消息导致"会话复活"
        const exists = list.some((t) => t.thread_id === tid);
        if (!exists && list.length > 0) {
          const fallback = list[0].thread_id;
          setThreadId(fallback);
          saveThreadId(fallback);
          const history = await getHistory(fallback);
          if (cancelled) return;
          setThreads(list);
          setMessages(history);
          return;
        }
        if (!exists && list.length === 0) {
          const fresh = crypto.randomUUID();
          setThreadId(fresh);
          saveThreadId(fresh);
          if (cancelled) return;
          setThreads([]);
          setMessages([]);
          return;
        }

        const history = await getHistory(tid);
        if (cancelled) return;
        setThreads(list);
        setMessages(history);
      } catch {
        // 任一失败：保持空会话，用户仍可正常提问
      } finally {
        if (!cancelled) setIsHydrating(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 切换会话：加载该会话历史
  const selectThread = useCallback(async (tid: string) => {
    setThreadId(tid);
    saveThreadId(tid);
    setIsHydrating(true);
    try {
      const history = await getHistory(tid);
      setMessages(history);
    } catch {
      setMessages([]);
    } finally {
      setIsHydrating(false);
    }
  }, []);

  // 新建会话：换新 thread_id + 空消息 + 列表置顶占位
  const createThread = useCallback(async () => {
    if (isLoading) return;
    const tid = crypto.randomUUID();
    setThreadId(tid);
    saveThreadId(tid);
    setMessages([]);
    setIsHydrating(false);
    setThreads((prev) => [
      {
        thread_id: tid,
        title: '',
        message_count: 0,
        updated_at: new Date().toISOString(),
      },
      ...prev,
    ]);
  }, [isLoading]);

  // 删除会话：清后端数据 + 移除列表；若删的是当前会话则切换到其余会话（全删则新建空会话）
  const deleteThread = useCallback(
    async (tid: string) => {
      if (isLoading) return;
      try {
        await deleteHistory(tid);
      } catch {
        // 后端不可用时本地仍可移除
      }
      setThreads((prev) => prev.filter((t) => t.thread_id !== tid));
      if (tid === currentThreadRef.current) {
        const remaining = threads.filter((t) => t.thread_id !== tid);
        if (remaining.length > 0) {
          await selectThread(remaining[0].thread_id);
        } else {
          const newTid = crypto.randomUUID();
          setThreadId(newTid);
          saveThreadId(newTid);
          setMessages([]);
          setIsHydrating(false);
          setThreads([{
            thread_id: newTid,
            title: '',
            message_count: 0,
            updated_at: new Date().toISOString(),
          }]);
        }
      }
    },
    [isLoading, threads, selectThread],
  );

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || isLoading) return;
      const tid = currentThreadRef.current;

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

      const controller = new AbortController();
      abortRef.current = controller;
      let receivedDone = false;

      try {
        // 模型切换器：当前生效的自定义 provider（null = 默认 DeepSeek，请求不携带）
        const provider = getActiveProviderConfig();
        for await (const event of streamChat(content, tid, provider ?? undefined, controller.signal)) {
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== aiMsg.id) return m;
              switch (event.type) {
                case 'step':
                  return {
                    ...m,
                    content: m.content + ((event.data.content as string) ?? ''),
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
                case 'context':
                  return {
                    ...m,
                    contextNotice: event.data.message as string,
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
                    content:
                      (event.data.message as string) ||
                      (event.data.content as string) ||
                      '处理失败，请重试',
                    isError: true,
                    isStreaming: false,
                  };
                case 'done':
                  receivedDone = true;
                  return { ...m, isStreaming: false };
                default:
                  return m;
              }
            }),
          );
        }

        // 流正常结束但未收到 done 事件 → 连接被中断（代理超时/后端挂起后关闭）
        // 2026-08-13：此前这种情况 isStreaming 永远为 true，用户看到"卡死"无提示
        if (!receivedDone) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === aiMsg.id
                ? {
                    ...m,
                    isStreaming: false,
                    isError: m.content.length === 0,
                    content: m.content.length === 0 ? '回复被中断，请重试' : m.content,
                  }
                : m,
            ),
          );
        }
      } catch {
        // abort = 用户主动点击「停止生成」，不算错误
        const aborted = controller.signal.aborted;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiMsg.id
              ? aborted
                ? { ...m, isStreaming: false }
                : { ...m, content: '网络请求失败，请重试', isError: true, isStreaming: false }
              : m,
          ),
        );
      } finally {
        abortRef.current = null;
        setIsLoading(false);
        // 回复完成后刷新会话列表（标题/更新时间变化）
        try {
          const list = await getThreads();
          setThreads(list);
        } catch {
          // 列表刷新失败不影响对话
        }
      }
    },
    [isLoading],
  );

  return {
    messages,
    isLoading,
    isHydrating,
    threadId,
    threads,
    sendMessage,
    stopGeneration,
    selectThread,
    createThread,
    deleteThread,
  };
}
