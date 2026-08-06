import { useState, useEffect } from 'preact/hooks';
import { Link } from 'wouter';
import type { ComponentChildren } from 'preact';
import { Header } from '../components/Header';
import { Sidebar } from '../components/Sidebar';
import { api } from '../lib/api';

interface AppLayoutProps {
  children: ComponentChildren;
}

/**
 * Full administrative layout: sticky header, collapsible sidebar, and
 * configuration/operations content area.
 * On desktop (lg+) the sidebar is always visible.
 * On mobile it slides in from the left as an overlay.
 */
export function AppLayout({ children }: AppLayoutProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [usingDefaultPassword, setUsingDefaultPassword] = useState(false);

  useEffect(() => {
    api
      .getPasswordInfo()
      .then((info) => setUsingDefaultPassword(info.using_default))
      .catch(() => {});
  }, []);

  return (
    <div className="min-h-screen flex flex-col bg-[#f9f8f7] text-[#2c2c2b] dark:bg-[#171716] dark:text-[#f4f3f1]">
      <Header
        onMobileMenuToggle={() => setMenuOpen((o) => !o)}
        mobileMenuOpen={menuOpen}
      />

      {usingDefaultPassword && (
        <div className="flex items-center justify-between gap-3 px-4 py-2 bg-[#8f3f34] dark:bg-[#6e3029] text-white text-xs font-medium">
          <span>
            You are using the default password. Change it in{' '}
            <Link href="/admin/security" className="underline underline-offset-2 hover:no-underline">
              Security
            </Link>{' '}
            before exposing this to the internet.
          </span>
          <button
            type="button"
            onClick={() => setUsingDefaultPassword(false)}
            className="flex-shrink-0 opacity-80 hover:opacity-100 text-white"
            aria-label="Dismiss"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {menuOpen && (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-[#2c2c2b]/35 lg:hidden"
          onClick={() => setMenuOpen(false)}
          aria-label="Close navigation menu"
        />
      )}

      <div className="flex flex-1 min-h-0">
        <div
          className={[
            'fixed lg:static inset-y-0 left-0 z-30 w-60 transition-transform duration-200',
            'lg:translate-x-0 lg:top-0',
            menuOpen ? 'translate-x-0' : '-translate-x-full',
            'top-14',
          ].join(' ')}
        >
          <Sidebar onClose={() => setMenuOpen(false)} />
        </div>

        <main className="flex-1 min-w-0 p-5 lg:p-8 overflow-auto">
          <div className="max-w-5xl mx-auto">{children}</div>
        </main>
      </div>
    </div>
  );
}
