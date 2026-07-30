import type { Message, TaxResult, SocialResult, FormResult } from '@/lib/types';
import { CalculatorSvg } from '@/components/icons';

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  }).format(amount);
}

function renderTaxResult(data: TaxResult) {
  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-2">
        <span className="text-sm text-[var(--color-text-secondary)]">应纳税额</span>
        <span className="font-mono text-3xl font-bold text-[var(--color-primary)]">
          {formatCurrency(data.tax_amount)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-[var(--color-text-tertiary)]">年收入</span>
          <span className="ml-2 font-mono">{formatCurrency(data.annual_income)}</span>
        </div>
        <div>
          <span className="text-[var(--color-text-tertiary)]">边际税率</span>
          <span className="ml-2 font-mono">{data.marginal_rate}</span>
        </div>
        <div>
          <span className="text-[var(--color-text-tertiary)]">应纳税所得额</span>
          <span className="ml-2 font-mono">{formatCurrency(data.taxable_income)}</span>
        </div>
        <div>
          <span className="text-[var(--color-text-tertiary)]">计税基数</span>
          <span className="ml-2 font-mono">{formatCurrency(data.taxable_basis)}</span>
        </div>
      </div>

      {/* 计算过程 */}
      {data.formula && (
        <details className="group">
          <summary className="cursor-pointer text-sm text-[var(--color-primary)] hover:underline">
            展开计算过程
          </summary>
          <div className="mt-2 space-y-1 rounded-[var(--radius-md)] bg-[var(--color-bg-page)] p-3 font-mono text-xs text-[var(--color-text-secondary)]">
            <div>{data.formula}</div>
            <div>起征点扣除：{formatCurrency(data.breakdown.annual_deduction)}</div>
            <div>社保年扣除：{formatCurrency(data.breakdown.social_insurance)}</div>
            <div>专项附加扣除：{formatCurrency(data.breakdown.special_deductions)}</div>
          </div>
        </details>
      )}

      {/* 年终奖 */}
      {data.bonus && (
        <div className="rounded-[var(--radius-md)] bg-[var(--color-primary-light)] p-3 text-sm">
          <div className="font-medium text-[var(--color-primary)]">年终奖计算</div>
          <div className="mt-1 flex justify-between">
            <span>单独计税税额</span>
            <span className="font-mono">{formatCurrency(data.bonus.separate_tax)}</span>
          </div>
          <div className="mt-1 text-[var(--color-text-secondary)]">{data.bonus.recommendation}</div>
        </div>
      )}

      {/* 法规依据 */}
      {data.legal_basis && (
        <div className="border-t border-[var(--color-border)] pt-2 text-xs text-[var(--color-text-tertiary)]">
          法规依据：{data.legal_basis}
        </div>
      )}
    </div>
  );
}

function renderSocialResult(data: SocialResult) {
  const items = Object.entries(data.social_insurance.breakdown);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-[var(--radius-md)] bg-[var(--color-primary-light)] p-3">
          <div className="text-xs text-[var(--color-text-secondary)]">个人月缴</div>
          <div className="font-mono text-2xl font-bold text-[var(--color-primary)]">
            {formatCurrency(data.total_personal)}
          </div>
        </div>
        <div className="rounded-[var(--radius-md)] bg-[var(--color-bg-page)] p-3">
          <div className="text-xs text-[var(--color-text-secondary)]">单位月缴</div>
          <div className="font-mono text-2xl font-bold text-[var(--color-text-primary)]">
            {formatCurrency(data.total_company)}
          </div>
        </div>
      </div>

      {/* 逐险种明细 */}
      <div className="space-y-1">
        {items.map(([name, item]) => (
          <div key={name} className="flex items-center justify-between border-b border-[var(--color-border)]/50 py-1 text-sm last:border-0">
            <span className="text-[var(--color-text-secondary)]">{name}</span>
            <div className="flex gap-4 font-mono text-xs">
              <span>个人 {formatCurrency(item.personal)}</span>
              <span>单位 {formatCurrency(item.company)}</span>
            </div>
          </div>
        ))}
        {/* 公积金 */}
        <div className="flex items-center justify-between py-1 text-sm">
          <span className="text-[var(--color-text-secondary)]">住房公积金</span>
          <div className="flex gap-4 font-mono text-xs">
            <span>个人 {formatCurrency(data.housing_fund.personal)}</span>
            <span>单位 {formatCurrency(data.housing_fund.company)}</span>
          </div>
        </div>
      </div>

      {data.legal_basis && (
        <div className="border-t border-[var(--color-border)] pt-2 text-xs text-[var(--color-text-tertiary)]">
          法规依据：{data.legal_basis}
        </div>
      )}
    </div>
  );
}

function renderFormResult(data: FormResult) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-[var(--color-text-secondary)]">申报表类型</span>
        <span className="font-medium text-[var(--color-primary)]">{data.form_type}</span>
      </div>
      <div className="text-sm">
        已填写 <span className="font-mono font-bold text-[var(--color-primary)]">{data.filled_fields}</span> 个字段
      </div>
      {data.skipped_fields.length > 0 && (
        <div className="text-xs text-[var(--color-text-tertiary)]">
          跳过字段：{data.skipped_fields.join('、')}
        </div>
      )}
      <div className="text-xs text-[var(--color-text-tertiary)]">
        文件路径：{data.file_path}
      </div>
    </div>
  );
}

const RESULT_TITLES: Record<string, string> = {
  tax_result: '个税计算结果',
  social_result: '社保计算结果',
  form_result: '申报表生成结果',
};

export function ResultCard({ resultCard }: { resultCard: NonNullable<Message['resultCard']> }) {
  const { type, data } = resultCard;

  return (
    <div
      className="my-2 rounded-[var(--radius-lg)] border border-[#E2E8F0] border-l-4 border-l-[var(--color-primary)] bg-white p-4"
      role="region"
      aria-label={RESULT_TITLES[type] || '计算结果'}
    >
      {/* 标题行 */}
      <div className="mb-3 flex items-center gap-2">
        <CalculatorSvg className="h-5 w-5 text-[var(--color-primary)]" />
        <span className="text-lg font-semibold text-[var(--color-text-primary)]">
          {RESULT_TITLES[type] || '计算结果'}
        </span>
      </div>

      {/* 数据区 */}
      {type === 'tax_result' && renderTaxResult(data as TaxResult)}
      {type === 'social_result' && renderSocialResult(data as SocialResult)}
      {type === 'form_result' && renderFormResult(data as FormResult)}
    </div>
  );
}
