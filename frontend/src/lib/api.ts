import type {
  ApiKey,
  ArticleContent,
  BudgetData,
  BudgetLimits,
  DigestConfig,
  DigestDetail,
  DigestEntry,
  DigestRunSummary,
  DigestItem,
  FeedTokenInfo,
  Job,
  LlmConfig,
  NetworkConfig,
  NetworkTestResult,
  PasswordInfo,
  PreferenceProfile,
  ProvidersConfig,
  ReadLaterItem,
  RatingArticle,
  RankingWeights,
  RunLog,
  RunLogSummary,
  ScheduleConfig,
  SchedulerStatus,
  Source,
  StarredItem,
} from './types';

interface RequestOptions {
  /**
   * Publication reads are intentionally public. A 401 from one of these
   * endpoints must not make the rest of the application treat the session as
   * expired.
   */
  dispatchAuthExpired?: boolean;
}

/** Generic HTTP helper. Throws on non-2xx responses. */
async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const init: RequestInit = { method, credentials: 'include' };
  if (body != null) {
    if (body instanceof FormData) {
      init.body = body;
    } else {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
  }
  const res = await fetch(path, init);
  if (!res.ok) {
    if (res.status === 401 && options.dispatchAuthExpired !== false) {
      window.dispatchEvent(new CustomEvent('auth:expired'));
    }
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${method} ${path} failed (${res.status}): ${text}`);
  }
  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) {
    return res.json() as Promise<T>;
  }
  return undefined as T;
}

export const api = {
  // Digests
  listDigests: (limit?: number, beforeId?: number) => {
    const query = new URLSearchParams();
    if (limit != null) query.set('limit', String(limit));
    if (beforeId != null) query.set('before_id', String(beforeId));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<DigestEntry[]>(
      'GET',
      `/api/digests${suffix}`,
      undefined,
      { dispatchAuthExpired: false },
    );
  },
  getLatestDigest: () =>
    request<DigestDetail | null>(
      'GET',
      '/api/digests/latest',
      undefined,
      { dispatchAuthExpired: false },
    ),
  getDigest: (id: number) =>
    request<DigestDetail>(
      'GET',
      `/api/digests/${id}`,
      undefined,
      { dispatchAuthExpired: false },
    ),

  getArticleContent: (url: string) =>
    request<ArticleContent>(
      'GET',
      `/api/articles/content?url=${encodeURIComponent(url)}`,
      undefined,
      { dispatchAuthExpired: false },
    ),

  // Job
  getJobStatus: () => request<Job>('GET', '/api/digest/status'),
  runDigest: () =>
    request<{ ok: boolean; message: string; job: Job }>(
      'POST',
      '/api/digest/run',
    ),
  dismissJob: () => request<Job>('POST', '/api/digest/dismiss'),
  listDigestRuns: (limit = 20) =>
    request<DigestRunSummary[]>('GET', `/api/digest/runs?limit=${limit}`),
  getLatestDigestRun: () =>
    request<DigestRunSummary | null>('GET', '/api/digest/runs/latest'),
  getDigestRun: (id: number) =>
    request<DigestRunSummary>('GET', `/api/digest/runs/${id}`),

  // Read tracking
  getReadUrls: () => request<{ urls: string[] }>('GET', '/api/read'),
  markRead: (url: string, isRead: boolean) =>
    request<void>('POST', '/api/read', { url, read: isRead }),

  // Dismiss (negative implicit signal + mark as read)
  dismissArticle: (url: string, title?: string) =>
    request<void>('POST', '/api/dismiss', { url, title: title ?? '' }),

  // Ratings
  getRatings: () => request<RatingArticle[]>('GET', '/api/ratings'),
  submitRating: (url: string, rating: number) =>
    request<void>('POST', '/api/ratings', { url, rating }),
  getPreferenceProfile: () =>
    request<PreferenceProfile>('GET', '/api/preferences/profile'),

  bootstrapPreferences: (interests: string) =>
    request<{
      ok: boolean;
      high_keywords: string[];
      medium_keywords: string[];
      dislikes: string[];
      synonyms: Record<string, string[]>;
      profile_summary: string;
    }>('POST', '/api/preferences/bootstrap', { interests }),

  // Ranking weights (admin-tunable)
  getRankingWeights: () =>
    request<RankingWeights>('GET', '/api/preferences/weights'),
  saveRankingWeights: (data: Partial<RankingWeights>) =>
    request<void>('PUT', '/api/preferences/weights', data),

  // Sources
  listSources: () => request<Source[]>('GET', '/api/sources'),
  addSource: (data: FormData) =>
    request<{ ok: boolean }>('POST', '/api/sources', data),
  updateSource: (id: number, data: FormData) =>
    request<{ ok: boolean }>('PUT', `/api/sources/${id}`, data),
  deleteSource: (id: number) =>
    request<void>('DELETE', `/api/sources/${id}`),
  toggleSource: (id: number, enabled: boolean) =>
    request<{ ok: boolean }>(
      'PATCH',
      `/api/sources/${id}/toggle`,
      { enabled },
    ),
  importOpml: (data: FormData) =>
    request<{ added: number }>('POST', '/api/sources/import-opml', data),
  exportOpmlUrl: () => '/api/sources/export.opml',

  // Provider endpoints and active provider
  getProviders: () => request<ProvidersConfig>('GET', '/api/config/providers'),
  saveProviders: (data: {
    active_provider: string;
    endpoints: Record<string, { base_url: string }>;
    openrouter_pick_cheapest: boolean;
  }) => request<void>('PUT', '/api/config/providers', data),

  // LLM model and reasoning settings
  getLlmConfig: () => request<LlmConfig>('GET', '/api/config/llm'),
  saveLlmConfig: (data: Partial<LlmConfig>) =>
    request<void>('PUT', '/api/config/llm', data),
  pullOllamaModel: (model: string) =>
    request<{ message: string }>(
      'POST',
      '/api/config/llm/ollama/pull',
      { model },
    ),
  deleteOllamaModel: (model: string) =>
    request<{ message: string }>(
      'POST',
      '/api/config/llm/ollama/delete',
      { model },
    ),

  // API keys
  listKeys: () => request<ApiKey[]>('GET', '/api/config/keys'),
  saveKey: (service: string, key_value: string) =>
    request<void>('POST', '/api/config/keys', { service, key_value }),
  deleteKey: (service: string) =>
    request<void>('DELETE', `/api/config/keys/${service}`),

  // Budget
  getBudget: () => request<BudgetData>('GET', '/api/config/budget'),
  getBudgetLimits: () =>
    request<BudgetLimits>('GET', '/api/config/budget-limits'),
  saveBudgetLimits: (data: BudgetLimits) =>
    request<void>('PUT', '/api/config/budget-limits', data),

  // Advanced network settings
  getNetworkConfig: () =>
    request<NetworkConfig>('GET', '/api/config/network'),
  saveNetworkConfig: (data: {
    enabled: boolean;
    proxy_url?: string;
    bypass_hosts: string;
  }) =>
    request<NetworkConfig & { ok: boolean }>(
      'PUT',
      '/api/config/network',
      data,
    ),
  testNetwork: (data: {
    enabled: boolean;
    proxy_url?: string;
    bypass_hosts: string;
  }) =>
    request<NetworkTestResult>('POST', '/api/config/network/test', data),

  // Scheduler
  getSchedulerStatus: () =>
    request<SchedulerStatus>('GET', '/api/scheduler/status'),

  // Schedule config
  getScheduleConfig: () =>
    request<ScheduleConfig>('GET', '/api/config/schedule'),
  saveScheduleConfig: (payload: { times?: string[]; enabled?: boolean; timezone?: string }) =>
    request<{ ok: boolean }>('PUT', '/api/config/schedule', payload),

  // Digest pipeline settings
  getDigestConfig: () =>
    request<DigestConfig>('GET', '/api/config/digest'),
  saveDigestConfig: (data: Partial<DigestConfig>) =>
    request<void>('PUT', '/api/config/digest', data),

  // Security
  getPasswordInfo: () =>
    request<PasswordInfo>('GET', '/api/config/password-info'),
  changePassword: (current_password: string, new_password: string) =>
    request<void>('PUT', '/api/config/password', {
      current_password,
      new_password,
    }),

  // Feed token
  getFeedToken: () =>
    request<FeedTokenInfo>('GET', '/api/config/feed-token'),
  generateFeedToken: () =>
    request<FeedTokenInfo>('POST', '/api/config/feed-token'),
  revokeFeedToken: () =>
    request<void>('DELETE', '/api/config/feed-token'),

  listLogs: () => request<RunLogSummary[]>('GET', '/api/logs'),
  getLog: (id: number) => request<RunLog | null>('GET', `/api/logs/${id}`),
  getLatestLog: () => request<RunLog | null>('GET', '/api/logs/latest'),

  // Read Later
  getReadLaterItems: () =>
    request<{ items: ReadLaterItem[] }>('GET', '/api/read-later'),
  getReadLaterUrls: () =>
    request<{ urls: string[] }>('GET', '/api/read-later/urls'),
  saveReadLater: (item: DigestItem) =>
    request<void>('POST', '/api/read-later', item),
  removeReadLater: (url: string) =>
    request<void>('DELETE', '/api/read-later', { url }),

  // Starred (permanent saves)
  getStarredItems: () =>
    request<{ items: StarredItem[] }>('GET', '/api/starred'),
  getStarredUrls: () =>
    request<{ urls: string[] }>('GET', '/api/starred/urls'),
  starItem: (item: DigestItem) =>
    request<void>('POST', '/api/starred', item),
  unstarItem: (url: string) =>
    request<void>('DELETE', '/api/starred', { url }),
};
