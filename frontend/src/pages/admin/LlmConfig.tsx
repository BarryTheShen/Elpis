import { useState, useEffect } from 'preact/hooks';
import { Link } from 'wouter';
import type { ComponentChildren } from 'preact';
import { api } from '../../lib/api';
import type { LlmConfig, ReasoningEffort } from '../../lib/types';
import { Card, CardHeader } from '../../components/Card';
import { Button } from '../../components/Button';
import { Spinner } from '../../components/Spinner';

const INPUT =
  'w-full px-3 py-2 text-sm bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500';

const REASONING_OPTIONS: Array<{ value: ReasoningEffort; label: string; hint: string }> = [
  { value: 'none', label: 'Off', hint: 'Fastest response with no explicit reasoning request.' },
  { value: 'minimal', label: 'Minimal', hint: 'Small reasoning budget for simple decisions.' },
  { value: 'low', label: 'Low', hint: 'Light reasoning with modest latency.' },
  { value: 'medium', label: 'Medium', hint: 'Balanced quality and latency.' },
  { value: 'high', label: 'High', hint: 'More deliberate reasoning for difficult articles.' },
  { value: 'xhigh', label: 'Extra high', hint: 'Maximum supported effort on capable models.' },
];

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ComponentChildren;
}) {
  return (
    <label class="flex flex-col gap-1">
      <span class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </span>
      {children}
      {hint && <span class="text-xs text-slate-400 dark:text-slate-500">{hint}</span>}
    </label>
  );
}

export function LlmConfigPage() {
  const [cfg, setCfg] = useState<LlmConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    api
      .getLlmConfig()
      .then(setCfg)
      .catch((error: unknown) => {
        setFlash(error instanceof Error ? error.message : 'Failed to load LLM settings.');
      })
      .finally(() => setLoading(false));
  }, []);

  function showFlash(message: string) {
    setFlash(message);
    setTimeout(() => setFlash(null), 4000);
  }

  async function handleSave(event: Event) {
    event.preventDefault();
    if (!cfg) return;
    setSaving(true);
    try {
      await api.saveLlmConfig(cfg);
      showFlash('LLM settings saved.');
    } catch (error) {
      showFlash(error instanceof Error ? error.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div class="flex items-center justify-center py-20">
        <Spinner size="lg" className="text-blue-600 dark:text-blue-400" />
      </div>
    );
  }

  if (!cfg) {
    return (
      <p class="text-sm text-red-600 dark:text-red-400 p-4">
        {flash ?? 'Could not load LLM settings.'}
      </p>
    );
  }

  const selectedReasoning =
    REASONING_OPTIONS.find((option) => option.value === cfg.reasoning_effort) ??
    REASONING_OPTIONS[0];

  return (
    <div class="space-y-5">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
          LLM settings
        </h1>
        <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Choose the model and how much reasoning it should use. Credentials and endpoints are managed in{' '}
          <Link href="/admin/providers" class="text-blue-600 hover:underline dark:text-blue-400">
            Providers
          </Link>.
        </p>
      </div>

      {flash && (
        <div class="px-4 py-3 text-sm rounded-lg bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
          {flash}
        </div>
      )}

      <Card>
        <CardHeader title="Model output" />
        <form onSubmit={handleSave} class="space-y-5">
          <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-800/50">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Active provider
            </p>
            <p class="mt-1 text-sm font-medium text-slate-900 dark:text-slate-100">
              {cfg.provider}
            </p>
          </div>

          <Field
            label="Model"
            hint="Use the model identifier expected by the active provider. OpenRouter IDs look like provider/model."
          >
            <input
              class={INPUT}
              value={cfg.model}
              required
              onInput={(event) =>
                setCfg((previous) =>
                  previous
                    ? { ...previous, model: (event.target as HTMLInputElement).value }
                    : previous,
                )
              }
            />
          </Field>

          <Field label="Reasoning effort" hint={selectedReasoning.hint}>
            <select
              class={INPUT}
              value={cfg.reasoning_effort}
              onChange={(event) =>
                setCfg((previous) =>
                  previous
                    ? {
                        ...previous,
                        reasoning_effort: (event.target as HTMLSelectElement)
                          .value as ReasoningEffort,
                      }
                    : previous,
                )
              }
            >
              {REASONING_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field
              label="Extended thinking"
              hint="Passes a provider-neutral thinking budget when supported."
            >
              <label class="flex items-center gap-2 min-h-10 text-sm text-slate-700 dark:text-slate-300">
                <input
                  type="checkbox"
                  checked={cfg.thinking_enabled}
                  onChange={(event) =>
                    setCfg((previous) =>
                      previous
                        ? {
                            ...previous,
                            thinking_enabled: (event.target as HTMLInputElement).checked,
                          }
                        : previous,
                    )
                  }
                />
                Enable thinking tokens
              </label>
            </Field>

            <Field
              label="Thinking token budget"
              hint="0 lets the provider choose. Range: 0-100000 tokens."
            >
              <input
                class={INPUT}
                type="number"
                min="0"
                max="100000"
                step="1"
                value={cfg.thinking_budget_tokens}
                onInput={(event) =>
                  setCfg((previous) =>
                    previous
                      ? {
                          ...previous,
                          thinking_budget_tokens: Number(
                            (event.target as HTMLInputElement).value,
                          ),
                        }
                      : previous,
                  )
                }
              />
            </Field>
          </div>

          <div class="rounded-lg bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-600 dark:bg-slate-800/50 dark:text-slate-400">
            LiteLLM normalizes reasoning controls across OpenRouter, OpenAI, Anthropic, Gemini, local Ollama, and custom OpenAI-compatible servers. Providers that do not support a control safely ignore it.
          </div>

          <Button type="submit" loading={saving}>
            Save LLM settings
          </Button>
        </form>
      </Card>
    </div>
  );
}
