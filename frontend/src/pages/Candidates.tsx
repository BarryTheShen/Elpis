import { useCallback, useEffect, useState } from 'preact/hooks';
import { Link, useSearch } from 'wouter';

import { CandidateCard } from '../components/CandidateCard';
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { Spinner } from '../components/Spinner';
import { api } from '../lib/api';
import type { CandidatePage as CandidatePageData } from '../lib/types';

const PAGE_SIZE = 24;

function parseDigestId(search: string): number | undefined {
  const value = new URLSearchParams(search).get('digest_id');
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function CandidateSkeleton() {
  return (
    <div className="grid gap-5 md:grid-cols-2" aria-label="Loading ranked candidates" aria-busy="true">
      {[0, 1, 2, 3].map((item) => (
        <div key={item} className="animate-pulse space-y-4 rounded-lg border border-[#e6e5e3] p-5 dark:border-[#3b3a37]">
          <div className="h-3 w-24 rounded bg-[#e6e5e3] dark:bg-[#3b3a37]" />
          <div className="h-5 w-4/5 rounded bg-[#e6e5e3] dark:bg-[#3b3a37]" />
          <div className="h-4 w-full rounded bg-[#f0efed] dark:bg-[#2a2927]" />
          <div className="h-4 w-11/12 rounded bg-[#f0efed] dark:bg-[#2a2927]" />
        </div>
      ))}
    </div>
  );
}

function hasNextPage(data: CandidatePageData): boolean {
  if (data.has_more != null) return data.has_more;
  if (data.next_page != null) return true;
  if (data.total != null) return data.page * data.limit < data.total;
  return data.candidates.length >= data.limit;
}

/** Authenticated publication view of every ranked candidate for an issue. */
export function CandidatesPage() {
  const search = useSearch();
  const digestId = parseDigestId(search);
  const [data, setData] = useState<CandidatePageData | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (requestedPage: number) => {
    setLoading(true);
    setError(null);
    try {
      const next = await api.listCandidates({
        digestId,
        page: requestedPage,
        limit: PAGE_SIZE,
      });
      setData(next);
      setPage(next.page || requestedPage);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Failed to load ranked candidates.');
    } finally {
      setLoading(false);
    }
  }, [digestId]);

  useEffect(() => {
    setPage(1);
    void load(1);
  }, [load]);

  const candidates = data?.candidates ?? [];
  const nextAvailable = data ? hasNextPage(data) : false;

  if (loading && !data) return <CandidateSkeleton />;

  if (error && !data) {
    return (
      <EmptyState
        title="Could not load ranked candidates"
        description={error}
        action={<Button onClick={() => void load(page)}>Retry</Button>}
      />
    );
  }

  return (
    <section className="space-y-8" aria-labelledby="candidates-heading">
      <header className="space-y-3">
        <p className="text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8]">Ranked reading</p>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 id="candidates-heading" className="text-4xl font-semibold tracking-[-0.035em] text-[#2c2c2b] dark:text-[#f4f3f1]">
              All candidates
            </h1>
            <p className="mt-2 max-w-prose text-base leading-7 text-[#7d7a75] dark:text-[#b4b1ab]">
              The full ranked set that passed your relevance gate. Briefed stories are marked so the selection remains transparent.
            </p>
          </div>
          <Link href="/" className="text-sm font-semibold text-[#1d5f9f] underline underline-offset-4 hover:text-[#164a7c] dark:text-[#a6d2f8]">
            Back to today
          </Link>
        </div>
        {data && (
          <p className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
            {data.total != null ? `${data.total} ranked candidates` : `Page ${data.page}`}
            {digestId != null ? ` · Issue #${digestId}` : ''}
          </p>
        )}
      </header>

      {error && data && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#f4c6c1] bg-[#fff1ef] px-4 py-3 text-sm text-[#8f3f34] dark:border-[#7e3f37] dark:bg-[#4a2521] dark:text-[#ffb9b1]" role="alert">
          <span>{error}</span>
          <Button variant="secondary" size="sm" onClick={() => void load(page)}>Retry</Button>
        </div>
      )}

      {loading && data ? <CandidateSkeleton /> : candidates.length === 0 ? (
        <EmptyState
          title="No ranked candidates yet"
          description="Candidates will appear here after a digest run passes the relevance gate."
          action={<Link href="/" className="inline-flex items-center rounded-md bg-[#2783de] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#1f6fbe] focus-visible:ring-2 focus-visible:ring-[#2783de] dark:bg-[#63aaf0] dark:text-[#171716]">Read today</Link>}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {candidates.map((candidate) => (
              <CandidateCard key={`${candidate.rank}-${candidate.url}`} candidate={candidate} />
            ))}
          </div>
          <nav className="flex flex-wrap items-center justify-center gap-3 border-t border-[#e6e5e3] pt-5 dark:border-[#3b3a37]" aria-label="Candidate pages">
            <Button
              variant="secondary"
              disabled={loading || page <= 1}
              onClick={() => void load(page - 1)}
            >
              Previous
            </Button>
            <span className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">Page {page}</span>
            <Button
              disabled={loading || !nextAvailable}
              onClick={() => void load(page + 1)}
            >
              Next
            </Button>
          </nav>
        </>
      )}

      {loading && data && <Spinner size="sm" className="mx-auto text-[#2783de] dark:text-[#63aaf0]" />}
    </section>
  );
}
