import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { ResultCard } from '@/components/chat/ResultCard';
import { Skeleton } from '@/components/shared/Skeleton';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { CalculatorSvg, HelpSvg } from '@/components/icons';
import { calculateTax, calculateSocial } from '@/lib/sse';
import { useApp } from '@/context/AppContext';
import type { ResultCardData } from '@/lib/types';

const INCOME_TYPES = [
  { value: 'salary', label: '综合所得（工资薪金）' },
  { value: 'labor_service', label: '劳务报酬' },
  { value: 'manuscript', label: '稿酬所得' },
  { value: 'royalty', label: '特许权使用费' },
];

const DEDUCTION_ITEMS = [
  { key: 'housing_rent', label: '租房扣除', hint: '按城市标准，郑州 1500 元/月' },
  { key: 'children_edu', label: '子女教育', hint: '每个子女 2000 元/月' },
  { key: 'elderly_support', label: '赡养老人', hint: '独生子女 3000 元/月，非独生子女分摊' },
  { key: 'continuing_education', label: '继续教育', hint: '学历教育 400 元/月' },
  { key: 'major_medical', label: '大病医疗', hint: '超过 15000 元部分据实扣除' },
  { key: 'housing_loan', label: '房贷利息', hint: '首套房贷 1000 元/月' },
  { key: 'childcare', label: '婴幼儿照护', hint: '3 岁以下每个 2000 元/月' },
];

function FieldLabel({ label, hint }: { label: string; hint: string }) {
  return (
    <div className="flex items-center gap-1">
      <span>{label}</span>
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" className="text-[var(--color-text-tertiary)] hover:text-[var(--color-primary)]">
            <HelpSvg className="h-4 w-4" />
          </button>
        </TooltipTrigger>
        <TooltipContent>{hint}</TooltipContent>
      </Tooltip>
    </div>
  );
}

export function TaxCalculator() {
  const { setActiveView, updateUserContext } = useApp();
  const [incomeType, setIncomeType] = useState('salary');
  const [monthlySalary, setMonthlySalary] = useState('');
  const [deductions, setDeductions] = useState<Record<string, string>>({});
  const [bonus, setBonus] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ResultCardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const annualIncome = Number(monthlySalary) * 12 || 0;

  const handleReset = () => {
    setMonthlySalary('');
    setIncomeType('salary');
    setDeductions({});
    setBonus('');
    setResult(null);
    setError(null);
  };

  const handleCalculate = async () => {
    if (!monthlySalary) {
      setError('请输入税前月薪');
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      // 社保：优先查询精确个人缴纳额，失败则回退 10.5% 估算
      let socialInsurance = Math.round(Number(monthlySalary) * 0.105 * 12);
      try {
        const social = await calculateSocial({
          salary: Number(monthlySalary),
          employment_type: 'employee',
        });
        if (typeof social.total_personal === 'number') {
          socialInsurance = Math.round(social.total_personal * 12);
        }
      } catch {
        // 社保查询失败，沿用估算值
      }

      const payload: Record<string, unknown> = {
        annual_income: annualIncome,
        income_type: incomeType,
        social_insurance: socialInsurance,
      };

      // 扣除项（发送月额，后端会 ×12 转年额）
      for (const item of DEDUCTION_ITEMS) {
        const val = Number(deductions[item.key]);
        if (val > 0) {
          payload[item.key] = val;
        }
      }

      if (bonus) {
        payload.bonus = Number(bonus);
      }

      const data = await calculateTax(payload as Parameters<typeof calculateTax>[0]);
      setResult({ type: 'tax_result', data });

      // 同步到用户上下文
      updateUserContext({
        salary: Number(monthlySalary),
        incomeType,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '计算失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <TooltipProvider>
      <div className="mx-auto max-w-2xl space-y-6 px-6 py-8">
        {/* 标题 */}
        <div className="flex items-center gap-2">
          <CalculatorSvg className="h-6 w-6 text-[var(--color-primary)]" />
          <h1 className="text-xl font-bold text-[var(--color-text-primary)]">税率计算器</h1>
        </div>

        {/* 收入信息 */}
        <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
          <div className="space-y-2">
            <FieldLabel label="收入类型" hint="选择你的收入类型，不同类型适用不同税率" />
            <Select value={incomeType} onChange={(e) => setIncomeType(e.target.value)}>
              {INCOME_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </Select>
          </div>

          <div className="space-y-2">
            <FieldLabel label="税前月薪" hint="输入你的税前月工资，将自动乘以 12 计算年收入" />
            <div className="flex items-center gap-2">
              <Input
                type="number"
                value={monthlySalary}
                onChange={(e) => setMonthlySalary(e.target.value)}
                placeholder="如 8000"
                aria-label="税前月薪"
              />
              <span className="text-sm text-[var(--color-text-secondary)]">元</span>
            </div>
            {annualIncome > 0 && (
              <div className="text-xs text-[var(--color-text-tertiary)]">
                年收入：¥{annualIncome.toLocaleString()}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <FieldLabel label="所在城市" hint="不同城市社保基数和租房扣除标准不同" />
            <Select disabled defaultValue="zhengzhou">
              <option value="zhengzhou">郑州</option>
            </Select>
          </div>
        </div>

        {/* 扣除项 */}
        <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
          <h3 className="text-base font-semibold text-[var(--color-text-primary)]">扣除项</h3>

          <div className="grid grid-cols-2 gap-4">
            {DEDUCTION_ITEMS.map((item) => (
              <div key={item.key} className="space-y-1">
                <FieldLabel label={item.label} hint={item.hint} />
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    value={deductions[item.key] || ''}
                    onChange={(e) =>
                      setDeductions((prev) => ({ ...prev, [item.key]: e.target.value }))
                    }
                    placeholder="0"
                    className="h-8"
                    aria-label={item.label}
                  />
                  <span className="text-xs text-[var(--color-text-tertiary)]">元/月</span>
                </div>
              </div>
            ))}
          </div>

          {/* 年终奖 */}
          <div className="space-y-1">
            <FieldLabel label="年终奖（可选）" hint="全年一次性奖金，可选择单独计税或并入综合所得" />
            <div className="flex items-center gap-2">
              <Input
                type="number"
                value={bonus}
                onChange={(e) => setBonus(e.target.value)}
                placeholder="0"
                className="h-8"
                aria-label="年终奖"
              />
              <span className="text-xs text-[var(--color-text-tertiary)]">元</span>
            </div>
          </div>
        </div>

        {/* 计算按钮 */}
        <div className="flex justify-center gap-3">
          <Button
            onClick={handleCalculate}
            disabled={loading}
            size="lg"
            className="w-full max-w-xs"
          >
            <CalculatorSvg className="h-4 w-4 text-white" />
            {loading ? '计算中……' : '开始计算'}
          </Button>
          <Button
            variant="secondary"
            onClick={handleReset}
            size="lg"
            disabled={loading}
          >
            清空
          </Button>
        </div>

        {/* 结果区 */}
        {loading && (
          <div className="space-y-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-white p-4">
            <Skeleton lineCount={3} />
          </div>
        )}

        {error && <ErrorBanner message={error} onRetry={handleCalculate} />}

        {result && (
          <div>
            <ResultCard resultCard={result} />
            {/* 切换到对话模式 */}
            <div className="mt-3 text-center">
              <button
                onClick={() => setActiveView('chat')}
                className="text-sm text-[var(--color-primary)] hover:underline"
              >
                💡 想了解更多？切换到对话模式
              </button>
            </div>
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
