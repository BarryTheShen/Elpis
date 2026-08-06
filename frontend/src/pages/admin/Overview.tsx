import { useEffect, useRef, useState } from 'preact/hooks';
import { Link } from 'wouter';
import { Badge } from '../../components/Badge';
import { Button } from '../../components/Button';
import { Card, CardHeader } from '../../components/Card';
import { Spinner } from '../../components/Spinner';
import { api } from '../../lib/api';
import { formatDigestLabel } from '../../lib/dates';
import type {
  DigestRunState,
  DigestRunSummary,
  Source,
} from '../../lib/types';

function statusLabel(state: DigestRunState): string {
  if (state === 'completed') return 'Completed';
  if (state === 'failed') return 'Failed';
  return 'Running';
}

function statusVariant(state: DigestRunState): 'ok' | 'error' | 'default' {
  if (state === 'completed') return 'ok';
  if (state === 'failed') return 'error';
  return 'default';
}

function numberStat(
  stats: Record<string, unknown>,
  key: string,
): number | null {
  const value = stats[key];
  return typeof value === 'number' ? value : null;
}

function processingTime(stats: Record<string, unknown>): string | null {
  const value = stats.processing_time;
  return typeof value === 'string' ? value : null;
}

export function OverviewPage() {
  const [runs, setRuns] = useState<DigestRunSummary[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadSequence = useRef(0);

  async function load(initial = false) {
    const sequence = ++loadSequence.current;
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const [nextRuns, nextSources] = await Promise.all([
        api.listDigestRuns(30),
        api.listSources(),
      ]);
      if (sequence !== loadSequence.current) return;
      setRuns(nextRuns);
      setSources(nextSources);
    } catch (err) {
      if (sequence !== loadSequence.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load overview.');
    } finally {
      if (sequence === loadSequence.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }

  useEffect(() => {
    void load(true);
    const refreshAfterRun = () => void load();
    window.addEventListener('digest:started', refreshAfterRun);
    window.addEventListener('digest:completed', refreshAfterRun);
    return () => {
      window.removeEventListener('digest:started', refreshAfterRun);
      window.removeEventListener('digest:completed', refreshAfterRun);
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" className="text-blue-600 dark:text-blue-400" />
      </div>
    );
  }

  const latest = runs[0] ?? null;
  const enabledSources = sources.filter((source) => source.enabled !== 0);
  const failedSources = enabledSources.filter(
    (source) => source.last_status === 'error',
  );
  const checkedSources = enabledSources.filter(
    (source) => source.last_status === 'ok' || source.last_status === 'error',
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8]">
            System overview
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#2c2c2b] dark:text-[#f4f3f1]">
            Digest operations
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#7d7a75] dark:text-[#b4b1ab]">
            See whether the latest run completed, which sources responded, and
            where to investigate when something failed.
          </p>
        </div>
        <Button
          size="sm"
          variant="secondary"
          loading={refreshing}
          onClick={() => void load()}
        >
          Refresh
        </Button>
      </div>

      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#f4c6c1] bg-[#fff1ef] px-4 py-3 text-sm text-[#b9382f] dark:border-[#7e3f37] dark:bg-[#4a2521] dark:text-[#ff9f96]">
          <span>{error}</span>
          <button
            type="button"
            className="font-semibold underline underline-offset-2"
            onClick={() => void load()}
          >
            Retry
          </button>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Latest digest run"
            description="The most recent scheduled or manual run."
          />
          {latest ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Badge variant={statusVariant(latest.state)}>
                    {statusLabel(latest.state)}
                  </Badge>
                  <span className="text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                    Run #{latest.id}
                  </span>
                </div>
                <span className="text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                  {formatDigestLabel(latest.finished_at ?? latest.started_at)}
                </span>
              </div>

              <p className="text-sm leading-6 text-[#5f5c57] dark:text-[#d0cdc6]">
                {latest.message || 'No run details available.'}
              </p>

              {latest.state === 'completed' && (
                <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-[#e6e5e3] pt-3 text-xs text-[#7d7a75] dark:border-[#3b3a37] dark:text-[#b4b1ab]">
                  {numberStat(latest.stats, 'articles_count') != null && (
                    <span>
                      {numberStat(latest.stats, 'articles_count')} articles
                    </span>
                  )}
                  {processingTime(latest.stats) && (
                    <span>{processingTime(latest.stats)}</span>
                  )}
                  {latest.digest_id != null && (
                    <span>Digest #{latest.digest_id}</span>
                  )}
                </div>
              )}

              {latest.state === 'failed' && latest.error && (
                <p className="break-words rounded-md bg-[#fff1ef] px-3 py-2 text-xs leading-5 text-[#b9382f] dark:bg-[#4a2521] dark:text-[#ff9f96]">
                  {latest.error}
                </p>
              )}

              <div className="flex flex-wrap gap-3 text-xs font-semibold">
                {latest.digest_id != null && (
                  <Link
                    href={`/?id=${latest.digest_id}`}
                    className="text-[#1d5f9f] hover:underline dark:text-[#a6d2f8]"
                  >
                    View digest
                  </Link>
                )}
                {latest.log_id != null && (
                  <Link
                    href="/admin/logs"
                    className="text-[#1d5f9f] hover:underline dark:text-[#a6d2f8]"
                  >
                    View logs
                  </Link>
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm leading-6 text-[#7d7a75] dark:text-[#b4b1ab]">
                No digest runs have been recorded yet.
              </p>
              <Link
                href="/admin/sources"
                className="inline-flex text-sm font-semibold text-[#1d5f9f] hover:underline dark:text-[#a6d2f8]"
              >
                Configure sources
              </Link>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Source health"
            description="Results from the latest collection run."
          />
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div>
                <p className="text-xl font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]">
                  {enabledSources.length}
                </p>
                <p className="mt-1 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                  Enabled
                </p>
              </div>
              <div>
                <p className="text-xl font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]">
                  {checkedSources.length}
                </p>
                <p className="mt-1 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                  Checked
                </p>
              </div>
              <div>
                <p className="text-xl font-semibold text-[#b9382f] dark:text-[#ff9f96]">
                  {failedSources.length}
                </p>
                <p className="mt-1 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                  Failed
                </p>
              </div>
            </div>

            {failedSources.length > 0 ? (
              <div className="space-y-2 border-t border-[#e6e5e3] pt-3 dark:border-[#3b3a37]">
                {failedSources.slice(0, 4).map((source) => (
                  <div
                    key={source.id}
                    className="flex items-start justify-between gap-3 text-sm"
                  >
                    <span className="min-w-0 truncate text-[#5f5c57] dark:text-[#d0cdc6]">
                      {source.name}
                    </span>
                    <span
                      className="max-w-[12rem] truncate text-xs text-[#b9382f] dark:text-[#ff9f96]"
                      title={source.last_error ?? ''}
                    >
                      {source.last_error || 'Collection failed'}
                    </span>
                  </div>
                ))}
                {failedSources.length > 4 && (
                  <p className="text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                    +{failedSources.length - 4} more failed sources
                  </p>
                )}
              </div>
            ) : (
              <p className="border-t border-[#e6e5e3] pt-3 text-sm text-[#7d7a75] dark:border-[#3b3a37] dark:text-[#b4b1ab]">
                {checkedSources.length === 0
                  ? 'Sources have not been checked yet.'
                  : 'No source failures recorded in the latest checks.'}
              </p>
            )}

            <Link
              href="/admin/sources"
              className="inline-flex text-xs font-semibold text-[#1d5f9f] hover:underline dark:text-[#a6d2f8]"
            >
              Manage sources
            </Link>
          </div>
        </Card>
      </div>

      <Card noPad>
        <div className="px-5 pt-5">
          <CardHeader
            title="Recent runs"
            description="A durable history remains available after a server restart."
          />
        </div>
        {runs.length === 0 ? (
          <p className="px-5 pb-5 text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
            Run a digest to start building history.
          </p>
        ) : (
          <div className="divide-y divide-[#e6e5e3] dark:divide-[#3b3a37]">
            {runs.map((run) => (
              <div key={run.id} className="px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Badge variant={statusVariant(run.state)}>
                      {statusLabel(run.state)}
                    </Badge>
                    <span className="text-sm font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]">
                      Run #{run.id}
                    </span>
                    {run.digest_id != null && (
                      <span className="text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                        Digest #{run.digest_id}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                    {formatDigestLabel(run.finished_at ?? run.started_at)}
                  </span>
                </div>
                <p className="mt-2 text-sm text-[#5f5c57] dark:text-[#d0cdc6]">
                  {run.message || 'No run details available.'}
                </p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                  {numberStat(run.stats, 'articles_count') != null && (
                    <span>{numberStat(run.stats, 'articles_count')} articles</span>
                  )}
                  {processingTime(run.stats) && (
                    <span>{processingTime(run.stats)}</span>
                  )}
                  {run.digest_id != null && (
                    <Link
                      href={`/?id=${run.digest_id}`}
                      className="font-semibold text-[#1d5f9f] hover:underline dark:text-[#a6d2f8]"
                    >
                      Open digest
                    </Link>
                  )}
                  {run.log_id != null && (
                    <Link
                      href="/admin/logs"
                      className="font-semibold text-[#1d5f9f] hover:underline dark:text-[#a6d2f8]"
                    >
                      Open logs
                    </Link>
                  )}
                </div>
                {run.state === 'failed' && run.error && (
                  <p
                    className="mt-2 truncate text-xs text-[#b9382f] dark:text-[#ff9f96]"
                    title={run.error}
                  >
                    {run.error}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
