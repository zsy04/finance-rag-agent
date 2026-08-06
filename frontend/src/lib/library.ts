import type {
  LibraryDocMeta,
  LibraryDocDetail,
  BenchmarkItem,
} from '@/lib/types';

/**
 * 资料库接口封装（2026-08-06 联调）
 * 后端：backend/routers/library.py，纯文件读取秒回
 * 前端通过 Vite 代理访问 /api → http://localhost:8000
 */

const BASE = '/api/library';

/** GET 封装：拼查询参数 + JSON 解析，非 200 抛错 */
async function getJSON<T>(
  path: string,
  params?: Record<string, string | number | undefined | null>,
): Promise<T> {
  const url = new URL(path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, String(v));
      }
    }
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `请求失败: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ---- 政策法规 ----

export interface LibraryListResponse {
  total: number;
  items: LibraryDocMeta[];
}

/** 法规列表：category（法律/行政法规/部门规章/规范性文件）/ keyword / limit / offset */
export function fetchDocuments(params: {
  category?: string;
  keyword?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<LibraryListResponse> {
  return getJSON<LibraryListResponse>(`${BASE}/documents`, {
    category: params.category,
    keyword: params.keyword,
    limit: params.limit !== undefined ? String(params.limit) : undefined,
    offset: params.offset !== undefined ? String(params.offset) : undefined,
  });
}

/** 法规正文：doc_id 为中文，必须 encodeURIComponent */
export function fetchDocumentDetail(docId: string): Promise<LibraryDocDetail> {
  return getJSON<LibraryDocDetail>(`${BASE}/documents/${encodeURIComponent(docId)}`);
}

// ---- 行业指标基准 ----

export interface BenchmarkResponse {
  total: number;
  industries: BenchmarkItem[];
}

/** 行业基准：category（行业门类精确）/ keyword（细分行业模糊） */
export function fetchBenchmark(params: {
  category?: string;
  keyword?: string;
} = {}): Promise<BenchmarkResponse> {
  return getJSON<BenchmarkResponse>(`${BASE}/benchmark`, params);
}

// ---- 城市（预留） ----

export interface CityInfo {
  code: string;
  name: string;
  province: string;
  city_code: string;
  data_version: string;
}

export interface CitiesResponse {
  total: number;
  cities: CityInfo[];
}

export function fetchCities(): Promise<CitiesResponse> {
  return getJSON<CitiesResponse>(`${BASE}/cities`);
}
