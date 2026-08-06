import { useEffect, useState, useCallback } from 'react';
import { Skeleton } from '@/components/shared/Skeleton';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { fetchDocuments, fetchDocumentDetail } from '@/lib/library';
import type { LibraryDocMeta, LibraryDocDetail } from '@/lib/types';
import { cn } from '@/lib/utils';

/**
 * 政策法规（2026-08-06 联调）
 * 数据源：GET /api/library/documents（列表）+ GET /api/library/documents/{id}（正文，HTML）
 */
const CATEGORIES = ['法律', '行政法规', '部门规章', '规范性文件'] as const;

export function DocumentsView() {
  // 列表态
  const [category, setCategory] = useState<string>('');
  const [keyword, setKeyword] = useState('');
  const [docs, setDocs] = useState<LibraryDocMeta[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  // 详情态
  const [detail, setDetail] = useState<LibraryDocDetail | null>(null);

  const load = useCallback(async (cat: string, kw: string, p: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDocuments({
        category: cat || undefined,
        keyword: kw || undefined,
        limit: PAGE_SIZE,
        offset: (p - 1) * PAGE_SIZE,
      });
      setDocs(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // 首次加载
  useEffect(() => { load('', '', 1); }, [load]);

  // 打开正文
  const openDetail = async (id: string) => {
    setError(null);
    try {
      const d = await fetchDocumentDetail(id);
      setDetail(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : '未找到该法规');
    }
  };

  // ── 详情视图 ──
  if (detail) {
    return (
      <div className="flex h-full flex-col px-9 py-7">
        <button
          type="button"
          onClick={() => { setDetail(null); setError(null); }}
          className="mb-4 flex w-fit items-center gap-1 text-sm text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-primary)]"
        >
          ← 返回列表
        </button>
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">{detail.title}</h2>
          <span className="rounded-full bg-[var(--color-primary-light)] px-2.5 py-0.5 text-xs text-[var(--color-primary)]">
            {detail.category}
          </span>
        </div>
        {/* 正文 HTML（后端已转 HTML，直接注入 + 容器排版样式） */}
        <div className="doc-prose mt-4 flex-1 overflow-y-auto rounded-xl border border-[var(--color-border)] bg-white p-8">
          <div dangerouslySetInnerHTML={{ __html: detail.html_content }} />
        </div>
      </div>
    );
  }

  // ── 列表视图 ──
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex h-full flex-col gap-5 px-9 py-7">
      {/* 页头 */}
      <div>
        <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">政策法规</h2>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
          已收录 {total || 53} 部财税法规，支持按分类筛选与关键词搜索
        </p>
      </div>

      {/* 筛选栏：分类 Tab + 搜索 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => { setCategory(''); setPage(1); load('', keyword, 1); }}
            className={cn(
              'rounded-lg px-3 py-1.5 text-sm transition-colors',
              category === ''
                ? 'bg-[var(--color-primary)] text-white'
                : 'bg-[var(--color-bg-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-primary-light)]',
            )}
          >
            全部
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => { setCategory(c); setPage(1); load(c, keyword, 1); }}
              className={cn(
                'rounded-lg px-3 py-1.5 text-sm transition-colors',
                category === c
                  ? 'bg-[var(--color-primary)] text-white'
                  : 'bg-[var(--color-bg-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-primary-light)]',
              )}
            >
              {c}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { setPage(1); load(category, keyword, 1); } }}
          placeholder="搜索法规名称…（回车搜索）"
          className="h-9 w-56 rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm outline-none focus:border-[var(--color-primary)]"
        />
      </div>

      {/* 列表 */}
      <div className="flex-1 space-y-2 overflow-y-auto">
        {loading && <Skeleton className="h-24 w-full" />}
        {error && <ErrorBanner message={error} />}
        {!loading && !error && docs.length === 0 && (
          <p className="py-10 text-center text-sm text-[var(--color-text-tertiary)]">未找到匹配的法规</p>
        )}
        {!loading &&
          !error &&
          docs.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => openDetail(d.id)}
              className="flex w-full items-center justify-between rounded-xl border border-[var(--color-border)] bg-white px-5 py-4 text-left transition-colors hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-bg-page)]"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">{d.title}</p>
                  <span className="shrink-0 rounded-full bg-[var(--color-primary-light)] px-2 py-0.5 text-[10px] text-[var(--color-primary)]">
                    {d.category}
                  </span>
                </div>
                <p className="mt-1 text-xs text-[var(--color-text-tertiary)]">
                  {d.source} · 更新于 {d.updated}
                </p>
              </div>
              <span className="ml-4 shrink-0 text-xs text-[var(--color-primary)]">查看 →</span>
            </button>
          ))}
      </div>

      {/* 分页 */}
      {!loading && totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => { const p = page - 1; setPage(p); load(category, keyword, p); }}
            className="rounded-lg border border-[var(--color-border)] bg-white px-3 py-1.5 text-xs text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-primary-light)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            上一页
          </button>
          <span className="text-xs text-[var(--color-text-tertiary)]">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => { const p = page + 1; setPage(p); load(category, keyword, p); }}
            className="rounded-lg border border-[var(--color-border)] bg-white px-3 py-1.5 text-xs text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-primary-light)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
