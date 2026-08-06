import { useEffect, useState } from 'preact/hooks';
import { Link, Redirect, Route, Switch } from 'wouter';

import { AppLayout } from '../layouts/AppLayout';
import { LoginPage } from '../pages/Login';
import { ProvidersPage } from '../pages/admin/Providers';
import { OverviewPage } from '../pages/admin/Overview';
import { BudgetPage } from '../pages/admin/Budget';
import { AdvancedPage } from '../pages/admin/Advanced';
import { LlmConfigPage } from '../pages/admin/LlmConfig';
import { LogsPage } from '../pages/admin/Logs';
import { PreferencesPage } from '../pages/admin/Preferences';
import { SchedulePage } from '../pages/admin/Schedule';
import { SecurityPage } from '../pages/admin/Security';
import { SettingsPage } from '../pages/admin/Settings';
import { SourcesPage } from '../pages/admin/Sources';
import { checkAuth } from '../lib/auth';

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

const ADMIN_HOME = '/admin/overview';

function AdminRoutes() {
  return (
    <Switch>
      <Route path="/admin">
        <Redirect to="/admin/overview" />
      </Route>
      <Route path="/admin/overview"><OverviewPage /></Route>
      <Route path="/admin/digest"><Redirect to="/" /></Route>
      <Route path="/admin/sources"><SourcesPage /></Route>
      <Route path="/admin/llm"><LlmConfigPage /></Route>
      <Route path="/admin/providers"><ProvidersPage /></Route>
      <Route path="/admin/keys"><Redirect to="/admin/providers" /></Route>
      <Route path="/admin/budget"><BudgetPage /></Route>
      <Route path="/admin/read-later"><Redirect to="/read-later" /></Route>
      <Route path="/admin/starred"><Redirect to="/starred" /></Route>
      <Route path="/admin/schedule"><SchedulePage /></Route>
      <Route path="/admin/advanced"><AdvancedPage /></Route>
      <Route path="/admin/logs"><LogsPage /></Route>
      <Route path="/admin/digest-settings"><SettingsPage /></Route>
      <Route path="/admin/profile"><PreferencesPage /></Route>
      <Route path="/admin/security"><SecurityPage /></Route>
      <Route>
        <div className="py-20 text-center text-[#7d7a75] dark:text-[#b4b1ab]">
          Admin page not found.
        </div>
      </Route>
    </Switch>
  );
}

function MobileAdminNotice() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f9f8f7] px-6 text-[#2c2c2b] dark:bg-[#171716] dark:text-[#f4f3f1]">
      <section className="max-w-sm text-center">
        <p className="text-sm font-semibold tracking-[0.12em] text-[#7d7a75] dark:text-[#b4b1ab]">
          Desktop only
        </p>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight">
          Administration is available on a larger screen.
        </h1>
        <p className="mt-3 text-base leading-7 text-[#7d7a75] dark:text-[#b4b1ab]">
          This mobile edition stays focused on reading today&apos;s publication.
        </p>
        <Link
          href="/"
          className="mt-6 inline-flex rounded-md bg-[#2783de] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#1f6fbe] active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de] dark:bg-[#63aaf0] dark:text-[#171716] dark:hover:bg-[#83bdf5]"
        >
          Return to today
        </Link>
      </section>
    </main>
  );
}

interface AdminSurfaceProps {
  /** `/login` is public; `/admin/*` is already authorized by the server. */
  loginOnly?: boolean;
}

/** Server-protected operational tools, omitted entirely on narrow screens. */
export function AdminSurface({ loginOnly = false }: AdminSurfaceProps) {
  const isDesktop = useDesktopViewport();
  const [authState, setAuthState] = useState<AuthState>('checking');

  useEffect(() => {
    if (!isDesktop && !loginOnly) return;

    let active = true;
    checkAuth()
      .then((ok) => active && setAuthState(ok ? 'authenticated' : 'unauthenticated'))
      .catch(() => active && setAuthState('unauthenticated'));

    return () => {
      active = false;
    };
  }, [isDesktop, loginOnly]);

  useEffect(() => {
    const handleExpired = () => setAuthState('unauthenticated');
    window.addEventListener('auth:expired', handleExpired);
    return () => window.removeEventListener('auth:expired', handleExpired);
  }, []);

  useEffect(() => {
    if (loginOnly && authState === 'authenticated') {
      window.location.replace(ADMIN_HOME);
    }
  }, [authState, loginOnly]);


  if (!isDesktop && !loginOnly) return <MobileAdminNotice />;

  if (authState === 'checking') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f9f8f7] dark:bg-[#171716]">
        <span className="h-8 w-8 animate-spin rounded-full border-4 border-[#2783de] border-t-transparent" />
      </div>
    );
  }

  if (authState === 'unauthenticated') {
    return (
      <LoginPage
        onLogin={() => {
          if (loginOnly) {
            window.location.assign(ADMIN_HOME);
          } else {
            setAuthState('authenticated');
          }
        }}
      />
    );
  }

  if (loginOnly) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f9f8f7] dark:bg-[#171716]">
        <span className="h-8 w-8 animate-spin rounded-full border-4 border-[#2783de] border-t-transparent" />
      </div>
    );
  }
  return (
    <AppLayout>
      <AdminRoutes />
    </AppLayout>
  );
}
