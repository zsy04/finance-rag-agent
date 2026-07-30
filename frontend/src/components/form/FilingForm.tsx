import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/shared/Skeleton';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { SaveSvg, GenerateSvg, DownloadSvg, BlankDocSvg } from '@/components/icons';
import { useApp } from '@/context/AppContext';

const FORM_TYPES = [
  { value: 'A', label: '个人所得税年度自行纳税申报表（A表）' },
  { value: 'B', label: '个人所得税年度自行纳税申报表（B表）' },
];

interface FormState {
  formType: string;
  name: string;
  idNumber: string;
  employer: string;
  annualIncome: string;
  prepaidTax: string;
}

export function FilingForm() {
  const { userContext } = useApp();
  const [form, setForm] = useState<FormState>({
    formType: 'A',
    name: '',
    idNumber: '',
    employer: '',
    annualIncome: userContext.salary ? String(userContext.salary * 12) : '',
    prepaidTax: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    form_type: string;
    file_path: string;
    filled_fields: number;
    skipped_fields: string[];
    preview?: string;
  } | null>(null);

  const updateField = (key: keyof FormState, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveDraft = () => {
    localStorage.setItem('filing_form_draft', JSON.stringify(form));
  };

  const handleGenerate = async () => {
    if (!form.name || !form.idNumber) {
      setError('请填写姓名和身份证号');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      // 申报表生成已融入 Agent 通路（fill_tax_form @tool）
      // 前端通过 /api/chat 发送生成请求，Agent 调用 fill_tax_form 工具
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: `帮我生成个税申报表${form.formType}表，姓名${form.name}，身份证号${form.idNumber}，任职单位${form.employer}，年收入${form.annualIncome}元，已预缴税额${form.prepaidTax}元`,
          thread_id: crypto.randomUUID(),
        }),
      });

      if (!response.ok) throw new Error(`生成失败: ${response.status}`);

      // 解析 SSE 流，提取 result 事件中的 form_result
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent: string | null = null;
      let formResult: typeof result = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ') && currentEvent === 'result') {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'form_result') {
                formResult = data.data as typeof result;
              }
            } catch { /* skip */ }
            currentEvent = null;
          }
        }
      }

      if (formResult) {
        setResult(formResult);
      } else {
        setError('未能生成申报表，请检查信息后重试');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-6 py-8">
      {/* 标题 */}
      <div className="flex items-center gap-2">
        <GenerateSvg className="h-6 w-6 text-[var(--color-primary)]" />
        <h1 className="text-xl font-bold text-[var(--color-text-primary)]">申报材料生成</h1>
      </div>

      {/* 基本信息 */}
      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
        <h3 className="text-base font-semibold text-[var(--color-text-primary)]">基本信息</h3>

        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">申报表类型</label>
          <Select
            value={form.formType}
            onChange={(e) => updateField('formType', e.target.value)}
          >
            {FORM_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">姓名</label>
            <Input
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder="请输入姓名"
              aria-label="姓名"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">身份证号</label>
            <Input
              value={form.idNumber}
              onChange={(e) => updateField('idNumber', e.target.value)}
              placeholder="请输入身份证号"
              aria-label="身份证号"
            />
          </div>
        </div>
      </div>

      {/* 收入信息 */}
      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
        <h3 className="text-base font-semibold text-[var(--color-text-primary)]">收入信息</h3>

        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">任职单位</label>
          <Input
            value={form.employer}
            onChange={(e) => updateField('employer', e.target.value)}
            placeholder="请输入任职单位名称"
            aria-label="任职单位"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">年收入（元）</label>
            <Input
              type="number"
              value={form.annualIncome}
              onChange={(e) => updateField('annualIncome', e.target.value)}
              placeholder="如 96000"
              aria-label="年收入"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">已预缴税额（元）</label>
            <Input
              type="number"
              value={form.prepaidTax}
              onChange={(e) => updateField('prepaidTax', e.target.value)}
              placeholder="如 2000"
              aria-label="已预缴税额"
            />
          </div>
        </div>
      </div>

      {/* 按钮 */}
      <div className="flex justify-end gap-3">
        <Button variant="secondary" onClick={handleSaveDraft}>
          <SaveSvg className="h-4 w-4" />
          保存草稿
        </Button>
        <Button onClick={handleGenerate} disabled={loading}>
          <GenerateSvg className="h-4 w-4" />
          {loading ? '生成中……' : '生成申报表'}
        </Button>
      </div>

      {/* 结果区 */}
      {loading && (
        <div className="space-y-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-white p-4">
          <Skeleton lineCount={4} />
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={handleGenerate} />}

      {result && (
        <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] border-l-4 border-l-[var(--color-primary)] bg-white p-6 shadow-[var(--shadow-sm)]">
          <h3 className="text-lg font-semibold text-[var(--color-primary)]">
            申报表生成完成
          </h3>

          <div className="space-y-1 text-sm">
            <div>
              <span className="text-[var(--color-text-secondary)]">申报表类型：</span>
              <span className="font-medium">{result.form_type}</span>
            </div>
            <div>
              <span className="text-[var(--color-text-secondary)]">已填写字段：</span>
              <span className="font-mono font-bold text-[var(--color-primary)]">{result.filled_fields}</span> 个
            </div>
            {result.skipped_fields.length > 0 && (
              <div className="text-xs text-[var(--color-text-tertiary)]">
                跳过字段：{result.skipped_fields.join('、')}
              </div>
            )}
          </div>

          {/* 下载按钮 */}
          <div className="flex gap-3">
            <a
              href={`/api/form/download?path=${encodeURIComponent(result.file_path)}`}
              className="inline-flex h-10 items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-primary)] px-4 text-sm font-medium text-white transition-all hover:bg-[var(--color-primary-dark)]"
            >
              <DownloadSvg className="h-4 w-4" />
              下载填好的表
            </a>
            <a
              href={`/api/form/download?path=blank_${result.form_type}`}
              className="inline-flex h-10 items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-primary)] bg-white px-4 text-sm font-medium text-[var(--color-primary)] transition-all hover:bg-[var(--color-primary-light)]"
            >
              <BlankDocSvg className="h-4 w-4" />
              下载空白原表
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
