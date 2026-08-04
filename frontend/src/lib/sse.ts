import type { SSEEvent, TaxResult, SocialResult } from '@/lib/types';

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
