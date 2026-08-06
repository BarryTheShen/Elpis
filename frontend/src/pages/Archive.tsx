import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { Link } from 'wouter';

import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { Spinner } from '../components/Spinner';
import { api } from '../lib/api';
import { formatDigestLabel } from '../lib/dates';
import type { DigestEntry } from '../lib/types';

const PAGE_SIZE = 20;

/** Public archive of published digest issues, loaded newest page first. */
export function ArchivePage() {
  const [entries, setEntries] = useState<DigestEntry[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    return () => {
      mounted.current = false;
    };
  }, []);

  const loadPage = useCallback(async (beforeId?: number) => {
    if (inFlight.current) return;

    const isInitial = beforeId == null;
    inFlight.current = true;
    setError(null);
    if (isInitial) {
      setInitialLoading(true);
    } else {
      setLoadingMore(true);
    }

    try {
      const page = await api.listDigests(PAGE_SIZE, beforeId);
      if (!mounted.current) return;

      if (isInitial) {
        setEntries(page);
      } else {
        setEntries((previous) => {
          const knownIds = new Set(previous.map((entry) => entry.id));
          const additions = page.filter((entry) => !knownIds.has(entry.id));
          return additions.length > 0 ? [...previous, ...additions] : previous;
        });
      }
      // A short page proves there are no older issues to request.
      setHasMore(page.length >= PAGE_SIZE);
    } catch (reason: unknown) {
      if (!mounted.current) return;
      setError(
        reason instanceof Error ? reason.message : 'Failed to load the archive.',
      );
    } finally {
      inFlight.current = false;
      if (mounted.current) {
        if (isInitial) {
          setInitialLoading(false);
        } else {
          setLoadingMore(false);
        }
      }
    }
  }, []);

  useEffect(() => {
    void loadPage();
  }, [loadPage]);

  const handleLoadMore = useCallback(() => {
    if (initialLoading || loadingMore || !hasMore || entries.length === 0) {
      return;
    }
    const last = entries[entries.length - 1];
    void loadPage(last.id);
  }, [entries, hasMore, initialLoading, loadPage, loadingMore]);

  if (initialLoading && entries.length === 0) {
    return (
      <div className="flex min-h-64 flex-col items-center justify-center gap-3 py-20" aria-busy="true">
        <Spinner size="lg" className="text-[#2783de] dark:text-[#63aaf0]" />
        <p className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">Loading archive…</p>
      </div>
    );
  }

  if (error && entries.length === 0) {
    return (
      <EmptyState
        title="Could not load archive"
        description={error}
        action={<Button onClick={() => void loadPage()}>Retry</Button>}
        icon={
          <svg className="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
        }
      />
    );
  }

  if (entries.length === 0) {
    return (
      <EmptyState
        title="No published issues yet"
        description="Published digest issues will appear here once the first briefing is ready."
        action={
          <Link
            href="/"
            className="inline-flex items-center rounded-lg bg-[#2783de] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#1f6fbe] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de] dark:bg-[#63aaf0] dark:text-[#171716] dark:hover:bg-[#83bdf5]"
          >
            Go to today
          </Link>
        }
      />
    );
  }

  return (
    <section className="space-y-8" aria-labelledby="archive-heading">
      <header className="space-y-3">
        <p className="text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8]">Publication history</p>
        <h1 id="archive-heading" className="text-4xl font-semibold tracking-[-0.035em] text-[#2c2c2b] dark:text-[#f4f3f1]">
          Archive
        </h1>
        <p className="max-w-prose text-base leading-7 text-[#7d7a75] dark:text-[#b4b1ab]">
          Browse earlier issues of the Elpis briefing.
        </p>
      </header>

      {error && (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#f4c6c1] bg-[#fff1ef] px-4 py-3 text-sm text-[#8f3f34] dark:border-[#7e3f37] dark:bg-[#4a2521] dark:text-[#ffb9b1]"
          role="alert"
        >
          <span>Could not load more issues: {error}</span>
          <Button variant="secondary" size="sm" onClick={handleLoadMore}>
            Retry
          </Button>
        </div>
      )}

      <ol className="divide-y divide-[#e6e5e3] border-y border-[#e6e5e3] dark:divide-[#3b3a37] dark:border-[#3b3a37]">
        {entries.map((entry) => {
          const label = formatDigestLabel(entry.created_at);
          return (
            <li key={entry.id}>
              <Link
                href={`/?id=${entry.id}`}
                aria-label={`Read issue ${entry.id}, published ${label}`}
                className="flex min-h-16 items-center justify-between gap-4 px-3 py-3 text-sm transition-colors hover:bg-[#f9f8f7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#2783de] sm:px-4 dark:hover:bg-[#20201e]"
              >
                <span className="font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]">Issue #{entry.id}</span>
                <time dateTime={entry.created_at} className="text-right text-[#7d7a75] dark:text-[#b4b1ab]">
                  {label}
                </time>
              </Link>
            </li>
          );
        })}
      </ol>

      {hasMore ? (
        <div className="flex justify-center">
          <Button loading={loadingMore} onClick={handleLoadMore}>
            Load more
          </Button>
        </div>
      ) : (
        <p className="text-center text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
          You&apos;ve reached the beginning of the archive.
        </p>
      )}
    </section>
  );
}
