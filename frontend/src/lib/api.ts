import type {
  ApiKey,
  ArticleContent,
  BudgetData,
  BudgetLimits,
  CandidatePage,
  DiscoveryPage,
  DigestConfig,
  DigestDetail,
  DigestEntry,
  DigestRunSummary,
  DigestItem,
  FeedTokenInfo,
  Job,
  LlmConfig,
  MonitorQuery,
  MonitorCheckResponse,
  MonitorQueryInput,
  MonitorResult,
  MonitorResultsPage,
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
  SourceDiscoveryPage,
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

type CandidateEnvelope = {
  candidates?: CandidatePage['candidates'];
  items?: CandidatePage['candidates'];
  page?: number;
  limit?: number;
  total?: number;
  has_more?: boolean;
  next_page?: number | null;
};

type DiscoveryEnvelope = {
  items: DiscoveryPage['results'];
  query?: string;
  page?: number;
  limit?: number;
  total?: number;
  has_more?: boolean;
  next_page?: number | null;
};

type MonitorResultsEnvelope = {
  monitor_id?: number;
  items: MonitorResultsPage['results'];
  page?: number;
  limit?: number;
  total?: number;
  has_more?: boolean;
  next_page?: number | null;
  new_count?: number;
};

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
  // Ranked candidate publication (authenticated readers only)
  listCandidates: (options: {
    digestId?: number;
    page?: number;
    limit?: number;
  } = {}) => {
    const query = new URLSearchParams();
    if (options.digestId != null) query.set('digest_id', String(options.digestId));
    if (options.page != null) query.set('page', String(options.page));
    if (options.limit != null) query.set('limit', String(options.limit));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<CandidatePage['candidates'] | CandidateEnvelope>(
      'GET',
      `/api/candidates${suffix}`,
    ).then((payload): CandidatePage => {
      const page = options.page ?? 1;
      if (Array.isArray(payload)) {
        const limit = options.limit ?? payload.length;
        const start = options.limit == null ? 0 : (page - 1) * limit;
        const candidates = payload.slice(start, start + limit);
        return {
          candidates,
          page,
          limit,
          total: payload.length,
          has_more: start + limit < payload.length,
          next_page: start + limit < payload.length ? page + 1 : null,
        };
      }
      const rawCandidates = payload.candidates ?? payload.items ?? [];
      const serverPaginated =
        'page' in payload ||
        'limit' in payload ||
        'has_more' in payload ||
        'next_page' in payload ||
        'total' in payload;
      const limit = payload.limit ?? options.limit ?? rawCandidates.length;
      const start = !serverPaginated && options.limit != null ? (page - 1) * limit : 0;
      const candidates = !serverPaginated
        ? rawCandidates.slice(start, start + limit)
        : rawCandidates;
      const total = payload.total ?? (!serverPaginated ? rawCandidates.length : undefined);
      return {
        ...payload,
        candidates,
        page: payload.page ?? page,
        limit,
        total,
        has_more: payload.has_more ?? (!serverPaginated && start + limit < rawCandidates.length),
        next_page: payload.next_page ?? (!serverPaginated && start + limit < rawCandidates.length ? page + 1 : null),
      };
    });
  },

  // General discovery is intentionally separate from digest collection/ranking.
  discover: (options: {
    query: string;
    page?: number;
    limit?: number;
    language?: string;
    country?: string;
    maxItems?: number;
  }) => {
    const query = new URLSearchParams();
    query.set('q', options.query);
    if (options.page != null) query.set('page', String(options.page));
    if (options.limit != null) query.set('limit', String(options.limit));
    if (options.language) query.set('language', options.language);
    if (options.country) query.set('country', options.country);
    if (options.maxItems != null || options.limit != null) {
      query.set('max_items', String(options.maxItems ?? options.limit));
    }
    return request<DiscoveryPage | DiscoveryPage['results'] | DiscoveryEnvelope>(
      'GET',
      `/api/discover?${query.toString()}`,
      undefined,
      { dispatchAuthExpired: false },
    ).then((payload): DiscoveryPage => {
      if (Array.isArray(payload)) {
        const limit = options.limit ?? payload.length;
        const page = options.page ?? 1;
        return {
          results: payload,
          query: options.query,
          page,
          limit,
          has_more: payload.length >= limit,
          next_page: payload.length >= limit ? page + 1 : null,
        };
      }
      const results = 'results' in payload ? payload.results : payload.items;
      const paginated =
        'page' in payload ||
        'limit' in payload ||
        'has_more' in payload ||
        'next_page' in payload ||
        'total' in payload;
      return {
        ...payload,
        results: results ?? [],
        query: ('query' in payload && payload.query) || options.query,
        page: paginated && 'page' in payload && payload.page ? payload.page : options.page || 1,
        limit: paginated && 'limit' in payload && payload.limit
          ? payload.limit
          : results?.length || 0,
        has_more: paginated && 'has_more' in payload ? payload.has_more : false,
      };
    });
  },

  // Monitoring query management and reader-facing result history.
  listMonitoring: () =>
    request<MonitorQuery[] | { queries: MonitorQuery[] }>(
      'GET',
      '/api/monitoring',
    ).then((payload) => (Array.isArray(payload) ? payload : payload.queries ?? [])),
  getMonitoring: (id: number) =>
    request<MonitorQuery>('GET', `/api/monitoring/${id}`),
  createMonitoring: (input: MonitorQueryInput) =>
    request<MonitorQuery>('POST', '/api/monitoring', input),
  updateMonitoring: (id: number, input: Partial<MonitorQueryInput>) =>
    request<MonitorQuery>('PUT', `/api/monitoring/${id}`, input),
  deleteMonitoring: (id: number) =>
    request<{ ok: boolean }>('DELETE', `/api/monitoring/${id}`),
  checkMonitoring: (id: number) =>
    request<MonitorQuery | MonitorCheckResponse>(
      'POST',
      `/api/monitoring/${id}/check`,
    ).then((payload) => ('monitor' in payload ? payload.monitor : payload)),
  listMonitoringResults: (
    id: number,
    options: { page?: number; limit?: number } = {},
  ) => {
    const query = new URLSearchParams();
    if (options.page != null) query.set('page', String(options.page));
    if (options.limit != null) query.set('limit', String(options.limit));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request<
      MonitorResultsPage | MonitorResultsPage['results'] | MonitorResultsEnvelope
    >(
      'GET',
      `/api/monitoring/${id}/results${suffix}`,
    ).then((payload): MonitorResultsPage => {
      if (Array.isArray(payload)) {
        const limit = options.limit ?? payload.length;
        const page = options.page ?? 1;
        return {
          results: payload,
          page,
          limit,
          has_more: payload.length >= limit,
          next_page: payload.length >= limit ? page + 1 : null,
        };
      }
      const results = 'results' in payload ? payload.results : payload.items;
      return {
        ...payload,
        results: results ?? [],
        page: ('page' in payload && payload.page) || options.page || 1,
        limit: ('limit' in payload && payload.limit) || options.limit || results?.length || 0,
      };
    });
  },
  markMonitoringResultSeen: (monitorId: number, resultId: number) =>
    request<MonitorResult>(
      'POST',
      `/api/monitoring/${monitorId}/results/${resultId}/seen`,
    ),
  dismissMonitoringResult: (monitorId: number, resultId: number) =>
    request<MonitorResult>(
      'POST',
      `/api/monitoring/${monitorId}/results/${resultId}/dismiss`,
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
  discoverSources: (options: {
    query: string;
    page?: number;
    limit?: number;
    language?: string;
    country?: string;
    maxItems?: number;
  }) => {
    const params = new URLSearchParams();
    params.set('q', options.query);
    if (options.page != null) params.set('page', String(options.page));
    if (options.limit != null) params.set('limit', String(options.limit));
    if (options.language) params.set('language', options.language);
    if (options.country) params.set('country', options.country);
    if (options.maxItems != null) {
      params.set('max_items', String(options.maxItems));
    }
    return request<SourceDiscoveryPage>(
      'GET',
      `/api/sources/discover?${params.toString()}`,
    );
  },
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
