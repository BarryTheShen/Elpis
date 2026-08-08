import { useEffect, useState } from 'preact/hooks';

import { Button } from '../../components/Button';
import { EmptyState } from '../../components/EmptyState';
import { Spinner } from '../../components/Spinner';
import { api } from '../../lib/api';
import type { MonitorQuery, MonitorQueryInput, MonitorScope } from '../../lib/types';
import { formatDigestLabel } from '../../lib/dates';

const EMPTY_FORM: MonitorQueryInput = {
  question: '',
  search_query: '',
  scope: 'both',
  enabled: true,
  cadence_minutes: 360,
  include_keywords: [],
  exclude_keywords: [],
  category: '',
  language: '',
  country: '',
  max_items: 20,
};

function displayTime(value?: string | null): string {
  return value ? formatDigestLabel(value) : '—';
}

function formFromQuery(query: MonitorQuery): MonitorQueryInput {
  return {
    question: query.question,
    search_query: query.search_query,
    scope: query.scope,
    enabled: query.enabled,
    cadence_minutes: query.cadence_minutes,
    include_keywords: Array.isArray(query.include_keywords) ? query.include_keywords : [],
    exclude_keywords: Array.isArray(query.exclude_keywords) ? query.exclude_keywords : [],
    category: query.category,
    language: query.language,
    country: query.country,
    max_items: query.max_items,
  };
}

/** Desktop-only monitor query CRUD and manual checks. */
export function MonitoringAdminPage() {
  const [queries, setQueries] = useState<MonitorQuery[]>([]);
  const [form, setForm] = useState<MonitorQueryInput>({ ...EMPTY_FORM });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ text: string; ok: boolean } | null>(null);

  function showFlash(text: string, ok = true) {
    setFlash({ text, ok });
    window.setTimeout(() => setFlash(null), 4500);
  }

  async function loadQueries() {
    setLoading(true);
    setError(null);
    try {
      setQueries(await api.listMonitoring());
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Failed to load monitoring questions.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadQueries(); }, []);

  function startCreate() {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setFormOpen(true);
    setError(null);
  }

  function startEdit(query: MonitorQuery) {
    setEditingId(query.id);
    setForm(formFromQuery(query));
    setFormOpen(true);
    setError(null);
  }

  async function saveForm(event: Event) {
    event.preventDefault();
    const question = form.question.trim();
    const searchQuery = form.search_query.trim();
    if (!question || !searchQuery) {
      setError('Question and search query are required.');
      return;
    }
    const payload: MonitorQueryInput = {
      ...form,
      question,
      cadence_minutes: Math.max(1, Math.round(Number(form.cadence_minutes) || 0)),
      max_items: Math.max(1, Math.min(100, Math.round(Number(form.max_items) || 0))),
      include_keywords: form.include_keywords,
      exclude_keywords: form.exclude_keywords,
      category: form.category.trim(),
      language: form.language.trim(),
      country: form.country.trim(),
    };
    setSaving(true);
    setError(null);
    try {
      const saved = editingId == null
        ? await api.createMonitoring(payload)
        : await api.updateMonitoring(editingId, payload);
      setQueries((current) => editingId == null ? [...current, saved] : current.map((query) => query.id === editingId ? saved : query));
      setFormOpen(false);
      setEditingId(null);
      showFlash(editingId == null ? 'Monitoring question created.' : 'Monitoring question updated.');
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Could not save monitoring question.');
    } finally {
      setSaving(false);
    }
  }

  async function toggleQuery(query: MonitorQuery) {
    setBusyId(query.id);
    setError(null);
    try {
      const updated = await api.updateMonitoring(query.id, { enabled: !query.enabled });
      setQueries((current) => current.map((item) => item.id === query.id ? updated : item));
      showFlash(updated.enabled ? 'Monitoring resumed.' : 'Monitoring paused.');
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Could not change monitoring status.');
    } finally {
      setBusyId(null);
    }
  }

  async function checkNow(query: MonitorQuery) {
    setBusyId(query.id);
    setError(null);
    try {
      const updated = await api.checkMonitoring(query.id);
      setQueries((current) => current.map((item) => item.id === query.id ? updated : item));
      showFlash(`Checked “${query.question}”.`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Could not check monitoring question.');
    } finally {
      setBusyId(null);
    }
  }

  async function deleteQuery(query: MonitorQuery) {
    if (!window.confirm(`Delete “${query.question}”? Its result history will also be removed.`)) return;
    setBusyId(query.id);
    setError(null);
    try {
      await api.deleteMonitoring(query.id);
      setQueries((current) => current.filter((item) => item.id !== query.id));
      if (editingId === query.id) {
        setEditingId(null);
        setFormOpen(false);
      }
      showFlash('Monitoring question deleted.');
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Could not delete monitoring question.');
    } finally {
      setBusyId(null);
    }
  }

  if (loading && queries.length === 0) {
    return <div className="flex min-h-48 items-center justify-center" aria-busy="true"><Spinner size="lg" className="text-[#2783de] dark:text-[#63aaf0]" /></div>;
  }

  return (
    <section className="space-y-6" aria-labelledby="monitoring-admin-heading">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8]">Administration</p>
          <h1 id="monitoring-admin-heading" className="mt-1 text-2xl font-bold tracking-tight text-[#2c2c2b] dark:text-[#f4f3f1]">Monitoring</h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[#7d7a75] dark:text-[#b4b1ab]">Keep questions such as “What changed in Qwen releases?” on a separate cadence from the daily digest.</p>
        </div>
        <Button onClick={startCreate}>New question</Button>
      </header>

      {flash && <div className={`rounded-lg border px-4 py-3 text-sm ${flash.ok ? 'border-[#b9d8ee] bg-[#e5f2fc] text-[#1d5f9f] dark:border-[#36536d] dark:bg-[#1c3852] dark:text-[#a6d2f8]' : 'border-[#f4c6c1] bg-[#fff1ef] text-[#8f3f34] dark:border-[#7e3f37] dark:bg-[#4a2521] dark:text-[#ffb9b1]'}`} role="status">{flash.text}</div>}
      {error && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#f4c6c1] bg-[#fff1ef] px-4 py-3 text-sm text-[#8f3f34] dark:border-[#7e3f37] dark:bg-[#4a2521] dark:text-[#ffb9b1]" role="alert"><span>{error}</span><Button variant="secondary" size="sm" onClick={() => void loadQueries()}>Retry</Button></div>}

      {formOpen && (
        <form onSubmit={saveForm} className="space-y-5 rounded-lg border border-[#b9d8ee] bg-[#f7fbfe] p-5 dark:border-[#36536d] dark:bg-[#1c2730]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]">{editingId == null ? 'New monitoring question' : 'Edit monitoring question'}</h2>
              <p className="mt-1 text-sm text-[#7d7a75] dark:text-[#b4b1ab]">The exact question is retained; the search query is used for collection.</p>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={() => setFormOpen(false)}>Cancel</Button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1 md:col-span-2"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Question</span><input required value={form.question} onInput={(event) => setForm((current) => ({ ...current, question: (event.currentTarget as HTMLInputElement).value }))} placeholder="What changed in Qwen releases?" className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]" /></label>
            <label className="space-y-1 md:col-span-2"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Search query</span><input required value={form.search_query} onInput={(event) => setForm((current) => ({ ...current, search_query: (event.currentTarget as HTMLInputElement).value }))} placeholder="Qwen release OR Qwen model" className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]" /></label>
            <label className="space-y-1"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Scope</span><select value={form.scope} onChange={(event) => setForm((current) => ({ ...current, scope: (event.currentTarget as HTMLSelectElement).value as MonitorScope }))} className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]"><option value="both">Discovery + configured feeds</option><option value="general_discovery">General discovery</option><option value="configured_feeds">Configured feeds</option></select></label>
            <label className="space-y-1"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Cadence (minutes)</span><input type="number" min="5" step="5" value={form.cadence_minutes} onInput={(event) => setForm((current) => ({ ...current, cadence_minutes: Number((event.currentTarget as HTMLInputElement).value) }))} className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]" /></label>
            <label className="space-y-1"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Include keywords</span><input value={form.include_keywords.join(', ')} onInput={(event) => setForm((current) => ({ ...current, include_keywords: (event.currentTarget as HTMLInputElement).value.split(',').map((part) => part.trim()).filter(Boolean) }))} placeholder="release, model, benchmark" className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]" /></label>
            <label className="space-y-1"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Exclude keywords</span><input value={form.exclude_keywords.join(', ')} onInput={(event) => setForm((current) => ({ ...current, exclude_keywords: (event.currentTarget as HTMLInputElement).value.split(',').map((part) => part.trim()).filter(Boolean) }))} placeholder="job, sponsored" className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]" /></label>
            <label className="space-y-1"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Category</span><input value={form.category} onInput={(event) => setForm((current) => ({ ...current, category: (event.currentTarget as HTMLInputElement).value }))} placeholder="Technology" className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]" /></label>
            <label className="space-y-1"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Max results</span><input type="number" min="1" max="100" value={form.max_items} onInput={(event) => setForm((current) => ({ ...current, max_items: Number((event.currentTarget as HTMLInputElement).value) }))} className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]" /></label>
            <label className="space-y-1"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Language</span><input value={form.language} onInput={(event) => setForm((current) => ({ ...current, language: (event.currentTarget as HTMLInputElement).value }))} placeholder="en" className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]" /></label>
            <label className="space-y-1"><span className="text-sm font-semibold text-[#5e5b56] dark:text-[#cbc8c1]">Country</span><input value={form.country} onInput={(event) => setForm((current) => ({ ...current, country: (event.currentTarget as HTMLInputElement).value }))} placeholder="US" className="w-full rounded-md border border-[#d7d5d2] bg-white px-3 py-2 text-sm dark:border-[#4a4945] dark:bg-[#20201e] dark:text-[#f4f3f1]" /></label>
          </div>
          <label className="flex items-center gap-2 text-sm text-[#5e5b56] dark:text-[#cbc8c1]"><input type="checkbox" checked={form.enabled} onChange={(event) => setForm((current) => ({ ...current, enabled: (event.currentTarget as HTMLInputElement).checked }))} /> Run checks automatically</label>
          <div className="flex justify-end"><Button type="submit" loading={saving}>{editingId == null ? 'Create question' : 'Save changes'}</Button></div>
        </form>
      )}

      {queries.length === 0 ? <EmptyState title="No monitoring questions" description="Create a question to begin a separate watch history." action={<Button onClick={startCreate}>New question</Button>} /> : (
        <div className="space-y-3">
          {queries.map((query) => {
            const busy = busyId === query.id;
            return (
              <article key={query.id} className="rounded-lg border border-[#e6e5e3] bg-white p-5 dark:border-[#3b3a37] dark:bg-[#20201e]">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2"><h2 className="text-base font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]">{query.question}</h2><span className={`rounded-full px-2 py-1 text-xs font-semibold ${query.enabled ? 'bg-[#e5f2fc] text-[#1d5f9f] dark:bg-[#1c3852] dark:text-[#a6d2f8]' : 'bg-[#f0efed] text-[#7d7a75] dark:bg-[#2a2927] dark:text-[#b4b1ab]'}`}>{query.enabled ? 'Active' : 'Paused'}</span>{(query.new_count ?? 0) > 0 && <span className="rounded-full bg-[#2783de] px-2 py-1 text-xs font-semibold text-white">{query.new_count} new</span>}</div>
                    <p className="mt-1 break-words text-sm text-[#7d7a75] dark:text-[#b4b1ab]">{query.search_query}</p>
                    <p className="mt-2 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">{query.scope.replace('_', ' ')} · every {query.cadence_minutes} min · last checked {displayTime(query.last_checked_at)}{query.last_error ? ` · ${query.last_error}` : ''}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="secondary" disabled={busy} onClick={() => startEdit(query)}>Edit</Button>
                    <Button size="sm" variant="secondary" loading={busy} onClick={() => void toggleQuery(query)}>{query.enabled ? 'Pause' : 'Resume'}</Button>
                    <Button size="sm" loading={busy} onClick={() => void checkNow(query)}>Check now</Button>
                    <Button size="sm" variant="danger" disabled={busy} onClick={() => void deleteQuery(query)}>Delete</Button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
