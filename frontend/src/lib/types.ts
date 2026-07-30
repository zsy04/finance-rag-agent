// ====== 视图导航 ======
export type ActiveView = 'chat' | 'calculator' | 'form';

// ====== 对话消息 ======
export type MessageRole = 'user' | 'assistant' | 'system';

export interface Source {
  title: string;
  url: string;
  tier?: string;
  relation?: string;
}

export interface TaxResult {
  annual_income: number;
  income_type: string;
  taxable_basis: number;
  taxable_income: number;
  tax_amount: number;
  marginal_rate: string;
  bracket_level: number;
  formula: string;
  breakdown: {
    annual_deduction: number;
    social_insurance: number;
    special_deductions: number;
  };
  legal_basis: string;
  bonus?: {
    amount: number;
    separate_tax: number;
    recommendation: string;
    saving: number;
  };
}

export interface SocialResult {
  city: string;
  employment_type: string;
  salary: number;
  social_insurance: {
    base: number;
    breakdown: Record<string, {
      base: number;
      rate_company: number;
      rate_personal: number;
      company: number;
      personal: number;
    }>;
    total_personal: number;
    total_company: number;
  };
  housing_fund: {
    base: number;
    ratio: number;
    personal: number;
    company: number;
  };
  total_personal: number;
  total_company: number;
  legal_basis: string;
}

export interface FormResult {
  form_type: string;
  file_path: string;
  filled_fields: number;
  skipped_fields: string[];
}

export type ResultCardType = 'tax_result' | 'social_result' | 'form_result';

export interface ResultCardData {
  type: ResultCardType;
  data: TaxResult | SocialResult | FormResult;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  resultCard?: ResultCardData | null;
  steps?: string[];
  sources?: Source[];
  disclaimer?: string;
  isStreaming?: boolean;
  isError?: boolean;
}

// ====== 对话上下文（跨视图共享，仅用于快捷表单预填） ======
// 注意：对话上下文由 Agent 内部管理（get_user_context / update_user_context @tool），
// 前端不需要传递 context 给后端。以下 UserContext 仅用于快捷表单间数据预填。
export interface UserContext {
  city: string;
  salary?: number;
  incomeType?: string;
  deductions: Record<string, number>;
}

// ====== SSE 事件 ======
export type SSEEventType =
  | 'thinking'
  | 'step'
  | 'result'
  | 'source'
  | 'disclaimer'
  | 'error'
  | 'done';

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}
