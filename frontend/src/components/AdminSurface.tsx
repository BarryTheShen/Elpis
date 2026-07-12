import { useEffect, useState } from 'preact/hooks';
import { Link, Redirect, Route, Switch } from 'wouter';

import { AppLayout } from '../layouts/AppLayout';
import { LoginPage } from '../pages/Login';
import { ApiKeysPage } from '../pages/admin/ApiKeys';
import { BudgetPage } from '../pages/admin/Budget';
import { LlmConfigPage } from '../pages/admin/LlmConfig';
import { LogsPage } from '../pages/admin/Logs';
import { PreferencesPage } from '../pages/admin/Preferences';
import { SchedulePage } from '../pages/admin/Schedule';
import { SecurityPage } from '../pages/admin/Security';
import { SettingsPage } from '../pages/admin/Settings';
import { SourcesPage } from '../pages/admin/Sources';
import { api } from '../lib/api';
import { checkAuth } from '../lib/auth';
import type { DigestEntry } from '../lib/types';

type AuthState = 'checking' | 'authenticated' | 'unauthenticated';

function useDesktopViewport(): boolean {
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches,
  );

  useEffect(() => {
    const query = window.matchMedia('(min-width: 768px)');
    const update = () => setIsDesktop(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  return isDesktop;
}

function AdminRoutes() {
  return (
    <Switch>
      <Route path="/admin">
        <Redirect to="/admin/sources" />
      </Route>
      <Route path="/admin/sources"><SourcesPage /></Route>
      <Route path="/admin/llm"><LlmConfigPage /></Route>
      <Route path="/admin/keys"><ApiKeysPage /></Route>
      <Route path="/admin/budget"><BudgetPage /></Route>
      <Route path="/admin/schedule"><SchedulePage /></Route>
      <Route path="/admin/logs"><LogsPage /></Route>
      <Route path="/admin/digest-settings"><SettingsPage /></Route>
      <Route path="/admin/profile"><PreferencesPage /></Route>
      <Route path="/admin/security"><SecurityPage /></Route>
      <Route>
        <div class="py-20 text-center text-slate-500 dark:text-slate-400">
          Admin page not found.
        </div>
      </Route>
    </Switch>
  );
}

function MobileAdminNotice() {
  return (
    <main class="flex min-h-screen items-center justify-center bg-[#f9f8f7] px-6 text-[#2c2c2b] dark:bg-slate-950 dark:text-slate-100">
      <section class="max-w-sm text-center">
        <p class="text-sm font-semibold uppercase tracking-[0.16em] text-[#7d7a75] dark:text-slate-400">
          Desktop only
        </p>
        <h1 class="mt-3 text-2xl font-semibold tracking-tight">
          Administration is available on a larger screen.
        </h1>
        <p class="mt-3 text-base leading-6 text-[#7d7a75] dark:text-slate-400">
          This mobile edition stays focused on reading today&apos;s publication.
        </p>
        <Link
          href="/"
          class="mt-6 inline-flex rounded-md bg-[#2783de] px-4 py-2.5 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2783de]"
        >
          Return to today
        </Link>
      </section>
    </main>
  );
}

/** Server-protected operational tools, omitted entirely on narrow screens. */
export function AdminSurface() {
  const isDesktop = useDesktopViewport();
  const [authState, setAuthState] = useState<AuthState>('checking');
  const [digests, setDigests] = useState<DigestEntry[]>([]);

  useEffect(() => {
    if (!isDesktop) return;

    let active = true;
    checkAuth()
      .then((ok) => active && setAuthState(ok ? 'authenticated' : 'unauthenticated'))
      .catch(() => active && setAuthState('unauthenticated'));

    return () => {
      active = false;
    };
  }, [isDesktop]);

  useEffect(() => {
    const handleExpired = () => setAuthState('unauthenticated');
    window.addEventListener('auth:expired', handleExpired);
    return () => window.removeEventListener('auth:expired', handleExpired);
  }, []);

  useEffect(() => {
    if (authState !== 'authenticated') return;
    api.listDigests().then(setDigests).catch(() => setDigests([]));
  }, [authState]);

  if (!isDesktop) return <MobileAdminNotice />;

  if (authState === 'checking') {
    return (
      <div class="flex min-h-screen items-center justify-center bg-[#f9f8f7] dark:bg-slate-950">
        <span class="h-8 w-8 animate-spin rounded-full border-4 border-[#2783de] border-t-transparent" />
      </div>
    );
  }

  if (authState === 'unauthenticated') {
    return <LoginPage onLogin={() => setAuthState('authenticated')} />;
  }

  return (
    <AppLayout digests={digests} currentDigestId={null}>
      <AdminRoutes />
    </AppLayout>
  );
}
