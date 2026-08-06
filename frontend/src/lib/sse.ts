import type {
  SSEEvent,
  TaxResult,
  SocialResult,
  Message,
  ThreadMeta,
  ProviderConfig,
  ProviderTemplate,
} from '@/lib/types';

/**
 * 使用 fetch + ReadableStream 消费 SSE 流
 * EventSource 不支持 POST 和自定义 headers，因此用本函数替代
 */
export async function* streamChat(
  message: string,
  threadId: string,
  provider?: ProviderConfig,
): AsyncGenerator<SSEEvent> {
  const body: Record<string, unknown> = { message, thread_id: threadId };
  // 模型切换器：用户配置了自定义 provider → 后端转发调用（缺省=默认 DeepSeek）
  if (provider) body.provider = provider;

  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    yield { type: 'error', data: { message: `请求失败: ${response.status}` } };
    return;
  }

  if (!response.body) {
    yield { type: 'error', data: { message: '响应体为空' } };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent: string | null = null;
  let dataLines: string[] = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        // 支持多行 data（SSE 规范：连续 data 行以 \n 拼接）
        dataLines.push(line.slice(6));
      } else if (line === '') {
        // 空行 = 事件结束，触发 yield
        if (currentEvent && dataLines.length > 0) {
          try {
            const data = JSON.parse(dataLines.join('\n'));
            yield { type: currentEvent as SSEEvent['type'], data };
          } catch {
            // 跳过无法解析的事件
          }
        }
        currentEvent = null;
        dataLines = [];
      }
    }
  }

  // 流结束时刷新可能残留的末尾事件
  if (currentEvent && dataLines.length > 0) {
    try {
      const data = JSON.parse(dataLines.join('\n'));
      yield { type: currentEvent as SSEEvent['type'], data };
    } catch {
      // 跳过无法解析的事件
    }
  }
}

/**
 * 会话列表 — GET /api/chat/threads（侧边栏多会话：新建/删除/切换）
 */
export async function getThreads(): Promise<ThreadMeta[]> {
  const res = await fetch('/api/chat/threads');
  if (!res.ok) throw new Error(`会话列表加载失败: ${res.status}`);
  const data = (await res.json()) as { threads: ThreadMeta[] };
  return data.threads;
}

/**
 * 历史回显 — GET /api/chat/history
 * 返回完整 Message JSON 列表（含 resultCard/sources/disclaimer/contextNotice），
 * 挂载时 fetch 后直接 setMessages 渲染。
 */
export async function getHistory(threadId: string): Promise<Message[]> {
  const res = await fetch(
    `/api/chat/history?thread_id=${encodeURIComponent(threadId)}`,
  );
  if (!res.ok) throw new Error(`历史加载失败: ${res.status}`);
  const data = (await res.json()) as { messages: Message[] };
  return data.messages;
}

/**
 * 清空指定会话（消息 + 画像 + 会话记录）— 「新会话」按钮（换人演示重置）
 */
export async function deleteHistory(threadId: string): Promise<void> {
  const res = await fetch(
    `/api/chat/history?thread_id=${encodeURIComponent(threadId)}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error(`清除会话失败: ${res.status}`);
}

/**
 * 模型供应商模板列表 — GET /api/models（设置页下拉数据源，不含 key）
 */
export async function getModels(): Promise<ProviderTemplate[]> {
  const res = await fetch('/api/models');
  if (!res.ok) throw new Error(`模型列表加载失败: ${res.status}`);
  const data = (await res.json()) as { templates: ProviderTemplate[] };
  return data.templates;
}

/**
 * 测试模型连接 — POST /api/models/test（设置页「测试」按钮）
 * 后端发一次最小请求验证 base_url + api_key + model 可用（浏览器直连会被 CORS 拦截）
 */
export async function testProvider(p: ProviderConfig): Promise<{
  ok: boolean;
  model?: string;
  reply?: string;
  error?: string;
}> {
  const res = await fetch('/api/models/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      base_url: p.base_url,
      api_key: p.api_key,
      model: p.model,
    }),
  });
  if (!res.ok) return { ok: false, error: `测试请求失败: ${res.status}` };
  return (await res.json()) as { ok: boolean; model?: string; reply?: string; error?: string };
}

/**
 * 快捷税率计算器 — POST /api/tax/calculate
 */
export async function calculateTax(payload: {
  annual_income: number;
  income_type: string;
  social_insurance?: number;
  housing_rent?: number;
  children_edu?: number;
  elderly_support?: number;
  continuing_education?: number;
  major_medical?: number;
  housing_loan?: number;
  childcare?: number;
  bonus?: number;
}): Promise<TaxResult> {
  const res = await fetch('/api/tax/calculate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`税率计算失败: ${res.status}`);
  return res.json();
}

/**
 * 快捷社保计算器 — POST /api/social/calculate
 */
export async function calculateSocial(payload: {
  salary: number;
  employment_type: string;
  housing_fund_ratio?: number;
  flexible_base_level?: string;
}): Promise<SocialResult> {
  const res = await fetch('/api/social/calculate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`社保计算失败: ${res.status}`);
  return res.json();
}
