import { Fragment } from 'preact';
import { useState, useEffect, useMemo } from 'preact/hooks';
import { api } from '../../lib/api';
import type { Source } from '../../lib/types';
import { Badge, kindVariant } from '../../components/Badge';
import { Button } from '../../components/Button';
import { Card, CardHeader } from '../../components/Card';
import { EmptyState } from '../../components/EmptyState';
import { Spinner } from '../../components/Spinner';
import { CategoryCombobox } from '../../components/CategoryCombobox';
import { formatDigestLabel } from '../../lib/dates';
import { itunesPodcastSearchUrl } from '../../lib/externalUrls';

/** Shared Tailwind class string for text inputs and selects. */
const inputCls =
  'w-full px-3 py-2 text-sm bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500';

const PRIORITY_LABELS: Record<number, string> = {
  1: 'High',
  2: 'Normal',
  3: 'Low',
  4: 'Lower',
  5: 'Lowest',
};

const PRIORITY_COLORS: Record<number, string> = {
  1: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  2: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  3: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  4: 'bg-blue-50 text-blue-500 dark:bg-blue-900/20 dark:text-blue-500',
  5: 'bg-slate-50 text-slate-400 dark:bg-slate-800/50 dark:text-slate-500',
};

interface ITunesResult {
  collectionName: string;
  artistName: string;
  feedUrl: string;
  artworkUrl100: string;
}

type SourceExtra = Record<string, string | number | boolean | null | string[]>;

function parseSourceExtra(source: Source): SourceExtra {
  if (!source.extra_json) {
    return {};
  }
  try {
    const parsed = JSON.parse(source.extra_json) as unknown;
    return parsed != null && typeof parsed === 'object'
      ? (parsed as SourceExtra)
      : {};
  } catch {
    return {};
  }
}

function extraText(
  extra: SourceExtra,
  key: string,
  fallback = '',
): string {
  const value = extra[key];
  return value == null ? fallback : String(value);
}

function extraNumber(
  extra: SourceExtra,
  key: string,
  fallback: number,
): number {
  const value = Number(extra[key]);
  return Number.isFinite(value) ? value : fallback;
}

async function searchITunesPodcasts(query: string): Promise<ITunesResult[]> {
  const res = await fetch(itunesPodcastSearchUrl(query));
  if (!res.ok) {
    throw new Error(`Podcast search failed (${res.status})`);
  }
  const data = (await res.json()) as { results?: unknown[] };
  return (data.results ?? []) as ITunesResult[];
}

export function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(
    null,
  );
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editLoadingId, setEditLoadingId] = useState<number | null>(
    null,
  );
  const [addLoading, setAddLoading] = useState(false);
  const [opmlLoading, setOpmlLoading] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [addFormOpen, setAddFormOpen] = useState(false);
  const [sourceType, setSourceType] = useState('rss');
  const [gnewsQuery, setGnewsQuery] = useState('');
  const [podcastQuery, setPodcastQuery] = useState('');
  const [podcastResults, setPodcastResults] = useState<ITunesResult[]>([]);
  const [podcastSearching, setPodcastSearching] = useState(false);
  const [podcastFeedUrl, setPodcastFeedUrl] = useState('');
  const [podcastName, setPodcastName] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(
    null,
  );

  useEffect(() => {
    load();
  }, []);

  function load() {
    setLoading(true);
    api
      .listSources()
      .then(setSources)
      .catch((e: unknown) => {
        setError(
          e instanceof Error ? e.message : 'Failed to load sources.',
        );
      })
      .finally(() => setLoading(false));
  }

  function showFlash(msg: string) {
    setFlash(msg);
    setTimeout(() => setFlash(null), 4000);
  }

  async function handleAdd(e: Event) {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const data = new FormData(form);
    setAddLoading(true);
    try {
      await api.addSource(data);
      form.reset();
      setSourceType('rss');
      setGnewsQuery('');
      setPodcastQuery('');
      setPodcastResults([]);
      setPodcastFeedUrl('');
      setPodcastName('');
      setAddFormOpen(false);
      load();
      showFlash('Source added.');
    } catch (err) {
      showFlash(
        err instanceof Error ? err.message : 'Failed to add source.',
      );
    } finally {
      setAddLoading(false);
    }
  }

  async function handleDelete(id: number) {
    if (confirmDeleteId !== id) {
      setConfirmDeleteId(id);
      setTimeout(() => setConfirmDeleteId(null), 3000);
      return;
    }
    setDeletingId(id);
    setConfirmDeleteId(null);
    try {
      await api.deleteSource(id);
      setSources((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      showFlash(
        err instanceof Error
          ? err.message
          : 'Failed to delete source.',
      );
    } finally {
      setDeletingId(null);
    }
  }

  async function handleEdit(e: Event, source: Source) {
    e.preventDefault();
    const form = e.currentTarget as HTMLFormElement;
    const data = new FormData(form);
    setEditLoadingId(source.id);
    try {
      await api.updateSource(source.id, data);
      setEditingId(null);
      load();
      showFlash('Source updated.');
    } catch (err) {
      showFlash(
        err instanceof Error ? err.message : 'Failed to update source.',
      );
    } finally {
      setEditLoadingId(null);
    }
  }

  async function handleToggle(id: number, currentEnabled: number) {
    const next = currentEnabled === 0;
    // Optimistically update UI before the request completes.
    setSources((prev) =>
      prev.map((s) =>
        s.id === id ? { ...s, enabled: next ? 1 : 0 } : s,
      ),
    );
    setTogglingId(id);
    try {
      await api.toggleSource(id, next);
    } catch (err) {
      // Revert on failure.
      setSources((prev) =>
        prev.map((s) =>
          s.id === id ? { ...s, enabled: currentEnabled } : s,
        ),
      );
      showFlash(
        err instanceof Error
          ? err.message
          : 'Failed to toggle source.',
      );
    } finally {
      setTogglingId(null);
    }
  }

  async function handleImportOpml(e: Event) {
    const input = e.target as HTMLInputElement;
    if (!input.files?.[0]) {
      return;
    }
    const data = new FormData();
    data.append('file', input.files[0]);
    setOpmlLoading(true);
    try {
      const res = await api.importOpml(data);
      input.value = '';
      load();
      showFlash(
        `Imported ${res.added} source${res.added !== 1 ? 's' : ''}.`,
      );
    } catch (err) {
      showFlash(
        err instanceof Error ? err.message : 'OPML import failed.',
      );
    } finally {
      setOpmlLoading(false);
    }
  }

  async function searchPodcasts() {
    if (!podcastQuery.trim()) return;
    setPodcastSearching(true);
    setPodcastResults([]);
    try {
      setPodcastResults(await searchITunesPodcasts(podcastQuery));
    } catch {
      // leave results empty on error
    } finally {
      setPodcastSearching(false);
    }
  }

  function selectPodcast(result: ITunesResult) {
    setPodcastFeedUrl(result.feedUrl ?? '');
    setPodcastName(result.collectionName ?? '');
    setPodcastResults([]);
    setPodcastQuery(result.collectionName ?? '');
  }

  /** Unique categories derived from current sources. */
  const categories = useMemo(() => {
    const cats = new Set(sources.map((s) => s.category));
    return Array.from(cats).sort();
  }, [sources]);

  /** Sources filtered by search query and active category. */
  const filteredSources = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return sources.filter((s) => {
      if (
        activeCategory &&
        s.category !== activeCategory
      ) {
        return false;
      }
      if (!q) {
        return true;
      }
      return (
        s.name.toLowerCase().includes(q) ||
        s.url.toLowerCase().includes(q) ||
        s.category.toLowerCase().includes(q)
      );
    });
  }, [sources, searchQuery, activeCategory]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner
          size="lg"
          className="text-blue-600 dark:text-blue-400"
        />
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400 p-4">
        {error}
      </p>
    );
  }

  return (
    <div className="space-y-5">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Sources
          </h1>
          {sources.length > 0 && (
            <span className="inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
              {sources.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setAddFormOpen((o) => !o)}
          >
            {addFormOpen ? 'Cancel' : 'Add source'}
          </Button>
        </div>
      </div>
      <p className="text-sm text-slate-500 dark:text-slate-400 -mt-3">
        RSS, YouTube, website monitors, Google News searches, Hacker News, Reddit, GitHub Releases, and Podcasts.
      </p>

      {flash && (
        <div className="px-4 py-3 text-sm rounded-lg bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
          {flash}
        </div>
      )}

      {/* Collapsible add-source form */}
      {addFormOpen && (
        <Card>
          <CardHeader title="Add source" />
          <form
            onSubmit={handleAdd}
            className="grid grid-cols-1 sm:grid-cols-2 gap-3"
          >
            {/* --- Type selector --- */}
            <Field label="Type">
              <select
                name="source_type"
                className={inputCls}
                value={sourceType}
                onChange={(e) =>
                  setSourceType(
                    (e.target as HTMLSelectElement).value,
                  )
                }
              >
                <option value="rss">RSS</option>
                <option value="youtube">YouTube</option>
                <option value="website">Website watch</option>
                <option value="google_news">Google News search</option>
                <option value="hackernews">Hacker News</option>
                <option value="reddit">Reddit</option>
                <option value="github_releases">GitHub Releases</option>
                <option value="podcast">Podcast</option>
              </select>
            </Field>

            {/* --- Name (always shown) --- */}
            <Field label="Name">
              {sourceType === 'podcast' ? (
                <input
                  name="name"
                  required
                  className={inputCls}
                  value={podcastName}
                  onInput={(e) =>
                    setPodcastName((e.target as HTMLInputElement).value)
                  }
                />
              ) : (
                <input name="name" required className={inputCls} />
              )}
            </Field>

            {/* --- URL (RSS / YouTube / Website only) --- */}
            {(sourceType === 'rss' ||
              sourceType === 'youtube' ||
              sourceType === 'website') && (
              <Field label="URL" className="sm:col-span-2">
                <input
                  name="url"
                  required
                  placeholder={
                    sourceType === 'youtube'
                      ? 'https://www.youtube.com/@channel'
                      : sourceType === 'website'
                        ? 'https://example.com/page-to-watch'
                        : 'https://example.com/feed.xml'
                  }
                  className={inputCls}
                />
                <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                  {sourceType === 'youtube'
                    ? 'Channel page URL or RSS feed URL'
                    : sourceType === 'website'
                      ? 'Page URL to monitor for changes'
                      : 'Direct RSS/Atom feed URL'}
                </span>
              </Field>
            )}

            {/* --- YouTube channel ID --- */}
            {sourceType === 'youtube' && (
              <Field
                label="YouTube channel ID"
                className="sm:col-span-2"
              >
                <input
                  name="channel_id"
                  aria-label="YouTube channel ID"
                  placeholder="UC..."
                  className={inputCls}
                />
                <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                  Found in the channel's About page or URL
                </span>
              </Field>
            )}

            {/* --- Google News search query --- */}
            {sourceType === 'google_news' && (
              <>
                <Field label="Search query" className="sm:col-span-2">
                  <input
                    name="query"
                    aria-label="Google News search query"
                    required
                    placeholder='site:reuters.com when:1d  /  "AI" intitle:release'
                    value={gnewsQuery}
                    onInput={(e) =>
                      setGnewsQuery(
                        (e.target as HTMLInputElement).value,
                      )
                    }
                    className={inputCls}
                  />
                  <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                    Supports{' '}
                    <code className="font-mono">site:</code>,{' '}
                    <code className="font-mono">when:</code>,{' '}
                    <code className="font-mono">intitle:</code>,{' '}
                    <code className="font-mono">source:</code> operators
                  </span>
                </Field>
                {gnewsQuery && (
                  <p className="sm:col-span-2 text-xs font-mono text-slate-400 dark:text-slate-500 break-all">
                    {`https://news.google.com/rss/search?q=${encodeURIComponent(gnewsQuery)}&hl=en-US&gl=US&ceid=US:en`}
                  </p>
                )}
                <Field label="Language">
                  <input
                    name="language"
                    aria-label="Google News language"
                    defaultValue="en"
                    placeholder="en"
                    className={inputCls}
                  />
                </Field>
                <Field label="Country">
                  <input
                    name="country"
                    aria-label="Google News country"
                    defaultValue="US"
                    placeholder="US"
                    className={inputCls}
                  />
                </Field>
              </>
            )}

            {/* --- Hacker News --- */}
            {sourceType === 'hackernews' && (
              <>
                <Field label="Feed">
                  <select name="hn_feed" className={inputCls} defaultValue="top">
                    <option value="top">Top stories</option>
                    <option value="best">Best stories</option>
                    <option value="new">New stories</option>
                    <option value="ask">Ask HN</option>
                    <option value="show">Show HN</option>
                  </select>
                </Field>
                <Field label="Min score">
                  <input
                    name="hn_min_score"
                    type="number"
                    defaultValue="50"
                    min="0"
                    className={inputCls}
                  />
                  <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                    Skip stories below this score
                  </span>
                </Field>
                <Field label="Max items">
                  <input
                    name="hn_max_items"
                    type="number"
                    defaultValue="20"
                    min="1"
                    max="100"
                    className={inputCls}
                  />
                </Field>
              </>
            )}

            {/* --- Reddit --- */}
            {sourceType === 'reddit' && (
              <>
                <Field label="Subreddit" className="sm:col-span-2">
                  <input
                    name="subreddit"
                  aria-label="Subreddit"
                    required
                    placeholder="netsec"
                    className={inputCls}
                  />
                  <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                    Name only, without{' '}
                    <code className="font-mono">r/</code>
                  </span>
                </Field>
                <Field label="Sort">
                  <select name="reddit_sort" className={inputCls} defaultValue="hot">
                    <option value="hot">Hot</option>
                    <option value="new">New</option>
                    <option value="top">Top</option>
                    <option value="rising">Rising</option>
                  </select>
                </Field>
                <Field label="Time filter (for Top)">
                  <select
                    name="reddit_time_filter"
                    className={inputCls}
                    defaultValue="day"
                  >
                    <option value="hour">Past hour</option>
                    <option value="day">Past 24 h</option>
                    <option value="week">Past week</option>
                    <option value="month">Past month</option>
                    <option value="year">Past year</option>
                    <option value="all">All time</option>
                  </select>
                </Field>
                <Field label="Min score">
                  <input
                    name="reddit_min_score"
                    type="number"
                    defaultValue="10"
                    min="0"
                    className={inputCls}
                  />
                </Field>
                <Field label="Max items">
                  <input
                    name="reddit_max_items"
                    type="number"
                    defaultValue="20"
                    min="1"
                    max="100"
                    className={inputCls}
                  />
                </Field>
              </>
            )}

            {/* --- GitHub Releases --- */}
            {sourceType === 'github_releases' && (
              <Field label="Repository" className="sm:col-span-2">
                <input
                  name="github_repo"
                  aria-label="GitHub repository"
                  required
                  placeholder="astral-sh/uv"
                  className={inputCls}
                />
                <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                  Format: <code className="font-mono">owner/repo</code>
                </span>
              </Field>
            )}

            {/* --- Podcast search + URL --- */}
            {sourceType === 'podcast' && (
              <>
                <div className="sm:col-span-2 space-y-2">
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      Search podcasts
                    </span>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        aria-label="Podcast search"
                        placeholder='e.g. "Darknet Diaries"'
                        value={podcastQuery}
                        onInput={(e) =>
                          setPodcastQuery(
                            (e.target as HTMLInputElement).value,
                          )
                        }
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            void searchPodcasts();
                          }
                        }}
                        className={`${inputCls} flex-1`}
                      />
                      <button
                        type="button"
                        onClick={() => void searchPodcasts()}
                        disabled={podcastSearching}
                        className="px-4 py-2 text-sm font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                      >
                        {podcastSearching ? 'Searching...' : 'Search'}
                      </button>
                    </div>
                  </div>

                  {podcastResults.length > 0 && (
                    <div className="rounded-lg border border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800 overflow-hidden">
                      {podcastResults.map((r) => (
                        <button
                          key={r.feedUrl}
                          type="button"
                          onClick={() => selectPodcast(r)}
                          className="w-full flex items-center gap-3 px-3 py-2.5 text-left bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                        >
                          {r.artworkUrl100 && (
                            <img
                              src={r.artworkUrl100}
                              alt=""
                              className="w-10 h-10 rounded-lg object-cover flex-shrink-0"
                            />
                          )}
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                              {r.collectionName}
                            </p>
                            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                              {r.artistName}
                            </p>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <Field label="Feed URL" className="sm:col-span-2">
                  <input
                    name="url"
                    aria-label="Podcast feed URL"
                    required
                    placeholder="https://feeds.example.com/podcast"
                    className={inputCls}
                    value={podcastFeedUrl}
                    onInput={(e) =>
                      setPodcastFeedUrl(
                        (e.target as HTMLInputElement).value,
                      )
                    }
                  />
                  <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                    Auto-filled from search, or paste the RSS feed URL directly
                  </span>
                </Field>
              </>
            )}

            {/* --- Category & priority (always shown) --- */}
            <Field label="Category">
              <CategoryCombobox
                name="category"
                defaultValue="General"
                options={categories}
                className={inputCls}
              />
            </Field>
            <Field label="Priority">
              <select
                name="priority"
                className={inputCls}
                defaultValue="2"
              >
                <option value="1">1 - High</option>
                <option value="2">2 - Normal</option>
                <option value="3">3 - Low</option>
                <option value="4">4 - Lower</option>
                <option value="5">5 - Lowest</option>
              </select>
            </Field>
            {(sourceType === 'rss' ||
              sourceType === 'google_news' ||
              sourceType === 'github_releases' ||
              sourceType === 'podcast') && (
              <Field label="Max items per source">
                <input
                  name="max_items"
                  type="number"
                  min="1"
                  max="200"
                  defaultValue="50"
                  className={inputCls}
                />
                <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                  Candidate entries collected before ranking (1–200)
                </span>
              </Field>
            )}

            {/* --- Filter rules --- */}
            <div className="sm:col-span-2 border-t border-slate-100 dark:border-slate-800 pt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <KeywordChipInput
                name="require_keywords"
                label="Show only if"
                hint='Only articles containing at least one of these are kept. Supports wildcards: CVE-*, GHSA-*. Leave empty to keep all articles.'
                chipColor="blue"
              />
              <KeywordChipInput
                name="hide_keywords"
                label="Hide keywords"
                hint='Articles whose title or content contains any of these are excluded. Case-insensitive, press Enter or comma to add.'
                chipColor="red"
              />
              <KeywordChipInput
                name="highlight_keywords"
                label="Highlight keywords"
                hint='Articles containing any of these get a ranking boost and a visual badge. Case-insensitive, press Enter or comma to add.'
                chipColor="amber"
              />
            </div>

            <div className="sm:col-span-2">
              <Button type="submit" loading={addLoading}>
                Add source
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* OPML import/export */}
      <Card>
        <CardHeader title="OPML" />
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <span className="inline-flex items-center px-4 py-2 text-sm font-semibold bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-300 dark:border-slate-600 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors cursor-pointer">
              {opmlLoading ? 'Importing...' : 'Import OPML'}
            </span>
            <input
              type="file"
              accept=".opml,.xml,text/xml"
              className="sr-only"
              onChange={handleImportOpml}
              disabled={opmlLoading}
            />
          </label>
          <a
            href={api.exportOpmlUrl()}
            download="elpis-sources.opml"
            className="inline-flex items-center px-4 py-2 text-sm font-semibold bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-300 dark:border-slate-600 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
          >
            Export OPML
          </a>
        </div>
      </Card>

      {/* Search + category filter */}
      {sources.length > 0 && (
        <div className="space-y-3">
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
              />
            </svg>
            <input
              type="text"
              aria-label="Search sources"
              placeholder="Search by name, URL, or category..."
              value={searchQuery}
              onInput={(e) =>
                setSearchQuery(
                  (e.target as HTMLInputElement).value,
                )
              }
              className={`${inputCls} pl-10`}
            />
          </div>

          {categories.length > 1 && (
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setActiveCategory(null)}
                className={[
                  'px-2.5 py-1 text-xs font-medium rounded-full transition-colors',
                  activeCategory === null
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700',
                ].join(' ')}
              >
                All
              </button>
              {categories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() =>
                    setActiveCategory(
                      activeCategory === cat ? null : cat,
                    )
                  }
                  className={[
                    'px-2.5 py-1 text-xs font-medium rounded-full transition-colors',
                    activeCategory === cat
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700',
                  ].join(' ')}
                >
                  {cat}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Sources list */}
      {sources.length === 0 ? (
        <EmptyState
          title="No sources yet"
          description="Add your first source - RSS, YouTube, Google News search, Hacker News, Reddit, GitHub Releases, or Podcasts."
          action={
            <Button onClick={() => setAddFormOpen(true)}>
              Add source
            </Button>
          }
        />
      ) : filteredSources.length === 0 ? (
        <div className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
          No sources match your search.
        </div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-slate-50 dark:bg-slate-800/60 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    <th className="text-left px-4 py-3">Type</th>
                    <th className="text-left px-4 py-3">Name</th>
                    <th className="text-left px-4 py-3">URL</th>
                    <th className="text-left px-4 py-3">Category</th>
                    <th className="text-left px-4 py-3">Priority</th>
                    <th className="text-left px-4 py-3">Health</th>
                    <th className="text-left px-4 py-3">Enabled</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {filteredSources.map((s) => (
                    <Fragment key={s.id}>
                      <tr
                        className={[
                          'border-t border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/30',
                          s.enabled === 0 ? 'opacity-50' : '',
                        ].join(' ')}
                      >
                        <td className="px-4 py-3">
                          <Badge variant={kindVariant(s.type)}>
                            {s.type}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">
                          {s.name}
                        </td>
                        <td className="px-4 py-3 max-w-xs truncate text-slate-500 dark:text-slate-400 font-mono text-xs">
                          {s.url}
                        </td>
                        <td className="px-4 py-3 text-slate-600 dark:text-slate-400">
                          {s.category}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${PRIORITY_COLORS[s.priority] ?? PRIORITY_COLORS[2]}`}
                          >
                            {PRIORITY_LABELS[s.priority] ??
                              `P${s.priority}`}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-500">
                          {s.last_status ? (
                            <div className="flex flex-col gap-0.5">
                              <Badge
                                variant={kindVariant(
                                  s.last_status === 'ok'
                                    ? 'ok'
                                    : 'error',
                                )}
                              >
                                {s.last_status}
                              </Badge>
                              {s.last_item_count != null && (
                                <span>
                                  {s.last_item_count} items
                                </span>
                              )}
                              {s.last_checked_at && (
                                <span title={s.last_error ?? ''}>
                                  {formatDigestLabel(s.last_checked_at)}
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-slate-400">
                              &mdash;
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <ToggleSwitch
                            enabled={s.enabled !== 0}
                            disabled={togglingId === s.id}
                            label={`${s.enabled !== 0 ? 'Disable' : 'Enable'} ${s.name}`}
                            onChange={() =>
                              handleToggle(s.id, s.enabled ?? 1)
                            }
                          />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setEditingId(
                                  editingId === s.id ? null : s.id,
                                )
                              }
                            >
                              {editingId === s.id ? 'Cancel' : 'Edit'}
                            </Button>
                            <Button
                              variant={
                                confirmDeleteId === s.id
                                  ? 'danger'
                                  : 'ghost'
                              }
                              size="sm"
                              loading={deletingId === s.id}
                              onClick={() => handleDelete(s.id)}
                            >
                              {confirmDeleteId === s.id
                                ? 'Confirm'
                                : 'Delete'}
                            </Button>
                          </div>
                        </td>
                      </tr>
                      {editingId === s.id && (
                        <tr className="border-t border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40">
                          <td colSpan={8} className="px-4 py-4">
                            <SourceEditForm
                              source={s}
                              loading={editLoadingId === s.id}
                              onCancel={() => setEditingId(null)}
                              onSubmit={(e) => handleEdit(e, s)}
                              categories={categories}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="md:hidden space-y-3">
            {filteredSources.map((s) => (
              <div
                key={s.id}
                className={[
                  'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-sm p-4 space-y-2',
                  s.enabled === 0 ? 'opacity-50' : '',
                ].join(' ')}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-sm text-slate-900 dark:text-slate-100 truncate">
                      {s.name}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 font-mono truncate mt-0.5">
                      {s.url}
                    </p>
                  </div>
                  <Badge variant={kindVariant(s.type)}>
                    {s.type}
                  </Badge>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-slate-600 dark:text-slate-400">
                    {s.category}
                  </span>
                  <span className="text-slate-300 dark:text-slate-600">
                    &middot;
                  </span>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${PRIORITY_COLORS[s.priority] ?? PRIORITY_COLORS[2]}`}
                  >
                    {PRIORITY_LABELS[s.priority] ??
                      `P${s.priority}`}
                  </span>
                  {s.last_status && (
                    <>
                      <span className="text-slate-300 dark:text-slate-600">
                        &middot;
                      </span>
                      <Badge
                        variant={kindVariant(
                          s.last_status === 'ok'
                            ? 'ok'
                            : 'error',
                        )}
                      >
                        {s.last_status}
                      </Badge>
                    </>
                  )}
                </div>
                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-2">
                    <ToggleSwitch
                      enabled={s.enabled !== 0}
                      disabled={togglingId === s.id}
                      label={`${s.enabled !== 0 ? 'Disable' : 'Enable'} ${s.name}`}
                      onChange={() =>
                        handleToggle(s.id, s.enabled ?? 1)
                      }
                    />
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      {s.enabled !== 0 ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setEditingId(editingId === s.id ? null : s.id)
                      }
                    >
                      {editingId === s.id ? 'Cancel' : 'Edit'}
                    </Button>
                    <Button
                      variant={
                        confirmDeleteId === s.id
                          ? 'danger'
                          : 'ghost'
                      }
                      size="sm"
                      loading={deletingId === s.id}
                      onClick={() => handleDelete(s.id)}
                    >
                      {confirmDeleteId === s.id
                        ? 'Confirm delete'
                        : 'Delete'}
                    </Button>
                  </div>
                </div>
                {editingId === s.id && (
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                    <SourceEditForm
                      source={s}
                      loading={editLoadingId === s.id}
                      onCancel={() => setEditingId(null)}
                      onSubmit={(e) => handleEdit(e, s)}
                      categories={categories}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function SourceEditForm({
  source,
  loading,
  onCancel,
  onSubmit,
  categories,
}: {
  source: Source;
  loading: boolean;
  onCancel: () => void;
  onSubmit: (e: Event) => void;
  categories: string[];
}) {
  const extra = parseSourceExtra(source);
  const sourceType = source.type;
  const [podcastQuery, setPodcastQuery] = useState('');
  const [podcastResults, setPodcastResults] = useState<ITunesResult[]>([]);
  const [podcastSearching, setPodcastSearching] = useState(false);
  const [podcastName, setPodcastName] = useState(source.name);
  const [podcastFeedUrl, setPodcastFeedUrl] = useState(() =>
    extraText(extra, 'feed_url', source.url),
  );

  async function searchPodcasts() {
    if (!podcastQuery.trim()) return;
    setPodcastSearching(true);
    setPodcastResults([]);
    try {
      setPodcastResults(await searchITunesPodcasts(podcastQuery));
    } catch {
      // leave results empty on error
    } finally {
      setPodcastSearching(false);
    }
  }

  function selectPodcast(result: ITunesResult) {
    setPodcastFeedUrl(result.feedUrl ?? '');
    setPodcastName(result.collectionName ?? '');
    setPodcastResults([]);
    setPodcastQuery(result.collectionName ?? '');
  }

  return (
    <form
      onSubmit={onSubmit}
      className="grid grid-cols-1 sm:grid-cols-2 gap-3"
    >
      <input type="hidden" name="source_type" value={sourceType} />
      <Field label="Name">
        {sourceType === 'podcast' ? (
          <input
            name="name"
            required
            value={podcastName}
            onInput={(e) =>
              setPodcastName((e.target as HTMLInputElement).value)
            }
            className={inputCls}
          />
        ) : (
          <input
            name="name"
            required
            defaultValue={source.name}
            className={inputCls}
          />
        )}
      </Field>

      {(sourceType === 'rss' ||
        sourceType === 'youtube' ||
        sourceType === 'website') && (
        <Field label="URL" className="sm:col-span-2">
          <input
            name="url"
            required
            defaultValue={source.url}
            className={inputCls}
          />
        </Field>
      )}

      {sourceType === 'youtube' && (
        <Field label="YouTube channel ID" className="sm:col-span-2">
          <input
            name="channel_id"
            defaultValue={extraText(extra, 'channel_id')}
            className={inputCls}
          />
        </Field>
      )}

      {sourceType === 'google_news' && (
        <>
          <Field label="Search query" className="sm:col-span-2">
            <input
              name="query"
              required
              defaultValue={extraText(extra, 'query')}
              className={inputCls}
            />
          </Field>
          <Field label="Language">
            <input
              name="language"
              defaultValue={extraText(extra, 'language', 'en')}
              className={inputCls}
            />
          </Field>
          <Field label="Country">
            <input
              name="country"
              defaultValue={extraText(extra, 'country', 'US')}
              className={inputCls}
            />
          </Field>
        </>
      )}

      {sourceType === 'hackernews' && (
        <>
          <Field label="Feed">
            <select
              name="hn_feed"
              className={inputCls}
              defaultValue={extraText(extra, 'feed', 'top')}
            >
              <option value="top">Top stories</option>
              <option value="best">Best stories</option>
              <option value="new">New stories</option>
              <option value="ask">Ask HN</option>
              <option value="show">Show HN</option>
            </select>
          </Field>
          <Field label="Min score">
            <input
              name="hn_min_score"
              type="number"
              min="0"
              defaultValue={extraNumber(extra, 'min_score', 50)}
              className={inputCls}
            />
          </Field>
          <Field label="Max items">
            <input
              name="hn_max_items"
              type="number"
              min="1"
              max="100"
              defaultValue={extraNumber(extra, 'max_items', 20)}
              className={inputCls}
            />
          </Field>
        </>
      )}

      {sourceType === 'reddit' && (
        <>
          <Field label="Subreddit" className="sm:col-span-2">
            <input
              name="subreddit"
              required
              defaultValue={extraText(extra, 'subreddit', source.name)}
              className={inputCls}
            />
          </Field>
          <Field label="Sort">
            <select
              name="reddit_sort"
              className={inputCls}
              defaultValue={extraText(extra, 'sort', 'hot')}
            >
              <option value="hot">Hot</option>
              <option value="new">New</option>
              <option value="top">Top</option>
              <option value="rising">Rising</option>
            </select>
          </Field>
          <Field label="Time filter">
            <select
              name="reddit_time_filter"
              className={inputCls}
              defaultValue={extraText(extra, 'time_filter', 'day')}
            >
              <option value="hour">Past hour</option>
              <option value="day">Past 24 h</option>
              <option value="week">Past week</option>
              <option value="month">Past month</option>
              <option value="year">Past year</option>
              <option value="all">All time</option>
            </select>
          </Field>
          <Field label="Min score">
            <input
              name="reddit_min_score"
              type="number"
              min="0"
              defaultValue={extraNumber(extra, 'min_score', 10)}
              className={inputCls}
            />
          </Field>
          <Field label="Max items">
            <input
              name="reddit_max_items"
              type="number"
              min="1"
              max="100"
              defaultValue={extraNumber(extra, 'max_items', 20)}
              className={inputCls}
            />
          </Field>
        </>
      )}

      {sourceType === 'github_releases' && (
        <Field label="Repository" className="sm:col-span-2">
          <input
            name="github_repo"
            required
            defaultValue={extraText(extra, 'repo')}
            className={inputCls}
          />
        </Field>
      )}

      {sourceType === 'podcast' && (
        <>
          <div className="sm:col-span-2 space-y-2">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Search podcasts
              </span>
              <div className="flex gap-2">
                <input
                  type="text"
                  aria-label="Podcast search"
                  placeholder='e.g. "Darknet Diaries"'
                  value={podcastQuery}
                  onInput={(e) =>
                    setPodcastQuery((e.target as HTMLInputElement).value)
                  }
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      void searchPodcasts();
                    }
                  }}
                  className={`${inputCls} flex-1`}
                />
                <button
                  type="button"
                  onClick={() => void searchPodcasts()}
                  disabled={podcastSearching}
                  className="px-4 py-2 text-sm font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                >
                  {podcastSearching ? 'Searching...' : 'Search'}
                </button>
              </div>
            </div>

            {podcastResults.length > 0 && (
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800 overflow-hidden">
                {podcastResults.map((r) => (
                  <button
                    key={r.feedUrl}
                    type="button"
                    onClick={() => selectPodcast(r)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 text-left bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                  >
                    {r.artworkUrl100 && (
                      <img
                        src={r.artworkUrl100}
                        alt=""
                        className="w-10 h-10 rounded-lg object-cover flex-shrink-0"
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                        {r.collectionName}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                        {r.artistName}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <Field label="Feed URL" className="sm:col-span-2">
            <input
              name="url"
              required
              value={podcastFeedUrl}
              onInput={(e) =>
                setPodcastFeedUrl((e.target as HTMLInputElement).value)
              }
              className={inputCls}
            />
          </Field>
        </>
      )}

      <Field label="Category">
        <CategoryCombobox
          name="category"
          defaultValue={source.category}
          options={categories}
          className={inputCls}
        />
      </Field>
      <Field label="Priority">
        <select
          name="priority"
          className={inputCls}
          defaultValue={String(source.priority)}
        >
          <option value="1">1 - High</option>
          <option value="2">2 - Normal</option>
          <option value="3">3 - Low</option>
          <option value="4">4 - Lower</option>
          <option value="5">5 - Lowest</option>
        </select>
      </Field>
      {(sourceType === 'rss' ||
        sourceType === 'google_news' ||
        sourceType === 'github_releases' ||
        sourceType === 'podcast') && (
        <Field label="Max items per source">
          <input
            name="max_items"
            type="number"
            min="1"
            max="200"
            defaultValue={extraNumber(extra, 'max_items', 50)}
            className={inputCls}
          />
          <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
            Candidate entries collected before ranking (1–200)
          </span>
        </Field>
      )}

      {/* --- Filter rules --- */}
      <div className="sm:col-span-2 border-t border-slate-100 dark:border-slate-800 pt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <KeywordChipInput
          name="require_keywords"
          label="Show only if"
          hint='Only articles containing at least one of these are kept. Supports wildcards: CVE-*, GHSA-*. Leave empty to keep all articles.'
          chipColor="blue"
          defaultKeywords={
            Array.isArray(extra['require_keywords'])
              ? (extra['require_keywords'] as unknown as string[]).filter(Boolean)
              : []
          }
        />
        <KeywordChipInput
          name="hide_keywords"
          label="Hide keywords"
          hint='Articles whose title or content contains any of these are excluded. Case-insensitive, press Enter or comma to add.'
          chipColor="red"
          defaultKeywords={
            Array.isArray(extra['hide_keywords'])
              ? (extra['hide_keywords'] as unknown as string[]).filter(Boolean)
              : []
          }
        />
        <KeywordChipInput
          name="highlight_keywords"
          label="Highlight keywords"
          hint='Articles containing any of these get a ranking boost and a visual badge. Case-insensitive, press Enter or comma to add.'
          chipColor="amber"
          defaultKeywords={
            Array.isArray(extra['highlight_keywords'])
              ? (extra['highlight_keywords'] as unknown as string[]).filter(Boolean)
              : []
          }
        />
      </div>

      <div className="sm:col-span-2 flex items-center gap-2">
        <Button type="submit" size="sm" loading={loading}>
          Save changes
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Field({
  label,
  children,
  className = '',
}: {
  label: string;
  children: preact.ComponentChildren;
  className?: string;
}) {
  return (
    <label className={`flex flex-col gap-1 ${className}`}>
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </span>
      {children}
    </label>
  );
}

/**
 * Chip/tag input that lets users add and remove keywords.
 * Serializes to a hidden form input as a comma-separated string.
 */
function KeywordChipInput({
  name,
  label,
  hint,
  defaultKeywords = [],
  chipColor = 'slate',
}: {
  name: string;
  label: string;
  hint: string;
  defaultKeywords?: string[];
  chipColor?: 'red' | 'amber' | 'blue' | 'slate';
}) {
  const [keywords, setKeywords] = useState<string[]>(defaultKeywords);
  const [inputValue, setInputValue] = useState('');

  const chipClass =
    chipColor === 'red'
      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
      : chipColor === 'amber'
      ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
      : chipColor === 'blue'
      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
      : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';

  function addKeyword(raw: string) {
    const parts = raw.split(',').map((s) => s.trim()).filter(Boolean);
    setKeywords((prev) => {
      const next = new Set(prev);
      for (const part of parts) {
        next.add(part);
      }
      return [...next];
    });
    setInputValue('');
  }

  function removeKeyword(kw: string) {
    setKeywords((prev) => prev.filter((k) => k !== kw));
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </span>
      <input type="hidden" name={name} value={keywords.join(',')} />
      {keywords.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {keywords.map((kw) => (
            <span
              key={kw}
              className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${chipClass}`}
            >
              {kw}
              <button
                type="button"
                aria-label={`Remove ${kw}`}
                onClick={() => removeKeyword(kw)}
                className="ml-0.5 hover:opacity-70 transition-opacity"
              >
                &times;
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <input
          type="text"
          aria-label="Keyword"
          placeholder="Add keyword..."
          value={inputValue}
          onInput={(e) => setInputValue((e.target as HTMLInputElement).value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault();
              if (inputValue.trim()) addKeyword(inputValue);
            }
          }}
          className={`${inputCls} flex-1`}
        />
        <button
          type="button"
          onClick={() => { if (inputValue.trim()) addKeyword(inputValue); }}
          className="px-3 py-2 text-sm font-semibold rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors whitespace-nowrap"
        >
          Add
        </button>
      </div>
      <p className="text-xs text-slate-400 dark:text-slate-500">{hint}</p>
    </div>
  );
}

/**
 * Accessible toggle switch. Uses a button with role="switch" so screen
 * readers announce the on/off state correctly.
 */
function ToggleSwitch({
  enabled,
  onChange,
  label,
  disabled = false,
}: {
  enabled: boolean;
  onChange: () => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-label={label}
      aria-checked={enabled}
      disabled={disabled}
      onClick={onChange}
      className={[
        'relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full',
        'transition-colors duration-200 ease-in-out',
        'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1',
        enabled
          ? 'bg-blue-500'
          : 'bg-slate-300 dark:bg-slate-600',
        disabled
          ? 'opacity-50 cursor-not-allowed'
          : 'cursor-pointer',
      ].join(' ')}
    >
      <span
        className={[
          'inline-block h-3.5 w-3.5 rounded-full bg-white shadow',
          'transition-transform duration-200 ease-in-out',
          enabled ? 'translate-x-5' : 'translate-x-0.5',
        ].join(' ')}
      />
    </button>
  );
}
