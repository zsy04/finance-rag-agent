import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/shared/Skeleton';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { SaveSvg, GenerateSvg, DownloadSvg, BlankDocSvg } from '@/components/icons';
import { useApp } from '@/context/AppContext';

// ── 常量 ──
const FORM_TYPES = [
  { value: 'A', label: 'A 表 — 雇员（单位代扣代缴）' },
  { value: 'B', label: 'B 表 — 个体工商户 / 自由职业者' },
];

const PERIOD_OPTIONS = [
  { value: 'quarter', label: '季度申报' },
  { value: 'annual', label: '年度申报' },
];

const NATIONALITY_OPTIONS = [
  { value: '中国', label: '中国' },
  { value: '华侨', label: '华侨' },
  { value: '港澳居民', label: '港澳居民' },
  { value: '台湾居民', label: '台湾居民' },
  { value: '外籍', label: '外籍个人' },
];

const GENDER_OPTIONS = [
  { value: '男', label: '男' },
  { value: '女', label: '女' },
];

const TAX_REASON_OPTIONS = [
  { value: '任职受雇', label: '任职受雇' },
  { value: '提供临时劳务', label: '提供临时劳务' },
  { value: '转让财产', label: '转让财产' },
  { value: '从事投资和经营活动', label: '从事投资和经营活动' },
  { value: '其他', label: '其他' },
];

// ── 出生日期校验 ──
function validateBirthDate(dateStr: string): { valid: boolean; message: string } {
  if (!dateStr) return { valid: false, message: '请选择出生日期' };

  const date = new Date(dateStr + 'T00:00:00');
  if (isNaN(date.getTime())) return { valid: false, message: '日期格式不正确' };

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  if (date > today) return { valid: false, message: '出生日期不能晚于今天' };

  const age = today.getFullYear() - date.getFullYear();
  if (age > 120) return { valid: false, message: '出生日期不合理' };

  // 从身份证号也能推算出生日期做交叉校验
  return { valid: true, message: '' };
}

// 日期选择器的 min/max 范围
const DATE_MIN = '1900-01-01';
function getDateMax(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 16); // 至少 16 岁
  return d.toISOString().split('T')[0];
}
function validateIdNumber(id: string): { valid: boolean; message: string } {
  if (!id) return { valid: false, message: '请输入身份证号' };
  const pattern = /^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$/;
  if (!pattern.test(id)) return { valid: false, message: '格式不正确（应为 18 位身份证号）' };
  const weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];
  const checkCodes = '10X98765432';
  const chars = id.split('');
  let sum = 0;
  for (let i = 0; i < 17; i++) sum += parseInt(chars[i]) * weights[i];
  if (chars[17].toUpperCase() !== checkCodes[sum % 11]) return { valid: false, message: '校验位不正确，请检查' };
  return { valid: true, message: '' };
}

// ── 外籍个人信息字段 ──
interface ForeignerFields {
  nationality: string;
  birthPlace: string;
  gender: string;
  firstEntryDate: string;
  expectedDepartureDate: string;
  taxReason: string;
}

const defaultForeigner: ForeignerFields = {
  nationality: '中国',
  birthPlace: '',
  gender: '',
  firstEntryDate: '',
  expectedDepartureDate: '',
  taxReason: '',
};

// ── A 表字段（雇员） ──
interface FormAState extends ForeignerFields {
  name: string;
  idNumber: string;
  birthDate: string;
  employer: string;
  annualIncome: string;
  prepaidTax: string;
  phone: string;
}

// ── B 表字段（个体户） ──
interface FormBState extends ForeignerFields {
  name: string;
  idNumber: string;
  birthDate: string;
  phone: string;
  businessName: string;
  businessCreditCode: string;
  period: 'quarter' | 'annual';
  income: string;
  cost: string;
  socialInsurance: string;
  previousLoss: string;
  deductionChildren: string;
  deductionEducation: string;
  deductionMedical: string;
  deductionMortgage: string;
  deductionElderly: string;
  deductionBaby: string;
}

function defaultFormA(salary?: number): FormAState {
  return {
    ...defaultForeigner,
    name: '',
    idNumber: '',
    birthDate: '',
    employer: '',
    annualIncome: salary ? String(salary * 12) : '',
    prepaidTax: '',
    phone: '',
  };
}

function defaultFormB(): FormBState {
  return {
    ...defaultForeigner,
    name: '',
    idNumber: '',
    birthDate: '',
    phone: '',
    businessName: '',
    businessCreditCode: '',
    period: 'quarter',
    income: '',
    cost: '',
    socialInsurance: '',
    previousLoss: '0',
    deductionChildren: '0',
    deductionEducation: '0',
    deductionMedical: '0',
    deductionMortgage: '0',
    deductionElderly: '0',
    deductionBaby: '0',
  };
}

function isForeigner(nationality: string): boolean {
  return nationality !== '中国';
}

type FormType = 'A' | 'B';

export function FilingForm() {
  const { userContext } = useApp();
  const [formType, setFormType] = useState<FormType>('A');
  const [formA, setFormA] = useState<FormAState>(defaultFormA(userContext.salary));
  const [formB, setFormB] = useState<FormBState>(defaultFormB());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idValidation, setIdValidation] = useState<{ valid: boolean; message: string }>({ valid: true, message: '' });
  const [birthValidation, setBirthValidation] = useState<{ valid: boolean; message: string }>({ valid: true, message: '' });
  const [result, setResult] = useState<{
    form_type: string;
    file_path: string;
    filled_fields: number;
    skipped_fields: string[];
    preview?: string;
  } | null>(null);

  const handleFormTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setFormType(e.target.value as FormType);
    setResult(null);
    setError(null);
    setIdValidation({ valid: true, message: '' });
    setBirthValidation({ valid: true, message: '' });
  };

  // ── A 表更新 ──
  const updateA = (key: keyof FormAState, value: string) =>
    setFormA((prev) => ({ ...prev, [key]: value }));

  // ── B 表更新 ──
  const updateB = (key: keyof FormBState, value: string) =>
    setFormB((prev) => ({ ...prev, [key]: value }));

  // ── 保存草稿 ──
  const handleSaveDraft = () => {
    localStorage.setItem(
      'filing_form_draft',
      JSON.stringify(formType === 'A' ? { type: 'A', data: formA } : { type: 'B', data: formB }),
    );
  };

  // ── 生成申报表 ──
  const handleGenerate = async () => {
    const form = formType === 'A' ? formA : formB;
    const id = form.idNumber;
    const name = form.name;

    if (!name || !id) {
      setError('请填写姓名和身份证号');
      return;
    }

    const validation = validateIdNumber(id);
    if (!validation.valid) {
      setIdValidation(validation);
      setError(validation.message);
      return;
    }
    setIdValidation({ valid: true, message: '' });

    // 出生日期校验
    const birthCheck = validateBirthDate(form.birthDate);
    if (!birthCheck.valid) {
      setBirthValidation(birthCheck);
      setError(birthCheck.message);
      return;
    }
    setBirthValidation({ valid: true, message: '' });

    // B表手机号必填
    if (formType === 'B' && !formB.phone) {
      setError('B 表手机号为必填项');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      // 构建 user_data
      let formTypeName: string;
      let userData: Record<string, string>;

      if (formType === 'A') {
        formTypeName = 'A表';
        userData = {
          '纳税人姓名': formA.name,
          '身份证件类型': '居民身份证',
          '身份证件号码': formA.idNumber,
          '出生日期': formA.birthDate,
          '国籍/地区': formA.nationality,
          '任职受雇从业类型': '雇员',
          '手机号码': formA.phone,
        };
        if (formA.employer) userData['任职单位'] = formA.employer;
        if (isForeigner(formA.nationality)) {
          userData['出生地'] = formA.birthPlace;
          userData['性别'] = formA.gender;
          if (formA.firstEntryDate) userData['首次入境时间'] = formA.firstEntryDate;
          if (formA.expectedDepartureDate) userData['预计离境时间'] = formA.expectedDepartureDate;
          if (formA.taxReason) userData['涉税事由'] = formA.taxReason;
        }
      } else {
        formTypeName = 'B表';
        userData = {
          '纳税人姓名': formB.name,
          '身份证件类型': '居民身份证',
          '身份证件号码': formB.idNumber,
          '出生日期': formB.birthDate,
          '国籍/地区': formB.nationality,
          '手机号码': formB.phone,
          '被投资单位名称': formB.businessName,
          '被投资单位信用代码': formB.businessCreditCode,
          '经营收入': formB.income,
          '成本费用': formB.cost,
          '自己交的社保': formB.socialInsurance,
          '以前年度亏损': formB.previousLoss,
          '申报周期': formB.period === 'quarter' ? '季度' : '年度',
        };
        if (isForeigner(formB.nationality)) {
          userData['出生地'] = formB.birthPlace;
          userData['性别'] = formB.gender;
          if (formB.firstEntryDate) userData['首次入境时间'] = formB.firstEntryDate;
          if (formB.expectedDepartureDate) userData['预计离境时间'] = formB.expectedDepartureDate;
          if (formB.taxReason) userData['涉税事由'] = formB.taxReason;
        }
      }

      const res = await fetch('/api/form/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ form_type: formTypeName, user_data: userData }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '生成失败' }));
        throw new Error(err.detail || `请求失败: ${res.status}`);
      }

      const data = await res.json();
      setResult({
        form_type: data.form_type,
        file_path: data.file_path,
        filled_fields: data.filled_fields,
        skipped_fields: data.skipped_fields || [],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  // ── 华侨/港澳台/外籍个人附加字段区 ──
  function renderForeignerFields<T extends ForeignerFields>(
    form: T,
    update: (key: keyof T, value: string) => void,
  ) {
    if (!isForeigner(form.nationality)) return null;

    return (
      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-subtle)] p-6">
        <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
          华侨、港澳台、外籍个人信息
          <span className="ml-2 text-xs font-normal text-[var(--color-error)]">*必填</span>
        </h3>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">*出生地</label>
            <Input
              value={(form as unknown as FormAState).birthPlace ?? ''}
              onChange={(e) => update('birthPlace' as keyof T, e.target.value)}
              placeholder="如：美国"
              aria-label="出生地"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">*性别</label>
            <Select
              value={(form as unknown as FormAState).gender ?? ''}
              onChange={(e) => update('gender' as keyof T, e.target.value)}
            >
              <option value="">请选择</option>
              {GENDER_OPTIONS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">首次入境时间</label>
            <Input
              type="date"
              value={form.firstEntryDate}
              onChange={(e) => update('firstEntryDate' as keyof T, e.target.value)}
              aria-label="首次入境时间"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">预计离境时间</label>
            <Input
              type="date"
              value={form.expectedDepartureDate}
              onChange={(e) => update('expectedDepartureDate' as keyof T, e.target.value)}
              aria-label="预计离境时间"
            />
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">*涉税事由</label>
          <Select
            value={form.taxReason}
            onChange={(e) => update('taxReason' as keyof T, e.target.value)}
          >
            <option value="">请选择</option>
            {TAX_REASON_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </Select>
        </div>
      </div>
    );
  }

  // ── B 表经营数据区 ──
  const renderBusinessSection = () => (
    <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
      <h3 className="text-base font-semibold text-[var(--color-text-primary)]">经营信息</h3>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">个体工商户名称</label>
          <Input
            value={formB.businessName}
            onChange={(e) => updateB('businessName', e.target.value)}
            placeholder="如：郑州市XX餐饮店"
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">统一社会信用代码</label>
          <Input
            value={formB.businessCreditCode}
            onChange={(e) => updateB('businessCreditCode', e.target.value)}
            placeholder="如：92410100MA12345678"
          />
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-sm text-[var(--color-text-secondary)]">申报周期</label>
        <Select value={formB.period} onChange={(e) => updateB('period', e.target.value)}>
          {PERIOD_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </Select>
        {formB.period === 'quarter' && (
          <p className="text-xs text-[var(--color-text-tertiary)]">
            季度申报期：1月（上年Q4）/ 4月（本年Q1）/ 7月（本年Q2）/ 10月（本年Q3）。系统会自动将季度数据折算为年度计税。
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">
            {formB.period === 'quarter' ? '季度经营收入（元）' : '年度经营收入（元）'}
          </label>
          <Input type="number" value={formB.income} onChange={(e) => updateB('income', e.target.value)} placeholder={formB.period === 'quarter' ? '如 32000' : '如 128000'} />
        </div>
        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">
            成本费用（元）<span className="text-xs text-[var(--color-text-tertiary)]">含房租/进货/人工/水电</span>
          </label>
          <Input type="number" value={formB.cost} onChange={(e) => updateB('cost', e.target.value)} placeholder="如 40000" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">自己交的社保（元/年）</label>
          <Input type="number" value={formB.socialInsurance} onChange={(e) => updateB('socialInsurance', e.target.value)} placeholder="如 9600" />
        </div>
        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">以前年度亏损（元）</label>
          <Input type="number" value={formB.previousLoss} onChange={(e) => updateB('previousLoss', e.target.value)} placeholder="如 5000" />
        </div>
      </div>
    </div>
  );

  // ── B 表专项扣除区 ──
  const renderDeductionSection = () => (
    <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
      <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
        专项附加扣除
        <span className="ml-2 text-xs font-normal text-[var(--color-text-tertiary)]">（年扣除额，个体户房租已计入成本，此处不含住房租金）</span>
      </h3>
      <div className="grid grid-cols-3 gap-4">
        {[
          { key: 'deductionChildren' as const, label: '子女教育', note: '2000元/月/子女' },
          { key: 'deductionEducation' as const, label: '继续教育', note: '400元/月 或 3600元/年' },
          { key: 'deductionMedical' as const, label: '大病医疗', note: '自付超15000部分据实扣' },
          { key: 'deductionMortgage' as const, label: '住房贷款利息', note: '1000元/月' },
          { key: 'deductionElderly' as const, label: '赡养老人', note: '3000元/月' },
          { key: 'deductionBaby' as const, label: '婴幼儿照护', note: '2000元/月/人' },
        ].map(({ key, label, note }) => (
          <div key={key} className="space-y-1">
            <label className="text-sm text-[var(--color-text-secondary)]">{label}<span className="ml-1 text-xs text-[var(--color-text-tertiary)]">({note})</span></label>
            <Input type="number" value={formB[key]} onChange={(e) => updateB(key, e.target.value)} placeholder="0" />
          </div>
        ))}
      </div>
    </div>
  );

  // ── A 表收入区 ──
  const renderEmployerSection = () => (
    <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
      <h3 className="text-base font-semibold text-[var(--color-text-primary)]">收入信息</h3>
      <div className="space-y-2">
        <label className="text-sm text-[var(--color-text-secondary)]">任职单位</label>
        <Input value={formA.employer} onChange={(e) => updateA('employer', e.target.value)} placeholder="请输入任职单位名称" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">年收入（元）</label>
          <Input type="number" value={formA.annualIncome} onChange={(e) => updateA('annualIncome', e.target.value)} placeholder="如 96000" />
        </div>
        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">已预缴税额（元）</label>
          <Input type="number" value={formA.prepaidTax} onChange={(e) => updateA('prepaidTax', e.target.value)} placeholder="如 2000" />
        </div>
      </div>
    </div>
  );

  // ── 当前表单引用 ──
  const currentForm = formType === 'A' ? formA : formB;

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-6 py-8">
      <div className="flex items-center gap-2">
        <GenerateSvg className="h-6 w-6 text-[var(--color-primary)]" />
        <h1 className="text-xl font-bold text-[var(--color-text-primary)]">申报材料生成</h1>
      </div>

      {/* 表单类型选择 */}
      <div className="space-y-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
        <h3 className="text-base font-semibold text-[var(--color-text-primary)]">选择申报类型</h3>
        <Select value={formType} onChange={handleFormTypeChange}>
          {FORM_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </Select>
        <p className="text-sm text-[var(--color-text-secondary)]">
          {formType === 'A'
            ? 'A 表适用于有固定任职单位的雇员，由单位代扣代缴个税。需填写任职单位信息。'
            : 'B 表适用于个体工商户、自由职业者等无扣缴义务人的纳税人。身份证件固定为居民身份证，经营所得按季度或年度自行申报。'}
        </p>
      </div>

      {/* 基本信息（A/B 通用） */}
      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
        <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
          基本信息
          <span className="ml-2 text-xs font-normal text-[var(--color-text-tertiary)]">带 * 为必填</span>
        </h3>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">*纳税人姓名</label>
            <Input
              value={currentForm.name}
              onChange={(e) => formType === 'A' ? updateA('name', e.target.value) : updateB('name', e.target.value)}
              placeholder="请输入姓名"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">*身份证号</label>
            <Input
              value={currentForm.idNumber}
              onChange={(e) => {
                const v = e.target.value;
                formType === 'A' ? updateA('idNumber', v) : updateB('idNumber', v);
                if (idValidation.message) setIdValidation({ valid: true, message: '' });
                if (error) setError(null);
              }}
              onBlur={(e) => { if (e.target.value) setIdValidation(validateIdNumber(e.target.value)); }}
              placeholder={formType === 'B' ? '请输入 18 位居民身份证号' : '请输入 18 位身份证号'}
              aria-invalid={!idValidation.valid}
            />
            {!idValidation.valid && idValidation.message && (
              <p className="text-xs text-[var(--color-error)]">{idValidation.message}</p>
            )}
          </div>
        </div>

        {/* A 表身份证类型可选，B 表固定为居民身份证 */}
        {formType === 'A' ? (
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">*身份证件类型</label>
            <Select value="居民身份证" onChange={() => {}}>
              <option value="居民身份证">居民身份证</option>
            </Select>
            <p className="text-xs text-[var(--color-text-tertiary)]">A 表默认使用居民身份证</p>
          </div>
        ) : (
          <div className="space-y-1 rounded-[var(--radius-md)] bg-[var(--color-bg-subtle)] px-3 py-2">
            <p className="text-sm text-[var(--color-text-secondary)]">
              身份证件类型：<span className="font-medium text-[var(--color-text-primary)]">居民身份证</span>
              <span className="ml-2 text-xs text-[var(--color-text-tertiary)]">B 表固定</span>
            </p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">*出生日期</label>
            <Input
              type="date"
              value={currentForm.birthDate}
              min={DATE_MIN}
              max={getDateMax()}
              onChange={(e) => {
                const v = e.target.value;
                formType === 'A' ? updateA('birthDate', v) : updateB('birthDate', v);
                if (birthValidation.message) setBirthValidation({ valid: true, message: '' });
                if (error) setError(null);
              }}
              onBlur={(e) => {
                if (e.target.value) setBirthValidation(validateBirthDate(e.target.value));
              }}
              aria-label="出生日期"
              aria-invalid={!birthValidation.valid}
            />
            {!birthValidation.valid && birthValidation.message && (
              <p className="text-xs text-[var(--color-error)]">{birthValidation.message}</p>
            )}
            <p className="text-xs text-[var(--color-text-tertiary)]">
              点击日历图标选择，或输入 YYYY-MM-DD 格式
            </p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-[var(--color-text-secondary)]">*国籍/地区</label>
            <Select
              value={currentForm.nationality}
              onChange={(e) => formType === 'A' ? updateA('nationality', e.target.value) : updateB('nationality', e.target.value)}
            >
              {NATIONALITY_OPTIONS.map((n) => <option key={n.value} value={n.value}>{n.label}</option>)}
            </Select>
          </div>
        </div>

        {/* 手机号：A 表选填，B 表必填 */}
        <div className="space-y-2">
          <label className="text-sm text-[var(--color-text-secondary)]">
            {formType === 'B' ? '*手机号码' : '手机号码'}
            {formType === 'A' && <span className="ml-1 text-xs text-[var(--color-text-tertiary)]">选填</span>}
          </label>
          <Input
            value={currentForm.phone}
            onChange={(e) => formType === 'A' ? updateA('phone', e.target.value) : updateB('phone', e.target.value)}
            placeholder="请输入境内有效手机号"
          />
        </div>
      </div>

      {/* 华侨/港澳台/外籍个人附加字段 — 选非中国时显示 */}
      {formType === 'A' && renderForeignerFields(formA, updateA)}
      {formType === 'B' && renderForeignerFields(formB, updateB)}

      {/* A 表：任职单位 + 收入 */}
      {formType === 'A' && renderEmployerSection()}

      {/* B 表：经营信息 */}
      {formType === 'B' && renderBusinessSection()}

      {/* B 表：专项附加扣除 */}
      {formType === 'B' && renderDeductionSection()}

      {/* B 表计税公式说明 */}
      {formType === 'B' && (
        <div className="rounded-[var(--radius-md)] bg-[var(--color-bg-subtle)] p-4">
          <p className="text-xs leading-relaxed text-[var(--color-text-tertiary)]">
            <strong className="text-[var(--color-text-secondary)]">计税逻辑：</strong>
            应纳税所得额 = 经营收入 - 成本费用 - 社保 - 基本扣除(60,000元/年) - 专项附加扣除 - 以前年度亏损。
            按 5%~35% 五级超额累进税率计税（季度数据自动折算为年度计算后再还原）。
          </p>
        </div>
      )}

      {/* 按钮 */}
      <div className="flex justify-end gap-3">
        <Button variant="secondary" onClick={handleSaveDraft}>
          <SaveSvg className="h-4 w-4" />保存草稿
        </Button>
        <Button onClick={handleGenerate} disabled={loading}>
          <GenerateSvg className="h-4 w-4" />{loading ? '生成中……' : '生成申报表'}
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
          <h3 className="text-lg font-semibold text-[var(--color-primary)]">申报表生成完成</h3>
          <div className="space-y-1 text-sm">
            <div><span className="text-[var(--color-text-secondary)]">申报表类型：</span><span className="font-medium">{result.form_type}</span></div>
            <div><span className="text-[var(--color-text-secondary)]">已填写字段：</span><span className="font-mono font-bold text-[var(--color-primary)]">{result.filled_fields}</span> 个</div>
            {result.skipped_fields.length > 0 && <div className="text-xs text-[var(--color-text-tertiary)]">跳过字段：{result.skipped_fields.join('、')}</div>}
          </div>
          <div className="flex gap-3">
            <a href={`/api/form/download?path=${encodeURIComponent(result.file_path)}`} className="inline-flex h-10 items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-primary)] px-4 text-sm font-medium text-white transition-all hover:bg-[var(--color-primary-dark)]">
              <DownloadSvg className="h-4 w-4" />下载填好的表
            </a>
            <a href={`/api/form/download?blank=blank_${result.form_type}`} className="inline-flex h-10 items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-primary)] bg-white px-4 text-sm font-medium text-[var(--color-primary)] transition-all hover:bg-[var(--color-primary-light)]">
              <BlankDocSvg className="h-4 w-4" />下载空白原表
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
