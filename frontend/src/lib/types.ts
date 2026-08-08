/** All shared TypeScript interfaces for Elpis UI. */

/**
 * Per-signal breakdown of how an article's preference_score was composed.
 * All values are signed floats (positive = good, negative = penalised).
 */
export interface ScoreBreakdown {
  keyword_high: number;
  keyword_negative: number;
  keyword_medium: number;
  term_overlap: number;
  bigram_overlap: number;
  tfidf_cosine: number;
  category: number;
  source: number;
  implicit_content: number;
  implicit_category: number;
  implicit_source: number;
  synonym_boost: number;
  /** Cosine similarity to the decay-weighted embedding centroid. */
  embedding_similarity: number;
  /** Overlap with LLM-extracted topic profile. */
  topic_score: number;
  /** Blended score component from the LLM reranker. */
  llm_rerank: number;
  /** Human-readable reason from the LLM reranker (may be absent). */
  llm_reason?: string;
}

export interface DigestItem {
  url: string;
  title: string;
  summary: string;
  /** One-sentence summary produced by the LLM structured output. */
  tldr?: string;
  /** Bullet-point takeaways produced by the LLM structured output. */
  key_takeaways?: string[];
  source: string;
  category: string;
  kind: string;
  published_at?: string;
  /** Saved star rating (1-5) or null/undefined when not yet rated. */
  rating?: number | null;
  /** OG or media thumbnail URL extracted during collection, if available. */
  image_url?: string;
  /** Total preference score used for ranking (higher = ranked higher). */
  preference_score?: number;
  /** Per-signal breakdown of the preference_score. */
  score_breakdown?: ScoreBreakdown;
  /** LLM-extracted semantic topics (kebab-case). */
  topics?: string[];
  /** Named entities (people, orgs, products) mentioned. */
  entities?: string[];
  /** Novelty score 1-5 (how surprising vs mainstream). */
  novelty?: number;
  /** One-sentence relevance note for this reader. */
  relevance_to_you?: string;
  /** True when the article matched a per-source highlight keyword rule. */
  highlighted?: boolean;
}

export interface DigestEntry {
  id: number;
  created_at: string;
}

export interface DigestStats {
  articles_count?: number;
  /** Number of collected article candidates before filtering. */
  collected_articles_count?: number;
  /** Number of candidates remaining after filtering. */
  filtered_articles_count?: number;
  /** Number of ranked candidates considered for final selection. */
  candidate_count?: number;
  /** Compatibility aliases retained in persisted run statistics. */
  ranked_candidate_count?: number;
  eligible_candidate_count?: number;
  /** Persisted ranked candidates; public responses may omit score evidence. */
  candidate_items?: CandidateItem[];
  model?: string;
  processing_time?: string;
}

export interface DigestMeta extends DigestStats {
  id: number;
  created_at: string;
}

export interface CandidateScoreBreakdown {
  [signal: string]: number | undefined;
  keyword_high?: number;
  keyword_negative?: number;
  keyword_medium?: number;
  term_overlap?: number;
  bigram_overlap?: number;
  tfidf_cosine?: number;
  category?: number;
  source?: number;
  implicit_content?: number;
  implicit_category?: number;
  implicit_source?: number;
  synonym_boost?: number;
  embedding_similarity?: number;
  topic_score?: number;
  llm_rerank?: number;
}

export interface CandidateEvidence {
  matched_terms: string[];
  title_matches: string[];
  context_matches: string[];
  relevance_reason: string;
  selected: boolean;
}

/** A sanitized ranked candidate. It is never an unpublished article reader payload. */
export interface CandidateItem {
  rank: number;
  url: string;
  title: string;
  source: string;
  category: string;
  kind: string;
  published_at?: string;
  excerpt: string;
  preference_score: number;
  score_breakdown: CandidateScoreBreakdown;
  evidence: CandidateEvidence;
}

export interface CandidatePage {
  candidates: CandidateItem[];
  page: number;
  limit: number;
  total?: number;
  has_more?: boolean;
  next_page?: number | null;
}

export interface DiscoveryItem {
  url: string;
  title: string;
  snippet: string;
  source: string;
  category: string;
  published_at?: string;
  provider?: string;
}

export interface DiscoveryPage {
  results: DiscoveryItem[];
  /** Some API versions include the same normalized rows under `items`. */
  items?: DiscoveryItem[];
  query: string;
  page: number;
  limit: number;
  total?: number;
  has_more?: boolean;
  next_page?: number | null;
}

export type MonitorScope =
  | 'general_discovery'
  | 'configured_feeds'
  | 'both';

export type MonitorState = 'new' | 'seen' | 'dismissed';

export interface MonitorQuery {
  id: number;
  question: string;
  search_query: string;
  scope: MonitorScope;
  enabled: boolean;
  cadence_minutes: number;
  include_keywords: string[];
  exclude_keywords: string[];
  category: string;
  language: string;
  country: string;
  max_items: number;
  status?: string;
  last_checked_at?: string | null;
  last_success_at?: string | null;
  next_check_at?: string | null;
  last_error?: string | null;
  new_count?: number;
  created_at?: string;
  updated_at?: string;
}

export interface MonitorEvidence {
  matched_terms?: string[];
  provider?: string;
  freshness?: number;
  [key: string]: string | number | string[] | undefined;
}

export interface MonitorResult {
  id: number;
  monitor_id: number;
  url: string;
  title: string;
  snippet: string;
  source: string;
  category: string;
  published_at?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  relevance_score: number;
  evidence: MonitorEvidence;
  state: MonitorState;
}

export interface MonitorResultsPage {
  monitor_id?: number;
  results: MonitorResult[];
  /** The backend also returns `items` for clients that prefer that name. */
  items?: MonitorResult[];
  page: number;
  limit: number;
  total?: number;
  has_more?: boolean;
  next_page?: number | null;
  new_count?: number;
}

export interface MonitorCheckResponse {
  monitor: MonitorQuery;
  results: MonitorResult[];
  new_count: number;
  error?: string | null;
}

export interface MonitorQueryInput {
  question: string;
  search_query: string;
  scope: MonitorScope;
  enabled: boolean;
  cadence_minutes: number;
  include_keywords: string[];
  exclude_keywords: string[];
  category: string;
  language: string;
  country: string;
  max_items: number;
}

export interface DigestDetail {
  meta: DigestMeta;
  items: DigestItem[];
  /** Authenticated-only full ranked candidates, when persisted by the pipeline. */
  candidates?: CandidateItem[];
}

export interface ArticleContent {
  url: string;
  title: string;
  content: string;
  source: string;
  category: string;
  published_at?: string;
}

export interface Source {
  id: number;
  type: string;
  name: string;
  url: string;
  category: string;
  priority: number;
  /** 1 = enabled, 0 = disabled. Defaults to 1 for newly-added sources. */
  enabled: number;
  /** Type-specific source settings stored by the backend as JSON text. */
  extra_json?: string;
  last_status?: string;
  last_item_count?: number;
  last_checked_at?: string;
  last_error?: string;
}
export interface SourceDiscoveryHealth {
  status: string;
  entry_count?: number;
  error?: string;
}

export interface SourceDiscoveryEvidence {
  feed_verified?: boolean;
  verification?: string;
  matched_terms?: string[];
  article_count?: number;
  score_basis?: Record<string, number>;
  [key: string]: unknown;
}

export interface SourceDiscoveryCandidate {
  name: string;
  source_type: 'rss' | 'google_news';
  url: string;
  feed_url: string | null;
  query: string | null;
  category: string;
  description: string;
  score: number;
  evidence: SourceDiscoveryEvidence;
  health: SourceDiscoveryHealth;
  existing: boolean;
}

export interface SourceDiscoveryPage {
  query: string;
  candidates: SourceDiscoveryCandidate[];
  page: number;
  limit: number;
  has_more: boolean;
}

export interface RatingArticle {
  url: string;
  title: string;
  category: string;
  rating?: number | null;
}

export type ReasoningEffort =
  | 'none'
  | 'minimal'
  | 'low'
  | 'medium'
  | 'high'
  | 'xhigh';

export interface LlmConfig {
  /** Active provider selected on the Providers page. */
  provider: string;
  /** Active provider's model identifier. */
  model: string;
  reasoning_effort: ReasoningEffort;
  thinking_enabled: boolean;
  thinking_budget_tokens: number;
}

export interface ProviderDefinition {
  id: string;
  label: string;
  description: string;
  litellm_provider: string;
  base_url: string;
  default_base_url: string;
  supports_base_url: boolean;
  requires_api_key: boolean;
  api_key_configured: boolean;
  key_preview: string;
}

export interface ProvidersConfig {
  active_provider: string;
  providers: ProviderDefinition[];
  openrouter_pick_cheapest: boolean;
  cheapest_model_id?: string | null;
  ollama_host: string;
  ollama_models: string[];
  ollama_reachable: boolean;
}

export interface ApiKey {
  service: string;
  key_preview: string;
}

export type JobState = 'idle' | 'running' | 'completed' | 'failed';

export interface Job {
  state: JobState;
  run_id?: number | null;
  message: string;
  started_at?: string | null;
  finished_at?: string | null;
  stats?: Record<string, unknown> | null;
  digest_id?: number | null;
  post_display?: string;
  error?: string | null;
  log_id?: number | null;
}

export type DigestRunState = 'running' | 'completed' | 'failed';

export interface DigestRunSummary {
  id: number;
  state: DigestRunState;
  message: string;
  started_at: string;
  finished_at: string | null;
  digest_id: number | null;
  stats: Record<string, unknown>;
  error: string;
  dry_run: boolean;
  skip_deploy: boolean;
  log_id: number | null;
}

export interface PreferenceTerm {
  term: string;
  score: number;
}

export interface PreferenceCategoryScore {
  category: string;
  score: number;
}

export interface PreferenceSourceScore {
  source: string;
  score: number;
}

export interface PreferenceProfile {
  rating_count: number;
  earliest_rating: string;
  latest_rating: string;
  min_ratings_threshold: number;
  learning_active: boolean;
  /** Distribution of star ratings: keys are '1'-'5', values are counts. */
  rating_distribution: Record<string, number>;
  /** Number of articles that were marked as read (implicit positive signal). */
  implicit_read_count: number;
  /** Number of articles ever saved for later, including processed ones (implicit strong positive). */
  implicit_saved_count: number;
  /** Number of articles the user has dismissed (implicit negative signal). */
  implicit_dismissed_count: number;
  /** Whether implicit learning is active (implicit_signal_weight > 0). */
  implicit_learning_active: boolean;
  /** How much weight the oldest rating carries after decay (0-1). */
  oldest_rating_decay: number;
  /** Decay half-life in days used for this profile. */
  decay_half_life_days: number;
  top_liked_terms: PreferenceTerm[];
  top_disliked_terms: PreferenceTerm[];
  top_liked_bigrams: PreferenceTerm[];
  top_disliked_bigrams: PreferenceTerm[];
  category_preferences: PreferenceCategoryScore[];
  source_preferences: PreferenceSourceScore[];
  /** True when an embedding profile centroid has been built. */
  embedding_active?: boolean;
  /** Top semantic topics extracted from liked articles. */
  top_liked_topics?: PreferenceTerm[];
  /** Top semantic topics extracted from disliked articles. */
  top_disliked_topics?: PreferenceTerm[];
}

export interface RankingWeights {
  tfidf_preference_weight: number;
  category_preference_weight: number;
  source_preference_weight: number;
  implicit_signal_weight: number;
  rating_decay_half_life_days: number;
  min_ratings_for_learning: number;
  /** Weight of the embedding cosine-similarity signal. */
  embedding_preference_weight: number;
  /** Embedding provider selection. */
  embedding_provider: 'off' | 'ollama' | 'openrouter' | 'openai';
  /** Model used to generate embeddings. */
  embedding_model: string;
  /** Weight of the LLM topic overlap signal. */
  topic_score_weight: number;
  /** Enable LLM reranker pass. */
  llm_rerank_enabled: boolean;
  /** Model used for reranking (empty = use summarizer model). */
  llm_rerank_model: string;
  /** Number of top candidates sent to the reranker. */
  llm_rerank_top_k: number;
  /** Blend weight between LLM score and classical score (0-1). */
  llm_rerank_blend: number;
  /** Semantic dedup: use embeddings to collapse same-story articles. Only active when embedding_provider != "off". */
  semantic_dedup_enabled: boolean;
  /** Cosine similarity threshold above which two articles are treated as the same story (0.5-1.0). */
  semantic_dedup_threshold: number;
  /** Free-text reader profile narrative fed to the LLM reranker. */
  profile_summary: string;
  /** Preset label for the UI selector. Does not affect the engine directly. */
  personalization_mode: 'off' | 'balanced' | 'aggressive' | 'custom';
  /** Category gate: learned score at/below which a category is dropped entirely (-5 to 0). */
  category_exclude_threshold: number;
  /** Category gate: learned score at/below which a category is demoted (-5 to 0). */
  category_demote_threshold: number;
  /** Category gate: max articles kept from a demoted category (0-50). */
  category_demote_cap: number;
  /** Category gate: minimum ratings a category needs before it can be gated (1-1000). */
  category_min_ratings: number;
}

export interface OpenRouterUsage {
  usage_daily: number;
  usage_weekly: number;
  usage_monthly: number;
  limit: number | null;
  limit_remaining: number | null;
  is_free_tier: boolean;
}

export interface ModelSpend {
  model: string;
  total_usd: number;
  requests: number;
}

export interface DigestCost {
  digest_id: number;
  created_at: string;
  cost_usd: number;
  articles: number;
}

export interface LocalBudget {
  today_usd: number;
  month_usd: number;
  daily_limit_usd: number;
  monthly_limit_usd: number;
  /** Average LLM cost per digest run across all time. */
  avg_cost_per_digest_usd: number;
  by_model: ModelSpend[];
  recent_digests: DigestCost[];
}

export interface BudgetData {
  /** Present when provider is openrouter and API key is set. */
  openrouter: OpenRouterUsage | null;
  local: LocalBudget;
}

export interface SchedulerStatus {
  enabled: boolean;
  next_run_utc: string | null;
  schedule_times: string[];
  timezone: string;
}

export interface ScheduleConfig {
  times: string[];
  enabled: boolean;
  next_run_utc: string | null;
  timezone: string;
}

export interface DigestConfig {
  max_articles_per_digest: number;
  /** Number of published issues retained in the public archive. */
  digest_history_limit: number;
  balance_digest_categories: boolean;
  max_articles_per_category: number;
  max_article_age_hours: number;
  preferred_languages: string[];
  exclude_keywords: string[];
  /** Topics the reader never wants to read about (soft negative ranking signal). */
  disliked_keywords: string[];
  max_key_takeaways: number;
  max_summary_paragraphs: number;
  /** ISO 639-1 code for the digest output language, or "source" to match
   *  each article's detected language. Default "en". */
  digest_language: string;
  youtube_transcription_enabled: boolean;
  youtube_transcription_model: string;
  youtube_transcription_max_duration: number;
}

export interface BudgetLimits {
  daily_budget_usd: number;
  monthly_budget_usd: number;
}

export interface PasswordInfo {
  /** 'default' | 'env' | 'db' */
  source: string;
  using_default: boolean;
}

export interface FeedTokenInfo {
  exists: boolean;
  token: string | null;
  feed_url: string | null;
}


export interface NetworkConfig {
  enabled: boolean;
  proxy_configured: boolean;
  proxy_url_display: string | null;
  proxy_source: 'database' | 'environment' | 'disabled';
  bypass_hosts: string[];
  youtube_proxy_override: boolean;
}

export interface NetworkTestResult {
  ok: boolean;
  status_code?: number;
  elapsed_ms?: number;
  proxy_used: boolean;
  target?: string;
  error?: string;
}
/**
 * A digest item that the user has saved to the read-later list.
 * Mirrors DigestItem plus a `saved_at` timestamp set when it was bookmarked.
 */
export interface ReadLaterItem extends DigestItem {
  saved_at: string;
}

/**
 * A digest item the user has starred for permanent keeping.
 * Mirrors DigestItem plus a `starred_at` timestamp set when it was starred.
 */
export interface StarredItem extends DigestItem {
  starred_at: string;
}

export interface RunLogSummary {
  id: number;
  run_id: number | null;
  digest_id: number | null;
  created_at: string;
  log_preview: string;
  status: DigestRunState | null;
}

export interface RunLog {
  id: number;
  run_id: number | null;
  digest_id: number | null;
  created_at: string;
  log_text: string;
  status: DigestRunState | null;
}
