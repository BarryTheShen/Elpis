import { useComputed } from '@preact/signals';
import { useEffect, useRef, useState } from 'preact/hooks';
import { Link } from 'wouter';
import { api } from '../lib/api';
import type { DigestRunSummary, Job } from '../lib/types';
import { formatDigestLabel } from '../lib/dates';
import { jobSignal } from '../lib/signals';
import { Button } from './Button';

function runToJob(run: DigestRunSummary): Job {
  return {
    state: run.state,
    run_id: run.id,
    message: run.message,
    started_at: run.started_at,
    finished_at: run.finished_at,
    stats: run.stats,
    digest_id: run.digest_id,
    error: run.error,
    log_id: run.log_id,
  };
}

function statusLabel(state: Job['state']): string {
  if (state === 'running') return 'Digest running';
  if (state === 'completed') return 'Digest ready';
  if (state === 'failed') return 'Digest failed';
  return '';
}

function statusClasses(state: Job['state']): string {
  if (state === 'completed') {
    return 'border-[#b9dfc5] bg-[#e8f6ee] text-[#23683b] dark:border-[#326b45] dark:bg-[#193a29] dark:text-[#9ad3ab]';
  }
  if (state === 'failed') {
    return 'border-[#f4c6c1] bg-[#fff1ef] text-[#b9382f] dark:border-[#7e3f37] dark:bg-[#4a2521] dark:text-[#ff9f96]';
  }
  return 'border-[#b8d8f3] bg-[#e5f2fc] text-[#1d5f9f] dark:border-[#2d5c87] dark:bg-[#1c3852] dark:text-[#a6d2f8]';
}

function numberStat(
  stats: Record<string, unknown> | null | undefined,
  key: string,
): number | null {
  const value = stats?.[key];
  return typeof value === 'number' ? value : null;
}

/** Run control plus persistent success/failure visibility. */
export function JobBanner() {
  const [isLoading, setIsLoading] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const job = useComputed(() => jobSignal.value);
  const [latestRun, setLatestRun] = useState<DigestRunSummary | null>(null);
  const [open, setOpen] = useState(false);
  const refreshEpoch = useRef(0);
  const startPending = useRef(false);
  const lastSeenRunId = useRef(jobSignal.value.run_id ?? 0);
  const runStartBaseline = useRef(0);
  const localStartFailure = useRef<Job | null>(null);

  useEffect(() => {
    let active = true;
    let requestInFlight = false;
    let previousState = jobSignal.value.state;
    let previousRunId = jobSignal.value.run_id ?? null;

    async function refresh(initial = false) {
      if (requestInFlight || startPending.current) return;
      requestInFlight = true;
      const epochAtRequest = refreshEpoch.current;
      try {
        const [status, latest] = await Promise.all([
          api.getJobStatus(),
          api.getLatestDigestRun(),
        ]);
        const observedRunId = Math.max(
          latest?.id ?? 0,
          status.run_id ?? 0,
        );
        if (observedRunId > 0) {
          lastSeenRunId.current = observedRunId;
        }
        if (
          !active ||
          startPending.current ||
          epochAtRequest !== refreshEpoch.current
        ) {
          return;
        }
        setHydrated(true);

        const wasRunning = previousState === 'running';
        previousState = status.state;
        setLatestRun(latest);
        const latestRunIsNew =
          latest != null && latest.id !== previousRunId;
        const latestRunStarted =
          latestRunIsNew && latest.state === 'running';
        const latestRunCompleted =
          latestRunIsNew && latest.state !== 'running';
        previousRunId = latest?.id ?? previousRunId;

        const backendRunId = Math.max(
          latest?.id ?? 0,
          status.run_id ?? 0,
        );
        const hasAuthoritativeRunningRun =
          status.state === 'running' && status.run_id != null;
        const hasNewPersistedRun =
          backendRunId > (runStartBaseline.current ?? 0);
        const hasNewRunAfterStart =
          localStartFailure.current != null &&
          (hasAuthoritativeRunningRun || hasNewPersistedRun);
        if (hasNewRunAfterStart) {
          localStartFailure.current = null;
          runStartBaseline.current = 0;
        }
        if (localStartFailure.current) {
          jobSignal.value = localStartFailure.current;
        } else {
          const statusRunId = status.run_id ?? null;
          const latestIsNewer =
            latest != null &&
            (status.state === 'idle' ||
              statusRunId == null ||
              latest.id > statusRunId);
          jobSignal.value = latestIsNewer ? runToJob(latest) : status;
        }

        if (!initial && latestRunStarted) {
          setOpen(true);
          window.dispatchEvent(new CustomEvent('digest:started'));
        }

        if (
          !initial &&
          (latestRunCompleted ||
            (wasRunning &&
              (status.state === 'completed' || status.state === 'failed')))
        ) {
          setOpen(true);
          window.dispatchEvent(
            new CustomEvent('digest:completed', { detail: status }),
          );
        }
      } catch {
        // Keep the last known result visible when status polling is unavailable.
      } finally {
        requestInFlight = false;
      }
    }

    void refresh(true);
    const interval = window.setInterval(() => void refresh(), 4000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  async function run() {
    if (!hydrated) return;
    runStartBaseline.current = Math.max(
      lastSeenRunId.current,
      latestRun?.id ?? 0,
      jobSignal.value.run_id ?? 0,
    );
    localStartFailure.current = null;
    refreshEpoch.current += 1;
    startPending.current = true;
    setIsLoading(true);
    setOpen(true);
    try {
      const res = await api.runDigest();
      if (res.job.run_id != null) {
        lastSeenRunId.current = Math.max(
          lastSeenRunId.current,
          res.job.run_id,
        );
      }
      jobSignal.value = res.job;
      window.dispatchEvent(new CustomEvent('digest:started'));
      if (res.job.state === 'completed' || res.job.state === 'failed') {
        window.dispatchEvent(
          new CustomEvent('digest:completed', { detail: res.job }),
        );
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Could not start digest.';
      jobSignal.value = { state: 'failed', message, error: message };
      localStartFailure.current = { state: 'failed', message, error: message };
      setOpen(true);
    } finally {
      startPending.current = false;
      refreshEpoch.current += 1;
      setIsLoading(false);
    }
  }

  const state = job.value.state;
  const showStatus = state !== 'idle';
  const matchingRun =
    latestRun?.id != null && latestRun.id === job.value.run_id
      ? latestRun
      : null;
  const stats = matchingRun?.stats ?? job.value.stats;
  const articles = numberStat(stats, 'articles_count');
  const processingTime =
    typeof stats?.processing_time === 'string' ? stats.processing_time : null;
  const runTimestamp =
    matchingRun?.finished_at ??
    job.value.finished_at ??
    matchingRun?.started_at ??
    job.value.started_at;
  const digestId = matchingRun?.digest_id ?? job.value.digest_id;
  const logId = matchingRun?.log_id ?? job.value.log_id;
  const error = matchingRun?.error || job.value.error;

  return (
    <div class="relative flex items-center gap-2">
      <Button
        size="sm"
        variant={state === 'running' ? 'ghost' : 'primary'}
        disabled={!hydrated || state === 'running'}
        loading={!hydrated || isLoading || state === 'running'}
        onClick={run}
      >
        {!hydrated
          ? 'Checking status…'
          : state === 'running'
            ? 'Running…'
            : 'Run digest'}

      </Button>
      {showStatus && (
        <div class="relative">
          <button
            type="button"
            aria-expanded={open}
            aria-label={statusLabel(state)}
            onClick={() => setOpen((value) => !value)}
            class={[
              'inline-flex h-8 items-center gap-1.5 rounded-md border px-2 text-xs font-semibold transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de]',
              statusClasses(state),
            ].join(' ')}
          >
            <span
              class={[
                'h-1.5 w-1.5 rounded-full',
                state === 'running' ? 'animate-pulse bg-current' : 'bg-current',
              ].join(' ')}
            />
            <span class="hidden sm:inline">{statusLabel(state)}</span>
          </button>

          {open && (
            <div
              role="status"
              class="absolute right-0 top-full z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-[#e6e5e3] bg-white p-4 text-left shadow-lg dark:border-[#3b3a37] dark:bg-[#20201e]"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]">
                    {statusLabel(state)}
                  </p>
                  {runTimestamp && (
                    <p class="mt-0.5 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                      {formatDigestLabel(runTimestamp)}
                    </p>
                  )}
                </div>
                <span
                  class={[
                    'rounded-md px-2 py-0.5 text-xs font-semibold',
                    state === 'completed'
                      ? 'bg-[#e8f6ee] text-[#23683b] dark:bg-[#193a29] dark:text-[#9ad3ab]'
                      : state === 'failed'
                        ? 'bg-[#fff1ef] text-[#b9382f] dark:bg-[#4a2521] dark:text-[#ff9f96]'
                        : 'bg-[#e5f2fc] text-[#1d5f9f] dark:bg-[#1c3852] dark:text-[#a6d2f8]',
                  ].join(' ')}
                >
                  {state}
                </span>
              </div>

              <p class="mt-3 text-sm leading-6 text-[#5f5c57] dark:text-[#d0cdc6]">
                {job.value.message || 'No run details available.'}
              </p>

              {state === 'completed' && (
                <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
                  {articles != null && <span>{articles} articles</span>}
                  {processingTime && <span>{processingTime}</span>}
                  {digestId != null && <span>Digest #{digestId}</span>}
                </div>
              )}

              {state === 'failed' && error && (
                <p class="mt-3 break-words rounded-md bg-[#fff1ef] px-3 py-2 text-xs leading-5 text-[#b9382f] dark:bg-[#4a2521] dark:text-[#ff9f96]">
                  {error}
                </p>
              )}

              <div class="mt-4 flex flex-wrap gap-3 text-xs font-semibold">
                {digestId != null && (
                  <Link
                    href={`/admin/digest?id=${digestId}`}
                    class="text-[#1d5f9f] hover:underline dark:text-[#a6d2f8]"
                    onClick={() => setOpen(false)}
                  >
                    View digest
                  </Link>
                )}
                {logId != null && (
                  <Link
                    href="/admin/logs"
                    class="text-[#1d5f9f] hover:underline dark:text-[#a6d2f8]"
                    onClick={() => setOpen(false)}
                  >
                    View logs
                  </Link>
                )}
                <Link
                  href="/admin/overview"
                  class="text-[#1d5f9f] hover:underline dark:text-[#a6d2f8]"
                  onClick={() => setOpen(false)}
                >
                  Run dashboard
                </Link>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
