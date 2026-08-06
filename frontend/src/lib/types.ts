// ====== 视图导航（2026-08-06 设计稿落地扩展为 6 视图） ======
// chat 智能问答 / calculator 税率计算 / form 申报材料 / guide 申报指引 / documents 政策法规 / benchmark 行业基准
export type ActiveView = 'chat' | 'calculator' | 'form' | 'guide' | 'documents' | 'benchmark';

// ====== 模型切换器（2026-08-06 新增，对齐后端 /api/models + /api/chat provider） ======
// 请求携带的 provider 配置（后端转发调用，保留 Agent 全链路）
export interface ProviderConfig {
  base_url?: string;
  api_key?: string;
  model: string;
  context_window?: number;
}

// 后端 GET /api/models 返回的供应商模板（设置页下拉数据源，不含 key）
export interface ProviderTemplate {
  id: string;
  label: string;
  base_url: string;
  default_model: string;
  context_window: number;
}

// localStorage 中保存的用户自配 provider（lest_providers / lest_active_provider）
export interface SavedProvider {
  id: string;            // 本地 uuid（区分多套配置）
  name: string;          // 用户起的名字（如"我的千问"）
  base_url: string;
  api_key: string;
  model: string;
  context_window: number;
}

// ====== 资料库（2026-08-06 新增，对齐后端 /api/library/*） ======
export interface LibraryDocMeta {
  id: string;
  title: string;
  category: string;      // 法律/行政法规/部门规章/规范性文件
  level?: string;
  updated?: string;
  source?: string;
}
export interface LibraryDocDetail extends LibraryDocMeta {
  html_content: string;  // 后端 Markdown → HTML
}
export interface BenchmarkIndicator { low: number | null; high: number | null; }
export interface BenchmarkItem {
  category: string;      // 行业门类
  sub_industry: string;  // 细分行业
  indicators: Record<string, BenchmarkIndicator>;  // 10 项指标（vat_burden/cit_burden/gross_margin/…）
}

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
  sources?: Source[];
  disclaimer?: string;
  contextNotice?: string;  // 历史摘要提示（SSE context 事件）
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

// ====== 会话元信息（多会话列表） ======
export interface ThreadMeta {
  thread_id: string;
  title: string; // 首条 user 消息预览（空会话为 ""）
  message_count: number;
  updated_at: string;
}

// ====== SSE 事件 ======
export type SSEEventType =
  | 'thinking'
  | 'step'
  | 'result'
  | 'source'
  | 'disclaimer'
  | 'context'
  | 'error'
  | 'done';

export interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}
