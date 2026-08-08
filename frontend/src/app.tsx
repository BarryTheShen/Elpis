import { useEffect, useState } from 'preact/hooks';
import { Router, Route, Switch } from 'wouter';

import { AdminSurface } from './components/AdminSurface';
import { PublicationLayout } from './layouts/PublicationLayout';
import { ArchivePage } from './pages/Archive';
import { AuthRequiredPage } from './pages/AuthRequired';
import { CandidatesPage } from './pages/Candidates';
import { DiscoverPage } from './pages/Discover';
import { DigestPage } from './pages/Digest';
import { MonitoringPage } from './pages/Monitoring';
import { ReadLaterPage } from './pages/ReadLater';
import { StarredPage } from './pages/Starred';
import { checkAuth } from './lib/auth';
import { product } from './lib/product';

type PublicationAuthState = 'checking' | 'authenticated' | 'unauthenticated';

function usePublicationAuth(): PublicationAuthState {
  const [authState, setAuthState] =
    useState<PublicationAuthState>('checking');

  useEffect(() => {
    let active = true;
    checkAuth()
      .then((authenticated) => {
        if (active) {
          setAuthState(authenticated ? 'authenticated' : 'unauthenticated');
        }
      })
      .catch(() => {
        if (active) setAuthState('unauthenticated');
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const handleExpired = () => setAuthState('unauthenticated');
    window.addEventListener('auth:expired', handleExpired);
    return () => window.removeEventListener('auth:expired', handleExpired);
  }, []);

  return authState;
}

function PublicationSurface() {
  const authState = usePublicationAuth();
  const authenticated = authState === 'authenticated';

  return (
    <PublicationLayout authenticated={authenticated}>
      <Switch>
        <Route path="/archive">
          <ArchivePage />
        </Route>
        <Route path="/discover">
          <DiscoverPage />
        </Route>
        <Route path="/candidates">
          {authenticated ? (
            <CandidatesPage />
          ) : (
            <AuthRequiredPage
              title="Ranked candidates are private"
              description="Sign in to review every candidate that passed your relevance gate."
              returnTo="/candidates"
            />
          )}
        </Route>
        <Route path="/monitoring">
          {authenticated ? (
            <MonitoringPage />
          ) : (
            <AuthRequiredPage
              title="Monitoring is for signed-in readers"
              description="Sign in to read your saved monitoring questions and their result history."
              returnTo="/monitoring"
            />
          )}
        </Route>
        <Route path="/read-later">
          {authenticated ? (
            <ReadLaterPage />
          ) : (
            <AuthRequiredPage
              title="Read later is for signed-in readers"
              description="Sign in to keep a personal list of stories you want to return to."
              returnTo="/read-later"
            />
          )}
        </Route>
        <Route path="/starred">
          {authenticated ? (
            <StarredPage />
          ) : (
            <AuthRequiredPage
              title="Starred stories are private"
              description="Sign in to view and manage the stories you have kept."
              returnTo="/starred"
            />
          )}
        </Route>
        <Route path="/">
          <DigestPage readOnly={!authenticated} />
        </Route>
        <Route>
          <div className="py-20 text-center text-[#7d7a75] dark:text-[#b4b1ab]">
            Page not found.
          </div>
        </Route>
      </Switch>
    </PublicationLayout>
  );
}

export function App() {
  useEffect(() => {
    document.title = product.name;
  }, []);

  return (
    <Router>
      <Switch>
        <Route path="/login">
          <AdminSurface loginOnly />
        </Route>
        <Route path="/admin/*?">
          <AdminSurface />
        </Route>
        <Route>
          <PublicationSurface />
        </Route>
      </Switch>
    </Router>
  );
}
