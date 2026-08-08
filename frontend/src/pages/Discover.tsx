import { useEffect, useState } from 'preact/hooks';
import { useLocation, useSearch } from 'wouter';

import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { Spinner } from '../components/Spinner';
import { api } from '../lib/api';
import type { DiscoveryPage as DiscoveryPageData, DiscoveryItem } from '../lib/types';
import { formatDateOnly } from '../lib/dates';

const PAGE_SIZE = 12;

function DiscoveryResultCard({ result }: { result: DiscoveryItem }) {
  return (
    <article className="rounded-lg border border-[#e6e5e3] bg-white p-5 dark:border-[#3b3a37] dark:bg-[#20201e]">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
        <span className="font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">{result.source || 'Unknown source'}</span>
        {result.category && <><span aria-hidden="true">·</span><span>{result.category}</span></>}
        {result.published_at && <><span aria-hidden="true">·</span><time dateTime={result.published_at}>{formatDateOnly(result.published_at, { year: true })}</time></>}
      </div>
      <h2 className="mt-3 text-lg font-semibold leading-snug text-[#2c2c2b] dark:text-[#f4f3f1]">
        <a
          href={result.url}
          target="_blank"
          rel="noreferrer"
          className="underline decoration-transparent underline-offset-4 transition-colors hover:decoration-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de]"
        >
          {result.title}
        </a>
      </h2>
      {result.snippet && <p className="mt-3 line-clamp-4 text-sm leading-6 text-[#5e5b56] dark:text-[#cbc8c1]">{result.snippet}</p>}
      <a
        href={result.url}
        target="_blank"
        rel="noreferrer"
        className="mt-4 inline-flex min-h-9 items-center text-sm font-semibold text-[#1d5f9f] underline underline-offset-4 hover:text-[#164a7c] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de] dark:text-[#a6d2f8]"
      >
        Open source <span aria-hidden="true" className="ml-1">↗</span>
      </a>
    </article>
  );
}

function hasNextPage(data: DiscoveryPageData): boolean {
  if (data.has_more != null) return data.has_more;
  if (data.next_page != null) return true;
  if (data.total != null) return data.page * data.limit < data.total;
  return data.results.length >= data.limit;
}

/** Public search page backed by general discovery, independent of digest ranking. */
export function DiscoverPage() {
  const search = useSearch();
  const [, navigate] = useLocation();
  const urlQuery = new URLSearchParams(search).get('q')?.trim() ?? '';
  const urlPageValue = Number(new URLSearchParams(search).get('page'));
  const urlPage = Number.isInteger(urlPageValue) && urlPageValue > 0 ? urlPageValue : 1;
  const [input, setInput] = useState(urlQuery);
  const [data, setData] = useState<DiscoveryPageData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setInput(urlQuery);
    if (!urlQuery) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);
    api.discover({ query: urlQuery, page: urlPage, limit: PAGE_SIZE })
      .then((next) => {
        if (active) setData(next);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Failed to search discovery.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [urlPage, urlQuery]);

  function submit(event: Event) {
    event.preventDefault();
    const query = input.trim();
    navigate(query ? `/discover?q=${encodeURIComponent(query)}` : '/discover');
  }

  function goToPage(page: number) {
    const query = new URLSearchParams();
    query.set('q', urlQuery);
    query.set('page', String(page));
    navigate(`/discover?${query.toString()}`);
  }

  const results = data?.results ?? [];

  return (
    <section className="space-y-8" aria-labelledby="discover-heading">
      <header className="space-y-3">
        <p className="text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8]">Open web reading</p>
        <h1 id="discover-heading" className="text-4xl font-semibold tracking-[-0.035em] text-[#2c2c2b] dark:text-[#f4f3f1]">Discover</h1>
        <p className="max-w-prose text-base leading-7 text-[#7d7a75] dark:text-[#b4b1ab]">
          Search beyond the daily briefing. Discovery results stay separate from your digest and preferences.
        </p>
      </header>

      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row" role="search">
        <label htmlFor="discovery-query" className="sr-only">Search discovery</label>
        <input
          id="discovery-query"
          type="search"
          value={input}
          onInput={(event) => setInput((event.currentTarget as HTMLInputElement).value)}
          placeholder="Search a topic, question, or source"
          className="min-h-11 min-w-0 flex-1 rounded-md border border-[#d7d5d2] bg-white px-3 text-base text-[#2c2c2b] placeholder:text-[#9b9892] focus:border-[#2783de] focus:outline-none focus:ring-2 focus:ring-[#2783de]/30 dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1] dark:placeholder:text-[#8d8a84]"
        />
        <Button type="submit" loading={loading && urlQuery === input.trim()}>
          Search
        </Button>
      </form>

      {!urlQuery && (
        <EmptyState
          title="Search when you are curious"
          description="Enter a question or topic to browse general discovery results without changing the daily digest."
        />
      )}

      {urlQuery && loading && !data && (
        <div className="flex min-h-48 flex-col items-center justify-center gap-3" aria-busy="true">
          <Spinner size="lg" className="text-[#2783de] dark:text-[#63aaf0]" />
          <p className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">Searching discovery…</p>
        </div>
      )}

      {urlQuery && error && !data && (
        <EmptyState
          title="Could not search discovery"
          description={error}
          action={<Button onClick={() => navigate(`/discover?q=${encodeURIComponent(urlQuery)}`)}>Retry</Button>}
        />
      )}

      {urlQuery && error && data && (
        <div className="rounded-lg border border-[#f4c6c1] bg-[#fff1ef] px-4 py-3 text-sm text-[#8f3f34] dark:border-[#7e3f37] dark:bg-[#4a2521] dark:text-[#ffb9b1]" role="alert">
          {error}
        </div>
      )}

      {urlQuery && !loading && data && results.length === 0 && !error && (
        <EmptyState
          title="No discovery results"
          description={`Nothing matched “${data.query || urlQuery}”. Try a broader phrase.`}
        />
      )}

      {urlQuery && data && results.length > 0 && (
        <>
          <div className="flex items-center justify-between gap-3 border-y border-[#e6e5e3] py-3 text-sm text-[#7d7a75] dark:border-[#3b3a37] dark:text-[#b4b1ab]">
            <span>{data.total != null ? `${data.total} results` : `${results.length} results`}</span>
            <span>Page {data.page}</span>
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            {results.map((result) => <DiscoveryResultCard key={result.url} result={result} />)}
          </div>
          <nav className="flex flex-wrap items-center justify-center gap-3 border-t border-[#e6e5e3] pt-5 dark:border-[#3b3a37]" aria-label="Discovery result pages">
            <Button variant="secondary" disabled={loading || urlPage <= 1} onClick={() => goToPage(urlPage - 1)}>Previous</Button>
            <span className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">Page {urlPage}</span>
            <Button disabled={loading || !hasNextPage(data)} onClick={() => goToPage(urlPage + 1)}>Next</Button>
          </nav>
        </>
      )}
    </section>
  );
}
