import { useState, useEffect } from 'preact/hooks';
import { api } from '../../lib/api';
import type { BudgetData, BudgetLimits } from '../../lib/types';
import { Card, CardHeader } from '../../components/Card';
import { Button } from '../../components/Button';
import { Spinner } from '../../components/Spinner';
import { formatDigestLabel } from '../../lib/dates';

const INPUT =
  'w-full px-3 py-2 text-sm bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500';

function fmt(usd: number): string {
  if (usd === 0) return '$0.00';
  if (usd < 0.001) return `$${usd.toFixed(6)}`;
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(4)}`;
}

function fmtCredits(v: number | null | undefined): string {
  if (v == null) return 'unlimited';
  return fmt(v / 1000);
}

interface BarProps {
  used: number;
  limit: number | null;
  label: string;
}

function UsageBar({ used, limit, label }: BarProps) {
  const pct = limit && limit > 0 ? Math.min((used / limit) * 100, 100) : null;
  const color =
    pct == null
      ? 'bg-blue-500'
      : pct > 90
        ? 'bg-red-500'
        : pct > 70
          ? 'bg-amber-500'
          : 'bg-blue-500';

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
        <span>{label}</span>
        <span>
          {fmt(used)}{limit != null ? ` / ${fmt(limit)}` : ''}
        </span>
      </div>
      {pct != null && (
        <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${color}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

export function BudgetPage() {
  const [budget, setBudget] = useState<BudgetData | null>(null);
  const [limits, setLimits] = useState<BudgetLimits | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingLimits, setSavingLimits] = useState(false);
  const [limitsFlash, setLimitsFlash] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    Promise.all([api.getBudget(), api.getBudgetLimits()])
      .then(([b, l]) => {
        setBudget(b);
        setLimits(l);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : 'Failed to load budget data.');
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleSaveLimits(e: Event) {
    e.preventDefault();
    if (!limits) return;
    setSavingLimits(true);
    try {
      await api.saveBudgetLimits(limits);
      setLimitsFlash({ text: 'Limits saved.', ok: true });
    } catch (err) {
      setLimitsFlash({
        text: err instanceof Error ? err.message : 'Save failed.',
        ok: false,
      });
    } finally {
      setSavingLimits(false);
      setTimeout(() => setLimitsFlash(null), 4000);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" className="text-blue-600 dark:text-blue-400" />
      </div>
    );
  }

  if (error || !budget) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400 p-4">
        {error ?? 'Unknown error'}
      </p>
    );
  }

  const { openrouter, local } = budget;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
          Budget
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          OpenRouter spending and local pipeline cost tracking.
        </p>
      </div>

      {/* OpenRouter account usage */}
      {openrouter ? (
        <Card>
          <CardHeader title="OpenRouter account" />
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-lg font-bold text-slate-900 dark:text-slate-100">
                  {fmtCredits(openrouter.usage_daily)}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">Today</p>
              </div>
              <div>
                <p className="text-lg font-bold text-slate-900 dark:text-slate-100">
                  {fmtCredits(openrouter.usage_weekly)}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">This week</p>
              </div>
              <div>
                <p className="text-lg font-bold text-slate-900 dark:text-slate-100">
                  {fmtCredits(openrouter.usage_monthly)}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">This month</p>
              </div>
            </div>
            {openrouter.limit != null && (
              <UsageBar
                used={openrouter.limit - (openrouter.limit_remaining ?? openrouter.limit)}
                limit={openrouter.limit}
                label="Credit limit"
              />
            )}
            {openrouter.is_free_tier && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                Free tier key detected. Add credits at openrouter.ai for higher rate limits.
              </p>
            )}
          </div>
        </Card>
      ) : (
        <Card>
          <CardHeader title="OpenRouter account" />
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No OpenRouter API key configured. Add one in{' '}
            <a href="/admin/providers" className="text-blue-600 dark:text-blue-400 hover:underline">Providers</a>.
          </p>
        </Card>
      )}

      {/* Local budget limits - usage + editable caps */}
      <Card>
        <CardHeader title="Pipeline budget limits" />
        <div className="space-y-3">
          <UsageBar
            used={local.today_usd}
            limit={local.daily_limit_usd}
            label="Daily"
          />
          <UsageBar
            used={local.month_usd}
            limit={local.monthly_limit_usd}
            label="Monthly"
          />
          {local.avg_cost_per_digest_usd > 0 && (
            <div className="flex items-center justify-between pt-1 border-t border-slate-100 dark:border-slate-800">
              <span className="text-xs text-slate-500 dark:text-slate-400">
                Avg cost per digest (all time)
              </span>
              <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                {fmt(local.avg_cost_per_digest_usd)}
              </span>
            </div>
          )}
        </div>

        {limits && (
          <form onSubmit={handleSaveLimits} className="mt-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Daily limit (USD)
                </span>
                <input
                  type="number"
                  className={INPUT}
                  min={0}
                  step={0.01}
                  required
                  value={limits.daily_budget_usd}
                  onInput={(e) =>
                    setLimits((p) =>
                      p
                        ? {
                            ...p,
                            daily_budget_usd: parseFloat(
                              (e.target as HTMLInputElement).value,
                            ) || 0,
                          }
                        : p,
                    )
                  }
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Monthly limit (USD)
                </span>
                <input
                  type="number"
                  className={INPUT}
                  min={0}
                  step={0.01}
                  required
                  value={limits.monthly_budget_usd}
                  onInput={(e) =>
                    setLimits((p) =>
                      p
                        ? {
                            ...p,
                            monthly_budget_usd: parseFloat(
                              (e.target as HTMLInputElement).value,
                            ) || 0,
                          }
                        : p,
                    )
                  }
                />
              </label>
            </div>
            <div className="flex items-center gap-3">
              <Button type="submit" size="sm" loading={savingLimits}>
                Save limits
              </Button>
              {limitsFlash && (
                <span
                  className={`text-xs ${limitsFlash.ok ? 'text-blue-600 dark:text-blue-400' : 'text-red-600 dark:text-red-400'}`}
                >
                  {limitsFlash.text}
                </span>
              )}
            </div>
          </form>
        )}
      </Card>

      {/* Per-model breakdown */}
      {local.by_model.length > 0 && (
        <Card>
          <CardHeader title="Spend by model (all time)" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-slate-800">
                  <th className="pb-2 pr-4 font-semibold">Model</th>
                  <th className="pb-2 pr-4 font-semibold text-right">Requests</th>
                  <th className="pb-2 font-semibold text-right">Total cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {local.by_model.map((row) => (
                  <tr key={row.model}>
                    <td className="py-2 pr-4 font-mono text-xs text-slate-600 dark:text-slate-300">
                      {row.model || '(unknown)'}
                    </td>
                    <td className="py-2 pr-4 text-right text-slate-500 dark:text-slate-400">
                      {row.requests}
                    </td>
                    <td className="py-2 text-right font-medium text-slate-700 dark:text-slate-200">
                      {fmt(row.total_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Recent digest costs */}
      {local.recent_digests.length > 0 && (
        <Card>
          <CardHeader title="Recent digest costs" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-slate-800">
                  <th className="pb-2 pr-4 font-semibold">Digest</th>
                  <th className="pb-2 pr-4 font-semibold">Date</th>
                  <th className="pb-2 pr-4 font-semibold text-right">Articles</th>
                  <th className="pb-2 font-semibold text-right">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {local.recent_digests.map((d) => (
                  <tr key={d.digest_id}>
                    <td className="py-2 pr-4 text-slate-600 dark:text-slate-300">
                      #{d.digest_id}
                    </td>
                    <td className="py-2 pr-4 text-slate-500 dark:text-slate-400 text-xs">
                      {formatDigestLabel(d.created_at)}
                    </td>
                    <td className="py-2 pr-4 text-right text-slate-500 dark:text-slate-400">
                      {d.articles}
                    </td>
                    <td className="py-2 text-right font-medium text-slate-700 dark:text-slate-200">
                      {d.cost_usd > 0 ? fmt(d.cost_usd) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {local.by_model.length === 0 && local.recent_digests.length === 0 && (
        <Card>
          <p className="text-sm text-slate-500 dark:text-slate-400 py-2">
            No spending data yet. Run a digest with the OpenRouter provider to start tracking costs.
          </p>
        </Card>
      )}
    </div>
  );
}
