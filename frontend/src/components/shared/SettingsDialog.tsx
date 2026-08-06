import { useEffect, useState, type FormEvent } from 'react';
import { useApp } from '@/context/AppContext';
import type { ProviderTemplate, SavedProvider } from '@/lib/types';
import { getModels, testProvider } from '@/lib/sse';
import {
  loadProviders,
  saveProviders,
  DEFAULT_CONTEXT_WINDOW,
} from '@/lib/provider';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { cn } from '@/lib/utils';

/**
 * 模型供应商设置弹窗（模型切换器 2026-08-06）
 * - 供应商模板下拉（GET /api/models，选中自动填充 base_url/默认模型）
 * - BYOK：自定义 base_url + api_key + model（接任意 OpenAI 兼容端点）
 * - 多套配置管理：保存 / 设为当前 / 删除
 * - 测试连接：POST /api/models/test（浏览器直连会被 CORS 拦，必须走后端）
 * - 存储：localStorage（lest_providers / lest_active_provider）
 */
interface Props {
  open: boolean;
  onClose: () => void;
}

function newId(): string {
  return crypto.randomUUID();
}

export function SettingsDialog({ open, onClose }: Props) {
  const { activeProviderId, setActiveProviderId } = useApp();
  const [providers, setProviders] = useState<SavedProvider[]>(() => loadProviders());
  const [templates, setTemplates] = useState<ProviderTemplate[]>([]);

  // 编辑态表单
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [contextWindow, setContextWindow] = useState(DEFAULT_CONTEXT_WINDOW);
  const [editId, setEditId] = useState<string | null>(null); // null = 新建

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

  // 打开时拉模板 + 重置表单
  useEffect(() => {
    if (!open) return;
    setProviders(loadProviders());
    getModels()
      .then(setTemplates)
      .catch(() => setTemplates([]));
    resetForm();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function resetForm() {
    setName('');
    setBaseUrl('');
    setApiKey('');
    setModel('');
    setContextWindow(DEFAULT_CONTEXT_WINDOW);
    setEditId(null);
    setTestResult(null);
  }

  function applyTemplate(templateId: string) {
    const t = templates.find((x) => x.id === templateId);
    if (!t) return;
    setBaseUrl(t.base_url);
    setModel(t.default_model);
    setContextWindow(t.context_window);
  }

  function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!model.trim()) return;
    const entry: SavedProvider = {
      id: editId ?? newId(),
      name: name.trim() || model.trim(),
      base_url: baseUrl.trim(),
      api_key: apiKey.trim(),
      model: model.trim(),
      context_window: contextWindow || DEFAULT_CONTEXT_WINDOW,
    };
    const next = editId
      ? providers.map((p) => (p.id === editId ? entry : p))
      : [...providers, entry];
    setProviders(next);
    saveProviders(next);
    resetForm();
  }

  function handleActivate(id: string) {
    setActiveProviderId(id);
  }

  function handleDelete(id: string) {
    const next = providers.filter((p) => p.id !== id);
    setProviders(next);
    saveProviders(next);
    if (activeProviderId === id) setActiveProviderId(null); // 删除当前 → 回默认 DeepSeek
  }

  async function handleTest() {
    if (!baseUrl.trim() || !apiKey.trim() || !model.trim()) {
      setTestResult({ ok: false, msg: '请先填写 base_url / API Key / 模型名' });
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const r = await testProvider({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model: model.trim(),
      });
      setTestResult(
        r.ok
          ? { ok: true, msg: `连接成功：${r.reply || '模型可正常调用'}` }
          : { ok: false, msg: r.error || '连接失败' },
      );
    } catch {
      setTestResult({ ok: false, msg: '网络异常，无法测试' });
    } finally {
      setTesting(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="模型设置"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
            模型设置
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="rounded-md p-1 text-[var(--color-text-secondary)] hover:bg-[var(--color-primary-light)] hover:text-[var(--color-primary)]"
          >
            ✕
          </button>
        </div>

        {/* ── 已保存配置列表 ── */}
        {providers.length > 0 && (
          <div className="mb-4 space-y-2">
            {providers.map((p) => (
              <div
                key={p.id}
                className={cn(
                  'flex items-center justify-between rounded-lg border px-3 py-2 text-sm',
                  activeProviderId === p.id
                    ? 'border-[var(--color-primary)] bg-[var(--color-primary-light)]'
                    : 'border-[var(--color-border)]',
                )}
              >
                <div className="min-w-0">
                  <div className="truncate font-medium text-[var(--color-text-primary)]">
                    {p.name}
                    {activeProviderId === p.id && (
                      <span className="ml-2 text-xs text-[var(--color-primary)]">使用中</span>
                    )}
                  </div>
                  <div className="truncate text-xs text-[var(--color-text-secondary)]">
                    {p.model} · {p.base_url || '默认端点'}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    className="rounded px-2 py-1 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-primary)]"
                    onClick={() => handleActivate(p.id)}
                  >
                    使用
                  </button>
                  <button
                    type="button"
                    className="rounded px-2 py-1 text-xs text-[var(--color-text-secondary)] hover:text-red-600"
                    onClick={() => handleDelete(p.id)}
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── 编辑表单 ── */}
        <form onSubmit={handleSave} className="space-y-3">
          <label className="block text-sm text-[var(--color-text-secondary)]">
            供应商模板
            <Select
              className="mt-1"
              defaultValue=""
              onChange={(e) => applyTemplate(e.target.value)}
            >
              <option value="">选择模板（自动填充）</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </Select>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm text-[var(--color-text-secondary)]">
              名称
              <Input
                className="mt-1"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="如：我的千问"
              />
            </label>
            <label className="block text-sm text-[var(--color-text-secondary)]">
              模型名 *
              <Input
                className="mt-1"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="deepseek-v4-flash"
                required
              />
            </label>
          </div>

          <label className="block text-sm text-[var(--color-text-secondary)]">
            API 端点（OpenAI 兼容 base_url）
            <Input
              className="mt-1"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.deepseek.com/v1"
            />
          </label>

          <label className="block text-sm text-[var(--color-text-secondary)]">
            API Key
            <Input
              className="mt-1"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
            />
          </label>

          <label className="block text-sm text-[var(--color-text-secondary)]">
            上下文窗口（tokens，影响摘要触发阈值）
            <Input
              className="mt-1"
              type="number"
              min={8000}
              step={1000}
              value={contextWindow}
              onChange={(e) => setContextWindow(Number(e.target.value) || DEFAULT_CONTEXT_WINDOW)}
            />
          </label>

          {testResult && (
            <p
              className={cn(
                'text-sm',
                testResult.ok ? 'text-green-600' : 'text-red-600',
              )}
            >
              {testResult.msg}
            </p>
          )}

          <div className="flex items-center justify-between pt-1">
            <Button
              type="button"
              variant="secondary"
              disabled={testing}
              onClick={handleTest}
            >
              {testing ? '测试中…' : '测试连接'}
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={resetForm}>
                清空
              </Button>
              <Button type="submit">{editId ? '保存修改' : '保存配置'}</Button>
            </div>
          </div>
        </form>

        <p className="mt-3 text-xs text-[var(--color-text-secondary)]">
          API Key 仅保存在本机浏览器并随请求传给本地后端调用，不会上传至 GitHub。
          切换模型后，若计算类问题返回异常，请切回默认 DeepSeek。
        </p>
      </div>
    </div>
  );
}
