import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * Markdown 渲染器 — 将 AI 回复中的 Markdown 语法渲染为格式化 HTML
 * 使用 remark-gfm 支持 GitHub Flavored Markdown（表格、删除线、任务列表等）
 */
export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div
      className={cn(
        'text-sm leading-relaxed',
        '[&_p]:my-1.5',
        '[&_p:first-child]:mt-0',
        '[&_p:last-child]:mb-0',
        '[&_h1]:mb-2 mt-1 [&_h1]:text-lg [&_h1]:font-bold',
        '[&_h2]:mb-2 mt-1 [&_h2]:text-base [&_h2]:font-bold',
        '[&_h3]:mb-1.5 mt-1 [&_h3]:text-sm [&_h3]:font-semibold',
        '[&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5',
        '[&_ol]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5',
        '[&_li]:my-0.5',
        '[&_strong]:font-semibold',
        '[&_em]:italic',
        '[&_del]:line-through [&_del]:text-[var(--color-text-tertiary)]',
        '[&_a]:text-[var(--color-primary)] [&_a]:underline',
        '[&_code]:rounded [&_code]:bg-[var(--color-bg-page)] [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs',
        '[&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-[var(--radius-md)] [&_pre]:bg-[var(--color-text-primary)] [&_pre]:p-3',
        '[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-xs [&_pre_code]:text-[var(--color-bg-page)]',
        '[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--color-primary)] [&_blockquote]:pl-3 [&_blockquote]:text-[var(--color-text-secondary)]',
        // 表格样式
        '[&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_table]:overflow-hidden [&_table]:rounded-[var(--radius-md)]',
        '[&_thead]:bg-[var(--color-bg-page)]',
        '[&_th]:border [&_th]:border-[var(--color-border)] [&_th]:px-3 [&_th]:py-1.5 [&_th]:text-left [&_th]:text-xs [&_th]:font-semibold [&_th]:text-[var(--color-text-secondary)]',
        '[&_td]:border [&_td]:border-[var(--color-border)] [&_td]:px-3 [&_td]:py-1.5 [&_td]:text-xs [&_td]:text-[var(--color-text-primary)]',
        '[&_tbody_tr:nth-child(even)]:bg-[var(--color-bg-page)]/50',
        '[&_hr]:my-3 [&_hr]:border-[var(--color-border)]',
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
