import type { SSEEvent } from '@/lib/types';

/**
 * 使用 fetch + ReadableStream 消费 SSE 流
 * EventSource 不支持 POST 和自定义 headers，因此用本函数替代
 */
export async function* streamChat(
  message: string,
  threadId: string,
): AsyncGenerator<SSEEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId }),
  });

  if (!response.ok) {
    yield { type: 'error', data: { message: `请求失败: ${response.status}` } };
    return;
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEvent) {
        try {
          const data = JSON.parse(line.slice(6));
          yield { type: currentEvent as SSEEvent['type'], data };
        } catch {
          // 跳过无法解析的行
        }
        currentEvent = null;
      }
    }
  }
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
  bonus?: number;
}): Promise<Record<string, unknown>> {
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
}): Promise<Record<string, unknown>> {
  const res = await fetch('/api/social/calculate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`社保计算失败: ${res.status}`);
  return res.json();
}
