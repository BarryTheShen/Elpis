import { useState, useEffect, useCallback } from 'preact/hooks';
import { useSearch } from 'wouter';
import { api } from '../lib/api';
import type { DigestDetail, DigestItem } from '../lib/types';
import { normalizeItem } from '../lib/normalize-item';
import { DigestCard } from '../components/DigestCard';
import { ItemDetailPanel } from '../components/ItemDetailPanel';
import { FilterPanel } from '../components/FilterPanel';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/Button';
import { formatDigestSubtitle } from '../lib/dates';

function fmtProcessingTime(raw: string): string {
  const match = raw.match(/^(\d+)s$/);
  if (!match) return raw;
  const total = parseInt(match[1], 10);
  if (total < 60) return raw;
  const m = Math.floor(total / 60);
  const s = total % 60;
  return s === 0 ? `${m}m` : `${m}m ${s}s`;
}
function DigestSkeleton() {
  return (
    <div class="animate-pulse space-y-8" aria-label="Loading digest">
      <div class="space-y-3">
        <div class="h-3 w-24 rounded bg-[#e6e5e3] dark:bg-[#3b3a37]" />
        <div class="h-9 w-64 rounded bg-[#e6e5e3] dark:bg-[#3b3a37]" />
        <div class="h-4 w-80 max-w-full rounded bg-[#f0efed] dark:bg-[#2a2927]" />
      </div>
      <div class="border-y border-[#e6e5e3] py-4 dark:border-[#3b3a37]">
        <div class="h-10 w-full rounded bg-[#f0efed] dark:bg-[#2a2927]" />
      </div>
      <div class="grid gap-5 md:grid-cols-2">
        {[0, 1, 2, 3].map((key) => (
          <div
            key={key}
            class="space-y-4 rounded-lg border border-[#e6e5e3] p-5 dark:border-[#3b3a37]"
          >
            <div class="h-3 w-24 rounded bg-[#e6e5e3] dark:bg-[#3b3a37]" />
            <div class="h-5 w-4/5 rounded bg-[#e6e5e3] dark:bg-[#3b3a37]" />
            <div class="h-4 w-full rounded bg-[#f0efed] dark:bg-[#2a2927]" />
            <div class="h-4 w-11/12 rounded bg-[#f0efed] dark:bg-[#2a2927]" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Map of url -> current saved rating for this digest view. */
type RatingsMap = Record<string, number>;

interface DigestPageProps {
  onDigestLoaded?: (id: number | null) => void;
  /** Public readers can browse sources but cannot change personal signals. */
  readOnly?: boolean;
}

/** Digest viewer page. Fetches the published digest and optional personal state. */
export function DigestPage({ onDigestLoaded, readOnly = false }: DigestPageProps) {
  const search = useSearch();
  const params = new URLSearchParams(search);
  const requestedId = params.get('id') ? Number(params.get('id')) : null;

  const [detail, setDetail] = useState<DigestDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [filtered, setFiltered] = useState<DigestItem[]>([]);

  /** Ratings keyed by URL, seeded from server response. */
  const [ratings, setRatings] = useState<RatingsMap>({});

  /** URLs the user has marked as read. */
  const [readUrls, setReadUrls] = useState<Set<string>>(new Set());

  /** When true (default) read items are hidden from the grid. */
  const [hideRead, setHideRead] = useState(true);

  /** URLs the user has saved to read later. */
  const [readLaterUrls, setReadLaterUrls] = useState<Set<string>>(new Set());

  /** URLs the user has starred for permanent keeping. */
  const [starredUrls, setStarredUrls] = useState<Set<string>>(new Set());

  /** Item currently open in the detail panel, or null when closed. */
  const [selectedItem, setSelectedItem] = useState<DigestItem | null>(null);

  useEffect(() => {
    const handleDigestCompleted = () => setRefreshToken((value) => value + 1);
    window.addEventListener('digest:completed', handleDigestCompleted);
    return () =>
      window.removeEventListener('digest:completed', handleDigestCompleted);
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);

    const load =
      requestedId !== null
        ? api.getDigest(requestedId)
        : api.getLatestDigest();

    const readUrlsRequest = readOnly
      ? Promise.resolve({ urls: [] as string[] })
      : api.getReadUrls().catch(() => ({ urls: [] as string[] }));
    const readLaterUrlsRequest = readOnly
      ? Promise.resolve({ urls: [] as string[] })
      : api.getReadLaterUrls().catch(() => ({ urls: [] as string[] }));
    const starredUrlsRequest = readOnly
      ? Promise.resolve({ urls: [] as string[] })
      : api.getStarredUrls().catch(() => ({ urls: [] as string[] }));

    Promise.all([
      load,
      readUrlsRequest,
      readLaterUrlsRequest,
      starredUrlsRequest,
    ])
      .then(([d, { urls: fetchedReadUrls }, { urls: fetchedReadLaterUrls }, { urls: fetchedStarredUrls }]) => {
        setDetail(d);
        setFiltered(d?.items ?? []);
        onDigestLoaded?.(d?.meta.id ?? null);

        // Seed ratings from server-supplied per-item ratings.
        const initial: RatingsMap = {};
        for (const item of d?.items ?? []) {
          if (item.url && item.rating != null) {
            initial[item.url] = item.rating;
          }
        }
        setRatings(initial);

        // Apply read / read-later / starred state together with the digest so
        // the first paint already has the correct visibility.
        setReadUrls(new Set(fetchedReadUrls));
        setReadLaterUrls(new Set(fetchedReadLaterUrls));
        setStarredUrls(new Set(fetchedStarredUrls));
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : 'Failed to load digest.');
      })
      .finally(() => setLoading(false));
  }, [requestedId, readOnly, onDigestLoaded, refreshToken]);

  /** Update ratings after a card-level save. */
  const handleRate = useCallback((url: string, rating: number) => {
    setRatings((prev) => ({ ...prev, [url]: rating }));
  }, []);

  /**
   * Toggle the read state for a URL.
   * Calls the server so the next digest pipeline can exclude articles
   * the user has already read. If the request fails, the optimistic
   * update is rolled back so the UI stays consistent with the DB.
   */
  const handleMarkRead = useCallback((url: string) => {
    setReadUrls((prev) => {
      const nowRead = !prev.has(url);
      const next = new Set(prev);
      if (nowRead) {
        next.add(url);
      } else {
        next.delete(url);
      }
      api.markRead(url, nowRead).catch(() => {
        // Roll back the optimistic update if the server call fails.
        setReadUrls((current) => {
          const rolled = new Set(current);
          if (nowRead) {
            rolled.delete(url);
          } else {
            rolled.add(url);
          }
          return rolled;
        });
      });
      return next;
    });
  }, []);

  /**
   * Toggle the read-later state for an item.
   * When saving, the full item payload is sent so the backend can persist it
   * without needing to look it up from a digest row.
   */
  const handleReadLater = useCallback((item: DigestItem) => {
    const url = item.url;
    setReadLaterUrls((prev) => {
      const next = new Set(prev);
      if (next.has(url)) {
        next.delete(url);
        api.removeReadLater(url).catch(() => undefined);
      } else {
        next.add(url);
        api.saveReadLater(item).catch(() => undefined);
      }
      return next;
    });
  }, []);

  /** Toggle the starred state for an item. */
  const handleToggleStar = useCallback((item: DigestItem) => {
    const url = item.url;
    setStarredUrls((prev) => {
      const next = new Set(prev);
      if (next.has(url)) {
        next.delete(url);
        api.unstarItem(url).catch(() => undefined);
      } else {
        next.add(url);
        api.starItem(item).catch(() => undefined);
      }
      return next;
    });
  }, []);

  /**
   * Dismiss an article: records a mild negative implicit signal on the
   * backend (distinct from "mark as read") and marks the item as read
   * locally so it disappears from the grid view. If the request fails,
   * the optimistic update is rolled back so the card reappears.
   */
  const handleDismiss = useCallback(
    (url: string) => {
      const item = detail?.items.find((i) => i.url === url);
      const title = item?.title;
      // Optimistically mark as read so the card disappears immediately.
      setReadUrls((prev) => {
        const next = new Set(prev);
        next.add(url);
        return next;
      });
      api.dismissArticle(url, title).catch(() => {
        // Roll back the optimistic update if the server call fails.
        setReadUrls((current) => {
          const rolled = new Set(current);
          rolled.delete(url);
          return rolled;
        });
      });
    },
    [detail],
  );

  const handleFiltered = useCallback((items: DigestItem[]) => {
    setFiltered(items);
  }, []);

  if (loading) {
    return <DigestSkeleton />;
  }

  if (error) {
    return (
      <EmptyState
        title="Could not load digest"
        description={error}
        action={
          <Button onClick={() => window.location.reload()}>Retry</Button>
        }
        icon={
          <svg class="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
        }
      />
    );
  }

  if (!detail) {
    return (
      <EmptyState
        title="No digest yet"
        description={
          readOnly
            ? 'A daily briefing will appear here once it is published.'
            : 'Click Run digest in the header to generate one, or configure your sources first.'
        }
        action={
          readOnly ? undefined : (
            <a href="/admin/sources" class="inline-flex items-center rounded-md bg-[#2783de] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#1f6fbe] active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de] dark:bg-[#63aaf0] dark:text-[#171716] dark:hover:bg-[#83bdf5]">
              Configure sources
            </a>
          )
        }
        icon={
          <svg class="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
        }
      />
    );
  }

  const { meta, items } = detail;
  const hasItems = items.length > 0;

  const readCount = filtered.filter((i) => readUrls.has(i.url)).length;

  const visibleItems = readOnly
    ? filtered
    : hideRead
      ? filtered.filter((i) => !readUrls.has(i.url))
      : filtered;

  return (
    <div class="space-y-10">
      {/* Page header */}
      <header class="space-y-4">
        <div class="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p class="text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8]">
              Daily briefing
            </p>
            <h1 class="mt-2 text-4xl font-semibold tracking-[-0.035em] text-[#2c2c2b] dark:text-[#f4f3f1]">
              Today&apos;s reading
            </h1>
            <p class="mt-2 max-w-prose text-base leading-7 text-[#7d7a75] dark:text-[#b4b1ab]">
              A focused selection of stories, ranked for your attention.
            </p>
          </div>
          <p class="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
            Issue #{meta.id}
          </p>
        </div>
        <p class="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
          {meta.created_at && formatDigestSubtitle(meta.created_at)}
          {meta.articles_count != null && ` · ${meta.articles_count} articles`}
          {meta.model && ` · ${meta.model}`}
          {meta.processing_time && ` · ${fmtProcessingTime(meta.processing_time)}`}
        </p>
      </header>
      {!hasItems && (
        <div class="border-y border-[#e6e5e3] dark:border-[#3b3a37]">
          <EmptyState
            title="This issue is empty"
            description="The publication has not received any readable items yet."
          />
        </div>
      )}

      {/* Card browser */}
      {hasItems && (
        <div class="overflow-hidden">
          <FilterPanel
            items={items}
            onFiltered={handleFiltered}
            readCount={readOnly ? 0 : readCount}
            hideRead={hideRead}
            onToggleHideRead={
              readOnly ? undefined : () => setHideRead((h) => !h)
            }
          />

          <div class="flex items-center justify-between gap-4 border-b border-[#e6e5e3] py-3 dark:border-[#3b3a37]">
            <p class="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
              {visibleItems.length === items.length
                ? `${items.length} item${items.length !== 1 ? 's' : ''}`
                : `${visibleItems.length} of ${items.length} item${items.length !== 1 ? 's' : ''}`}
            </p>
          </div>

          {visibleItems.length === 0 ? (
            <div class="py-16 text-center text-base text-[#7d7a75] dark:text-[#b4b1ab]">
              {readCount > 0 && hideRead
                ? 'All matching items are marked as read.'
                : 'No items match these filters.'}
            </div>
          ) : (
            <div class="grid grid-cols-1 gap-5 py-5 md:grid-cols-2">
              {visibleItems.map((raw) => {
                const item = normalizeItem({
                  ...raw,
                  rating: ratings[raw.url] ?? raw.rating,
                });
                return (
                  <DigestCard
                    key={item.url}
                    item={item}
                    readOnly={readOnly}
                    onRate={readOnly ? undefined : handleRate}
                    onMarkRead={readOnly ? undefined : handleMarkRead}
                    isRead={readUrls.has(item.url)}
                    onSelect={readOnly ? undefined : setSelectedItem}
                    onReadLater={readOnly ? undefined : handleReadLater}
                    isReadLater={readLaterUrls.has(item.url)}
                    onDismiss={readOnly ? undefined : handleDismiss}
                    onToggleStar={readOnly ? undefined : handleToggleStar}
                    isStarred={starredUrls.has(item.url)}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Item detail panel (slide-over) */}
      {!readOnly && selectedItem && (
        <ItemDetailPanel
          item={normalizeItem({
            ...selectedItem,
            rating: ratings[selectedItem.url] ?? selectedItem.rating,
          })}
          isRead={readUrls.has(selectedItem.url)}
          rating={ratings[selectedItem.url] ?? selectedItem.rating}
          onClose={() => setSelectedItem(null)}
          onRate={handleRate}
          onMarkRead={handleMarkRead}
          onReadLater={handleReadLater}
          isReadLater={readLaterUrls.has(selectedItem.url)}
          onDismiss={handleDismiss}
          onToggleStar={handleToggleStar}
          isStarred={starredUrls.has(selectedItem.url)}
        />
      )}
    </div>
  );
}
