import { useCallback, useEffect, useState } from 'preact/hooks';
import { Link, useSearch } from 'wouter';

import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { Spinner } from '../components/Spinner';
import { api } from '../lib/api';
import { formatDigestLabel } from '../lib/dates';
import type { MonitorQuery, MonitorResult, MonitorResultsPage } from '../lib/types';

const PAGE_SIZE = 20;

function parseMonitorId(search: string): number | undefined {
  const value = new URLSearchParams(search).get('id');
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function timestamp(value?: string | null): string {
  return value ? formatDigestLabel(value) : 'Not checked yet';
}

function monitorLabel(query: MonitorQuery): string {
  return query.question || query.search_query || `Monitor #${query.id}`;
}

function resultStateClass(state: MonitorResult['state']): string {
  if (state === 'new') return 'bg-[#e5f2fc] text-[#1d5f9f] dark:bg-[#1c3852] dark:text-[#a6d2f8]';
  if (state === 'dismissed') return 'bg-[#f0efed] text-[#7d7a75] dark:bg-[#2a2927] dark:text-[#b4b1ab]';
  return 'border border-[#e6e5e3] text-[#7d7a75] dark:border-[#3b3a37] dark:text-[#b4b1ab]';
}

function MonitorResultCard({
  result,
  busy,
  onSeen,
}: {
  result: MonitorResult;
  busy: boolean;
  onSeen: () => void;
}) {
  const matchedTerms = result.evidence?.matched_terms ?? [];
  return (
    <article className="rounded-lg border border-[#e6e5e3] bg-white p-5 dark:border-[#3b3a37] dark:bg-[#20201e]">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs uppercase tracking-[0.08em] text-[#7d7a75] dark:text-[#b4b1ab]">
        <span>{result.source || 'Unknown source'}{result.category ? ` · ${result.category}` : ''}</span>
        <span className={`rounded-full px-2 py-1 text-[11px] font-semibold normal-case tracking-normal ${resultStateClass(result.state)}`}>
          {result.state}
        </span>
      </div>
      <h3 className="mt-3 text-lg font-semibold leading-snug text-[#2c2c2b] dark:text-[#f4f3f1]">
        <a href={result.url} target="_blank" rel="noreferrer" className="underline decoration-transparent underline-offset-4 transition-colors hover:decoration-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de]">
          {result.title}
        </a>
      </h3>
      <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
        {result.published_at && <time dateTime={result.published_at}>Published {timestamp(result.published_at)}</time>}
        {result.relevance_score != null && <span>· Relevance {result.relevance_score.toFixed(2)}</span>}
      </div>
      {result.snippet && <p className="mt-3 text-sm leading-6 text-[#5e5b56] dark:text-[#cbc8c1]">{result.snippet}</p>}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {matchedTerms.slice(0, 5).map((term) => <span key={term} className="rounded-full bg-[#f0efed] px-2 py-1 text-xs text-[#5e5b56] dark:bg-[#2a2927] dark:text-[#cbc8c1]">{term}</span>)}
        {result.evidence?.provider && <span className="rounded-full border border-[#e6e5e3] px-2 py-1 text-xs text-[#7d7a75] dark:border-[#3b3a37] dark:text-[#b4b1ab]">{result.evidence.provider}</span>}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <a href={result.url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-[#1d5f9f] underline underline-offset-4 hover:text-[#164a7c] focus-visible:ring-2 focus-visible:ring-[#2783de] dark:text-[#a6d2f8]">Open source ↗</a>
        {result.state === 'new' && <Button size="sm" variant="secondary" loading={busy} onClick={onSeen}>Mark seen</Button>}
      </div>
    </article>
  );
}

function hasNextPage(data: MonitorResultsPage): boolean {
  if (data.has_more != null) return data.has_more;
  if (data.next_page != null) return true;
  if (data.total != null) return data.page * data.limit < data.total;
  return data.results.length >= data.limit;
}

/** Authenticated, read-focused monitor history. Query mutation lives in admin. */
export function MonitoringPage() {
  const search = useSearch();
  const requestedId = parseMonitorId(search);
  const [queries, setQueries] = useState<MonitorQuery[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(requestedId ?? null);
  const [resultsData, setResultsData] = useState<MonitorResultsPage | null>(null);
  const [loadingQueries, setLoadingQueries] = useState(true);
  const [loadingResults, setLoadingResults] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [resultPage, setResultPage] = useState(1);
  const [busyResultId, setBusyResultId] = useState<number | null>(null);

  const loadQueries = useCallback(async () => {
    setLoadingQueries(true);
    setError(null);
    try {
      const next = await api.listMonitoring();
      setQueries(next);
      setSelectedId((current) => {
        if (current != null && next.some((query) => query.id === current)) return current;
        return next[0]?.id ?? null;
      });
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Failed to load monitoring questions.');
    } finally {
      setLoadingQueries(false);
    }
  }, []);

  useEffect(() => { void loadQueries(); }, [loadQueries]);

  const loadResults = useCallback(async (monitorId: number, page: number) => {
    setLoadingResults(true);
    setResultsError(null);
    try {
      const next = await api.listMonitoringResults(monitorId, { page, limit: PAGE_SIZE });
      setResultsData(next);
      setResultPage(next.page || page);
    } catch (reason: unknown) {
      setResultsError(reason instanceof Error ? reason.message : 'Failed to load monitoring history.');
    } finally {
      setLoadingResults(false);
    }
  }, []);

  useEffect(() => {
    setResultsData(null);
    setResultPage(1);
    if (selectedId != null) void loadResults(selectedId, 1);
  }, [loadResults, selectedId]);

  async function markSeen(result: MonitorResult) {
    if (selectedId == null || busyResultId != null) return;
    setBusyResultId(result.id);
    try {
      await api.markMonitoringResultSeen(selectedId, result.id);
      setResultsData((current) => current ? {
        ...current,
        results: current.results.map((item) => item.id === result.id ? { ...item, state: 'seen' } : item),
      } : current);
      setQueries((current) => current.map((query) => query.id === selectedId && (query.new_count ?? 0) > 0 ? { ...query, new_count: Math.max(0, (query.new_count ?? 0) - 1) } : query));
    } catch (reason: unknown) {
      setResultsError(reason instanceof Error ? reason.message : 'Could not mark result seen.');
    } finally {
      setBusyResultId(null);
    }
  }

  const selectedQuery = queries.find((query) => query.id === selectedId) ?? null;
  const results = resultsData?.results ?? [];

  if (loadingQueries && queries.length === 0) {
    return <div className="flex min-h-48 items-center justify-center" aria-busy="true"><Spinner size="lg" className="text-[#2783de] dark:text-[#63aaf0]" /></div>;
  }

  if (error && queries.length === 0) {
    return <EmptyState title="Could not load monitoring" description={error} action={<Button onClick={() => void loadQueries()}>Retry</Button>} />;
  }

  return (
    <section className="space-y-8" aria-labelledby="monitoring-heading">
      <header className="space-y-3">
        <p className="text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8]">Personal watch list</p>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 id="monitoring-heading" className="text-4xl font-semibold tracking-[-0.035em] text-[#2c2c2b] dark:text-[#f4f3f1]">Monitoring</h1>
            <p className="mt-2 max-w-prose text-base leading-7 text-[#7d7a75] dark:text-[#b4b1ab]">Read the latest results from your saved questions. Manage questions on desktop in Admin.</p>
          </div>
          <Link href="/" className="text-sm font-semibold text-[#1d5f9f] underline underline-offset-4 hover:text-[#164a7c] dark:text-[#a6d2f8]">Back to today</Link>
        </div>
      </header>

      {error && <div className="rounded-lg border border-[#f4c6c1] bg-[#fff1ef] px-4 py-3 text-sm text-[#8f3f34] dark:border-[#7e3f37] dark:bg-[#4a2521] dark:text-[#ffb9b1]" role="alert">{error}</div>}

      {queries.length === 0 ? (
        <EmptyState title="No monitoring questions yet" description="An administrator can add a question such as a release watch from the desktop Admin area." />
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(12rem,18rem)_1fr]">
          <aside aria-label="Monitoring questions">
            <div className="space-y-2">
              {queries.map((query) => {
                const active = query.id === selectedId;
                return (
                  <button
                    key={query.id}
                    type="button"
                    onClick={() => setSelectedId(query.id)}
                    className={`w-full rounded-lg border px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de] ${active ? 'border-[#9fc8e8] bg-[#e5f2fc] dark:border-[#52799c] dark:bg-[#1c3852]' : 'border-[#e6e5e3] hover:bg-[#f9f8f7] dark:border-[#3b3a37] dark:hover:bg-[#20201e]'}`}
                  >
                    <span className="block text-sm font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]">{monitorLabel(query)}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                      <span>{query.enabled ? 'Active' : 'Paused'}</span>
                      {(query.new_count ?? 0) > 0 && <span className="rounded-full bg-[#2783de] px-1.5 py-0.5 font-semibold text-white">{query.new_count} new</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          </aside>

          <div className="min-w-0 space-y-5">
            {selectedQuery && (
              <div className="border-b border-[#e6e5e3] pb-5 dark:border-[#3b3a37]">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-2xl font-semibold tracking-tight text-[#2c2c2b] dark:text-[#f4f3f1]">{monitorLabel(selectedQuery)}</h2>
                    <p className="mt-1 text-sm text-[#7d7a75] dark:text-[#b4b1ab]">{selectedQuery.scope.replace('_', ' ')} · every {selectedQuery.cadence_minutes} minutes · {selectedQuery.enabled ? 'active' : 'paused'}</p>
                  </div>
                  {selectedQuery.last_error && <span className="max-w-xs text-right text-xs text-[#8f3f34] dark:text-[#ffb9b1]">Last check failed: {selectedQuery.last_error}</span>}
                </div>
                <p className="mt-2 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">Last checked {timestamp(selectedQuery.last_checked_at)} · Next check {timestamp(selectedQuery.next_check_at)}</p>
              </div>
            )}

            {resultsError && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#f4c6c1] bg-[#fff1ef] px-4 py-3 text-sm text-[#8f3f34] dark:border-[#7e3f37] dark:bg-[#4a2521] dark:text-[#ffb9b1]" role="alert"><span>{resultsError}</span>{selectedId != null && <Button variant="secondary" size="sm" onClick={() => void loadResults(selectedId, resultPage)}>Retry</Button>}</div>}
            {loadingResults && !resultsData ? <div className="flex min-h-48 items-center justify-center" aria-busy="true"><Spinner size="lg" className="text-[#2783de] dark:text-[#63aaf0]" /></div> : results.length === 0 ? <div className="rounded-lg border border-dashed border-[#d7d5d2] px-5 py-12 text-center dark:border-[#4a4945]"><p className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">No results yet</p><p className="mt-1 text-sm text-[#7d7a75] dark:text-[#b4b1ab]">The next check will add matching stories here.</p></div> : (
              <>
                <div className="space-y-4">{results.map((result) => <MonitorResultCard key={result.id} result={result} busy={busyResultId === result.id} onSeen={() => void markSeen(result)} />)}</div>
                <nav className="flex flex-wrap items-center justify-center gap-3 border-t border-[#e6e5e3] pt-5 dark:border-[#3b3a37]" aria-label="Monitoring result pages">
                  <Button variant="secondary" disabled={loadingResults || resultPage <= 1 || selectedId == null} onClick={() => selectedId != null && void loadResults(selectedId, resultPage - 1)}>Previous</Button>
                  <span className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">Page {resultPage}</span>
                  <Button disabled={loadingResults || selectedId == null || !resultsData || !hasNextPage(resultsData)} onClick={() => selectedId != null && void loadResults(selectedId, resultPage + 1)}>Next</Button>
                </nav>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
