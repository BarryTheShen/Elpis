import { useEffect } from 'preact/hooks';
import { Router, Route, Switch } from 'wouter';

import { AdminSurface } from './components/AdminSurface';
import { PublicationLayout } from './layouts/PublicationLayout';
import { DigestPage } from './pages/Digest';
import { product } from './lib/product';

export function App() {
  useEffect(() => {
    document.title = product.name;
  }, []);

  return (
    <Router>
      <Switch>
        <Route path="/admin/*?">
          <AdminSurface />
        </Route>
        <Route path="/">
          <PublicationLayout>
            <DigestPage readOnly />
          </PublicationLayout>
        </Route>
        <Route>
          <PublicationLayout>
            <div class="py-20 text-center text-[#7d7a75] dark:text-slate-400">
              Page not found.
            </div>
          </PublicationLayout>
        </Route>
      </Switch>
    </Router>
  );
}
