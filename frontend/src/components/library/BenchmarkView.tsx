import { useEffect, useState, useCallback } from 'react';
import { Skeleton } from '@/components/shared/Skeleton';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { fetchBenchmark } from '@/lib/library';
import type { BenchmarkItem } from '@/lib/types';
import { cn } from '@/lib/utils';

/**
 * 行业指标基准（2026-08-06 联调）
 * 数据源：GET /api/library/benchmark?category=&keyword=
 * 10 项指标：比率类 ×100 显示 %；周转/流动类直接显示
 */
const INDICATORS: { key: string; label: string; kind: 'ratio' | 'times' }[] = [
  { key: 'vat_burden', label: '增值税税负率', kind: 'ratio' },
  { key: 'cit_burden', label: '企业所得税税负率', kind: 'ratio' },
  { key: 'gross_margin', label: '毛利率', kind: 'ratio' },
  { key: 'net_margin', label: '净利率', kind: 'ratio' },
  { key: 'ar_turnover', label: '应收账款周转率', kind: 'times' },
  { key: 'inventory_turnover', label: '存货周转率', kind: 'times' },
  { key: 'debt_ratio', label: '资产负债率', kind: 'ratio' },
  { key: 'current_ratio', label: '流动比率', kind: 'times' },
  { key: 'quick_ratio', label: '速动比率', kind: 'times' },
  { key: 'expense_ratio', label: '费用率', kind: 'ratio' },
];

/** 范围对象 → 显示文本（比率 ×100 加 %；周转/流动直接显示；null = 不适用） */
function fmt(v: { low: number | null; high: number | null } | undefined, kind: 'ratio' | 'times'): string {
  if (!v || (v.low === null && v.high === null)) return '—';
  const format = (n: number) => (kind === 'ratio' ? `${Math.round(n * 100)}%` : String(n));
  if (v.low === null) return `≤ ${format(v.high!)}`;
  if (v.high === null) return `≥ ${format(v.low)}`;
  return `${format(v.low)} ~ ${format(v.high)}`;
}

export function BenchmarkView() {
  const [category, setCategory] = useState('');
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState<BenchmarkItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (cat: string, kw: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBenchmark({ category: cat || undefined, keyword: kw || undefined });
      setItems(data.industries);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load('', ''); }, [load]);

  return (
    <div className="flex h-full flex-col gap-5 px-9 py-7">
      {/* 页头 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">行业指标基准</h2>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
          20 个行业门类 × 97 个细分行业的 10 项财务指标平均范围，判断企业指标是否正常（当前 {total} 条）
        </p>
      </div>

      {/* 搜索：门类精确 + 细分模糊 */}
      <div className="flex items-center gap-3">
        <input
          type="search"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') load(category, keyword); }}
          placeholder="行业门类，如：制造业（回车查询）"
          className="h-9 w-56 rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm outline-none focus:border-[var(--color-primary)]"
        />
        <input
          type="search"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') load(category, keyword); }}
          placeholder="细分行业，如：电子（回车查询）"
          className="h-9 w-56 rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm outline-none focus:border-[var(--color-primary)]"
        />
        <button
          type="button"
          onClick={() => load(category, keyword)}
          className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm text-white transition-opacity hover:opacity-90"
        >
          查询
        </button>
        {(category || keyword) && (
          <button
            type="button"
            onClick={() => { setCategory(''); setKeyword(''); load('', ''); }}
            className="text-xs text-[var(--color-text-secondary)] underline hover:text-[var(--color-primary)]"
          >
            清除筛选
          </button>
        )}
      </div>

      {/* 表格 */}
      <div className="flex-1 overflow-auto rounded-xl border border-[var(--color-border)] bg-white">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs text-white">
              <th className="sticky top-0 z-10 border-b border-[#001645] bg-[var(--color-primary)] px-4 py-3">行业门类</th>
              <th className="sticky top-0 z-10 border-b border-[#001645] bg-[var(--color-primary)] px-4 py-3">细分行业</th>
              {INDICATORS.map(({ key, label, kind }) => (
                <th key={key} className="sticky top-0 z-10 whitespace-nowrap border-b border-[#001645] bg-[var(--color-primary)] px-3 py-3" title={`${label}${kind === 'ratio' ? '（%）' : ''}`}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={INDICATORS.length + 2}>
                  <Skeleton className="m-3 h-40 w-full" />
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={INDICATORS.length + 2}>
                  <ErrorBanner message={error} />
                </td>
              </tr>
            )}
            {!loading && !error && items.length === 0 && (
              <tr>
                <td colSpan={INDICATORS.length + 2} className="py-10 text-center text-sm text-[var(--color-text-tertiary)]">
                  未找到匹配的行业
                </td>
              </tr>
            )}
            {!loading &&
              !error &&
              items.map((i, idx) => (
                <tr key={`${i.category}-${i.sub_industry}`} className={cn(idx % 2 && 'bg-[var(--color-bg-page)]/50')}>
                  <td className="border-b border-[var(--color-border)] px-4 py-3 whitespace-nowrap text-[var(--color-text-secondary)]">{i.category}</td>
                  <td className="border-b border-[var(--color-border)] px-4 py-3 font-medium whitespace-nowrap text-[var(--color-text-primary)]">{i.sub_industry}</td>
                  {INDICATORS.map(({ key, kind }) => (
                    <td key={key} className="border-b border-[var(--color-border)] px-3 py-3 whitespace-nowrap text-[var(--color-text-secondary)]">
                      {fmt(i.indicators?.[key], kind)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
