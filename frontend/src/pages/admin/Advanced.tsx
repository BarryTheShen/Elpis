import { useEffect, useState } from 'preact/hooks';

import { Button } from '../../components/Button';
import { Card, CardHeader } from '../../components/Card';
import { Spinner } from '../../components/Spinner';
import { api } from '../../lib/api';
import type { NetworkConfig, NetworkTestResult } from '../../lib/types';

const INPUT =
  'w-full px-3 py-2 text-sm bg-white dark:bg-slate-950 border border-slate-200' +
  ' dark:border-slate-700 rounded-lg text-slate-900 dark:text-slate-100' +
  ' focus:outline-none focus:ring-2 focus:ring-blue-500';

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: preact.ComponentChildren;
}) {
  return (
    <label className='flex flex-col gap-1'>
      <span className='text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400'>
        {label}
      </span>
      {children}
      {hint && (
        <span className='text-xs leading-relaxed text-slate-400 dark:text-slate-500'>
          {hint}
        </span>
      )}
    </label>
  );
}

function sourceLabel(config: NetworkConfig): string {
  if (config.proxy_source === 'database') return 'Saved in Elpis';
  if (config.proxy_source === 'environment') return 'Inherited from environment';
  return 'Disabled';
}

export function AdvancedPage() {
  const [config, setConfig] = useState<NetworkConfig | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [proxyUrl, setProxyUrl] = useState('');
  const [bypassHosts, setBypassHosts] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [flash, setFlash] = useState<{ text: string; ok: boolean } | null>(null);
  const [testResult, setTestResult] = useState<NetworkTestResult | null>(null);

  function showFlash(text: string, ok = true) {
    setFlash({ text, ok });
    window.setTimeout(() => setFlash(null), 5000);
  }

  useEffect(() => {
    api
      .getNetworkConfig()
      .then((value) => {
        if (!value || !Array.isArray(value.bypass_hosts)) {
          throw new Error('Network settings response was invalid.');
        }
        setConfig(value);
        setEnabled(value.enabled);
        setBypassHosts(value.bypass_hosts.join(', '));
      })
      .catch((error: unknown) => {
        showFlash(
          error instanceof Error ? error.message : 'Failed to load network settings.',
          false,
        );
      })
      .finally(() => setLoading(false));
  }, []);

  async function save(event: Event) {
    event.preventDefault();
    setSaving(true);
    setTestResult(null);
    try {
      const value = await api.saveNetworkConfig({
        enabled,
        proxy_url: proxyUrl.trim(),
        bypass_hosts: bypassHosts,
      });
      setConfig(value);
      setProxyUrl('');
      setBypassHosts(value.bypass_hosts.join(', '));
      showFlash('Network settings saved. The next digest run will use the new policy.');
    } catch (error: unknown) {
      showFlash(error instanceof Error ? error.message : 'Failed to save network settings.', false);
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.testNetwork({
        enabled,
        proxy_url: proxyUrl.trim(),
        bypass_hosts: bypassHosts,
      });
      setTestResult(result);
      showFlash(
        `Connection succeeded via ${result.proxy_used ? 'the configured proxy' : 'a direct connection'} (${result.elapsed_ms ?? 0} ms).`,
      );
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Proxy connection failed.';
      setTestResult({ ok: false, proxy_used: enabled, error: message });
      showFlash(message, false);
    } finally {
      setTesting(false);
    }
  }

  if (loading) {
    return (
      <div className='flex justify-center py-20'>
        <Spinner size='md' />
      </div>
    );
  }

  return (
    <div className='max-w-3xl space-y-6'>
      <header>
        <p className='text-xs font-semibold uppercase tracking-[0.12em] text-[#7d7a75] dark:text-[#b4b1ab]'>
          System
        </p>
        <h1 className='mt-1 text-2xl font-semibold tracking-tight text-[#2c2c2b] dark:text-[#f4f3f1]'>
          Advanced settings
        </h1>
        <p className='mt-2 text-sm leading-6 text-[#7d7a75] dark:text-[#b4b1ab]'>
          Control outbound network access for feed collection, article fetching,
          YouTube, model providers, and command-line downloaders.
        </p>
      </header>

      {flash && (
        <div
          role='status'
          className={[
            'rounded-lg border px-4 py-3 text-sm',
            flash.ok
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200'
              : 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200',
          ].join(' ')}
        >
          {flash.text}
        </div>
      )}

      <Card>
        <CardHeader
          title='Network & proxy'
          description='Shared proxy policy for Elpis-managed outbound requests.'
        />
        <form onSubmit={save} className='space-y-5'>
          <label className='flex items-start gap-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700'>
            <input
              type='checkbox'
              className='mt-1 h-4 w-4 accent-blue-600'
              checked={enabled}
              onChange={(event) => setEnabled((event.target as HTMLInputElement).checked)}
            />
            <span>
              <span className='block text-sm font-semibold text-slate-800 dark:text-slate-200'>
                Route outbound traffic through a proxy
              </span>
              <span className='mt-1 block text-xs leading-relaxed text-slate-500 dark:text-slate-400'>
                HTTP(S) and SOCKS5 proxy URLs are supported. The setting is applied to
                Elpis-managed HTTPX clients, urllib, requests, YouTubeTranscriptApi,
                yt-dlp, and model APIs.
              </span>
            </span>
          </label>

          <Field
            label='Proxy URL'
            hint='Enter the complete URL when changing it, for example http://user:password@proxy.example:8080. Credentials are encrypted and never shown again.'
          >
            <input
              type='url'
              className={INPUT}
              aria-label='Proxy URL'
              value={proxyUrl}
              onInput={(event) => setProxyUrl((event.target as HTMLInputElement).value)}
              placeholder={config?.proxy_url_display ?? 'http://proxy.example:8080'}
              disabled={!enabled}
              autoComplete='off'
            />
          </Field>

          <Field
            label='Bypass hosts'
            hint='Comma- or newline-separated hostnames. localhost, 127.0.0.1, ::1, and host.docker.internal are always bypassed so local Ollama remains reachable.'
          >
            <textarea
              className={INPUT + ' min-h-[88px] resize-y leading-relaxed'}
              aria-label='Proxy bypass hosts'
              value={bypassHosts}
              onInput={(event) => setBypassHosts((event.target as HTMLTextAreaElement).value)}
              placeholder='localhost, 127.0.0.1, ::1, host.docker.internal'
              rows={3}
            />
          </Field>

          <div className='flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4 dark:border-slate-700'>
            <div className='text-xs text-slate-500 dark:text-slate-400'>
              Current source: <span className='font-semibold'>{config ? sourceLabel(config) : 'Unknown'}</span>
              {config?.youtube_proxy_override && (
                <span className='ml-2 text-amber-700 dark:text-amber-300'>
                  YouTube has an explicit environment override.
                </span>
              )}
            </div>
            <div className='flex gap-2'>
              <Button type='submit' loading={saving}>
                Save settings
              </Button>
              <Button type='button' variant='secondary' loading={testing} onClick={testConnection}>
                Test form settings
              </Button>
            </div>
          </div>
        </form>
      </Card>

      {testResult && (
        <Card>
          <CardHeader title='Latest connection test' />
          <div className={testResult.ok ? 'text-sm text-emerald-700 dark:text-emerald-300' : 'text-sm text-red-700 dark:text-red-300'}>
            {testResult.ok
              ? `HTTP ${testResult.status_code} from ${testResult.target ?? 'the test endpoint'} in ${testResult.elapsed_ms ?? 0} ms.`
              : testResult.error ?? 'The proxy test failed.'}
          </div>
        </Card>
      )}

      <Card>
        <CardHeader title='Safety notes' />
        <ul className='list-disc space-y-2 pl-5 text-sm leading-relaxed text-slate-600 dark:text-slate-300'>
          <li>Proxy credentials are encrypted with Elpis&apos; existing data key.</li>
          <li>Credentials are masked in the API response, logs, and this page.</li>
          <li>Fresh installs with no saved or environment policy start disabled; existing environment policies are detected.</li>
          <li>Test form settings is ephemeral and never writes the database.</li>
          <li>Save settings persists the encrypted policy across restarts, refreshes the running environment, and applies to the next digest run.</li>
          <li>Use bypass hosts for private services that should never leave the machine or Docker network.</li>
        </ul>
      </Card>
    </div>
  );
}
