import { useEffect, useState } from 'preact/hooks';
import { Link } from 'wouter';
import { api } from '../../lib/api';
import type { ProviderDefinition, ProvidersConfig } from '../../lib/types';
import { Button } from '../../components/Button';
import { Card, CardHeader } from '../../components/Card';
import { Spinner } from '../../components/Spinner';

const INPUT =
  'w-full px-3 py-2 text-sm bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500';

function updateProvider(
  cfg: ProvidersConfig,
  id: string,
  update: (provider: ProviderDefinition) => ProviderDefinition,
): ProvidersConfig {
  return {
    ...cfg,
    providers: cfg.providers.map((provider) =>
      provider.id === id ? update(provider) : provider,
    ),
  };
}

export function ProvidersPage() {
  const [cfg, setCfg] = useState<ProvidersConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [keyValues, setKeyValues] = useState<Record<string, string>>({});
  const [pullModel, setPullModel] = useState('');
  const [pulling, setPulling] = useState(false);
  const [deleteModel, setDeleteModel] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  function load() {
    setLoading(true);
    api
      .getProviders()
      .then(setCfg)
      .catch((error: unknown) => {
        setFlash(error instanceof Error ? error.message : 'Failed to load providers.');
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  function showFlash(message: string) {
    setFlash(message);
    setTimeout(() => setFlash(null), 4000);
  }

  async function saveSettings(event: Event) {
    event.preventDefault();
    if (!cfg) return;
    setSaving(true);
    try {
      const endpoints = Object.fromEntries(
        cfg.providers.map((provider) => [provider.id, { base_url: provider.base_url }]),
      );
      await api.saveProviders({
        active_provider: cfg.active_provider,
        endpoints,
        openrouter_pick_cheapest: cfg.openrouter_pick_cheapest,
      });
      showFlash('Provider settings saved.');
      load();
    } catch (error) {
      showFlash(error instanceof Error ? error.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  }

  async function saveKey(provider: ProviderDefinition) {
    const value = (keyValues[provider.id] ?? '').trim();
    if (!value) return;
    setSavingKey(provider.id);
    try {
      await api.saveKey(provider.id, value);
      setKeyValues((previous) => ({ ...previous, [provider.id]: '' }));
      showFlash(`${provider.label} key saved.`);
      load();
    } catch (error) {
      showFlash(error instanceof Error ? error.message : 'Key save failed.');
    } finally {
      setSavingKey(null);
    }
  }

  async function deleteKey(provider: ProviderDefinition) {
    setSavingKey(`delete:${provider.id}`);
    try {
      await api.deleteKey(provider.id);
      showFlash(`${provider.label} saved key removed.`);
      load();
    } catch (error) {
      showFlash(error instanceof Error ? error.message : 'Key removal failed.');
    } finally {
      setSavingKey(null);
    }
  }

  async function pullOllama(event: Event) {
    event.preventDefault();
    if (!pullModel.trim()) return;
    setPulling(true);
    try {
      const result = await api.pullOllamaModel(pullModel.trim());
      showFlash(result.message);
      setPullModel('');
      load();
    } catch (error) {
      showFlash(error instanceof Error ? error.message : 'Ollama pull failed.');
    } finally {
      setPulling(false);
    }
  }

  async function deleteOllama(event: Event) {
    event.preventDefault();
    if (!deleteModel) return;
    setDeleting(true);
    try {
      const result = await api.deleteOllamaModel(deleteModel);
      showFlash(result.message);
      setDeleteModel('');
      load();
    } catch (error) {
      showFlash(error instanceof Error ? error.message : 'Ollama delete failed.');
    } finally {
      setDeleting(false);
    }
  }

  if (loading && !cfg) {
    return (
      <div class="flex items-center justify-center py-20">
        <Spinner size="lg" className="text-blue-600 dark:text-blue-400" />
      </div>
    );
  }

  if (!cfg) {
    return <p class="text-sm text-red-600 dark:text-red-400 p-4">{flash ?? 'Could not load providers.'}</p>;
  }

  return (
    <div class="space-y-5">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
          Providers
        </h1>
        <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Credentials, endpoints, and the active model backend live here. API keys are encrypted at rest.
        </p>
      </div>

      {flash && (
        <div class="px-4 py-3 text-sm rounded-lg bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
          {flash}
        </div>
      )}

      <Card>
        <CardHeader title="Active backend" description="Choose where Elpis sends model requests." />
        <form onSubmit={saveSettings} class="space-y-4">
          <label class="flex flex-col gap-1">
            <span class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Provider
            </span>
            <select
              class={INPUT}
              value={cfg.active_provider}
              onChange={(event) =>
                setCfg((previous) =>
                  previous
                    ? { ...previous, active_provider: (event.target as HTMLSelectElement).value }
                    : previous,
                )
              }
            >
              <option value="fallback">Fallback (Ollama, then OpenRouter)</option>
              {cfg.providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.label}
                </option>
              ))}
            </select>
          </label>

          <label class="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              class="mt-0.5"
              checked={cfg.openrouter_pick_cheapest}
              onChange={(event) =>
                setCfg((previous) =>
                  previous
                    ? {
                        ...previous,
                        openrouter_pick_cheapest: (event.target as HTMLInputElement).checked,
                      }
                    : previous,
                )
              }
            />
            <span>
              <span class="block text-sm text-slate-700 dark:text-slate-300">
                Let OpenRouter choose the cheapest suitable text model
              </span>
              {cfg.cheapest_model_id && (
                <span class="block mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Current catalog choice: <code class="font-mono">{cfg.cheapest_model_id}</code>
                </span>
              )}
            </span>
          </label>

          <Button type="submit" loading={saving}>
            Save provider settings
          </Button>
        </form>
      </Card>

      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {cfg.providers.map((provider) => (
          <Card key={provider.id}>
            <div class="flex items-start justify-between gap-3">
              <div>
                <h2 class="text-base font-semibold text-slate-900 dark:text-slate-100">
                  {provider.label}
                </h2>
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {provider.description}
                </p>
              </div>
              {cfg.active_provider === provider.id && (
                <span class="shrink-0 rounded-full bg-blue-100 px-2 py-1 text-[11px] font-semibold text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                  Active
                </span>
              )}
            </div>

            {provider.supports_base_url && (
              <label class="mt-4 flex flex-col gap-1">
                <span class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  API base URL
                </span>
                <input
                  class={INPUT}
                  value={provider.base_url}
                  placeholder={provider.default_base_url || 'https://your-server.example/v1'}
                  onInput={(event) =>
                    setCfg((previous) =>
                      previous
                        ? updateProvider(previous, provider.id, (current) => ({
                            ...current,
                            base_url: (event.target as HTMLInputElement).value,
                          }))
                        : previous,
                    )
                  }
                />
                <span class="text-xs text-slate-400 dark:text-slate-500">
                  {provider.id === 'custom'
                    ? 'Use the server base URL, usually ending in /v1.'
                    : provider.default_base_url
                      ? `Default: ${provider.default_base_url}`
                      : 'Leave blank to use the provider SDK default.'}
                </span>
              </label>
            )}

            {provider.requires_api_key ? (
              <form
                class="mt-4 flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  void saveKey(provider);
                }}
              >
                <input
                  type="password"
                  class={`${INPUT} flex-1`}
                  autoComplete="off"
                  aria-label={`${provider.label} API key`}
                  placeholder={provider.api_key_configured ? provider.key_preview : 'API key'}
                  value={keyValues[provider.id] ?? ''}
                  onInput={(event) =>
                    setKeyValues((previous) => ({
                      ...previous,
                      [provider.id]: (event.target as HTMLInputElement).value,
                    }))
                  }
                />
                <Button type="submit" size="sm" loading={savingKey === provider.id}>
                  Save key
                </Button>
              </form>
            ) : (
              <p class="mt-4 text-xs text-slate-500 dark:text-slate-400">
                No API key required. Local Ollama must be reachable from the Elpis process.
              </p>
            )}

            {provider.api_key_configured && provider.requires_api_key && (
              <div class="mt-2 flex items-center justify-between gap-3">
                <p class="text-xs text-emerald-600 dark:text-emerald-400">
                  Key configured: {provider.key_preview}
                </p>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={savingKey === `delete:${provider.id}`}
                  onClick={() => void deleteKey(provider)}
                >
                  Remove saved key
                </Button>
              </div>
            )}
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader
          title="Ollama models"
          description={`Manage models at ${cfg.ollama_host}. Model and reasoning choices stay on the LLM settings page.`}
        />
        {!cfg.ollama_reachable ? (
          <p class="text-sm text-amber-700 dark:text-amber-300">
            Ollama is not reachable. Start it locally or set its endpoint above.
          </p>
        ) : (
          <div class="space-y-3">
            <form onSubmit={pullOllama} class="flex gap-2">
              <input
                class={`${INPUT} flex-1`}
                placeholder="llama3.2:3b"
                value={pullModel}
                required
                onInput={(event) => setPullModel((event.target as HTMLInputElement).value)}
              />
              <Button type="submit" loading={pulling}>Pull</Button>
            </form>
            {cfg.ollama_models.length > 0 && (
              <form onSubmit={deleteOllama} class="flex gap-2">
                <select
                  class={`${INPUT} flex-1`}
                  value={deleteModel}
                  required
                  onChange={(event) => setDeleteModel((event.target as HTMLSelectElement).value)}
                >
                  <option value="">Select model to delete...</option>
                  {cfg.ollama_models.map((model) => <option key={model} value={model}>{model}</option>)}
                </select>
                <Button type="submit" variant="secondary" loading={deleting}>Delete</Button>
              </form>
            )}
          </div>
        )}
      </Card>

      <p class="text-xs text-slate-500 dark:text-slate-400">
        Configure output model and reasoning intensity in <Link href="/admin/llm" class="text-blue-600 hover:underline dark:text-blue-400">LLM settings</Link>.
      </p>
    </div>
  );
}
