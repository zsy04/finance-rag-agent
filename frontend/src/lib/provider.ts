import type { ProviderConfig, SavedProvider } from '@/lib/types';

/**
 * 模型供应商配置的 localStorage 管理（模型切换器 2026-08-06）
 *
 * 设计（《财务RAG-模型切换器需求记录.md》§2）：
 *  - 用户在前端设置页填写 API Key / base_url / model
 *  - 存 localStorage（lest_providers = 配置数组 / lest_active_provider = 当前 id）
 *  - 发消息时把当前 provider 转为 ProviderConfig 随请求携带（后端转发）
 *  - API Key 仅存本机浏览器 + 随请求传给本地后端，不进代码、不进 git
 */
const PROVIDERS_KEY = 'lest_providers';
const ACTIVE_KEY = 'lest_active_provider';

/** 默认上下文窗口（未指定时用 DeepSeek 口径） */
export const DEFAULT_CONTEXT_WINDOW = 64_000;

export function loadProviders(): SavedProvider[] {
  try {
    const raw = localStorage.getItem(PROVIDERS_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw) as SavedProvider[];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function saveProviders(list: SavedProvider[]): void {
  try {
    localStorage.setItem(PROVIDERS_KEY, JSON.stringify(list));
  } catch {
    // 隐私模式等写入失败 → 本次会话内仍可用（内存态由调用方维护）
  }
}

export function loadActiveProviderId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

export function saveActiveProviderId(id: string | null): void {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id);
    else localStorage.removeItem(ACTIVE_KEY);
  } catch {
    // 忽略写入失败
  }
}

/** 当前生效的 provider（active 配置 → 请求体 ProviderConfig）；无自定义 → null（走默认 DeepSeek） */
export function getActiveProviderConfig(): ProviderConfig | null {
  const providers = loadProviders();
  const activeId = loadActiveProviderId();
  if (!activeId) return null;
  const p = providers.find((x) => x.id === activeId);
  if (!p || !p.model.trim()) return null;
  return {
    base_url: p.base_url || undefined,
    api_key: p.api_key || undefined,
    model: p.model.trim(),
    context_window: p.context_window || DEFAULT_CONTEXT_WINDOW,
  };
}
