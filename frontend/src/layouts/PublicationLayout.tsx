import type { ComponentChildren } from 'preact';
import { Link } from 'wouter';

import { product } from '../lib/product';
import { ThemeToggle } from '../components/ThemeToggle';

interface PublicationLayoutProps {
  children: ComponentChildren;
  authenticated?: boolean;
}

/**
 * Publication frame shared by desktop and mobile readers.
 * Administrative tools intentionally live behind a separate route boundary.
 */
export function PublicationLayout({
  children,
  authenticated = false,
}: PublicationLayoutProps) {
  const linkClass =
    'shrink-0 whitespace-nowrap rounded-md px-2 py-2 text-xs font-medium leading-tight text-[#2c2c2b] transition-colors hover:bg-[#f0efed] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de] sm:px-3 sm:text-sm dark:text-[#f4f3f1] dark:hover:bg-[#2a2927]';

  return (
    <div className="min-h-screen bg-white text-[#2c2c2b] dark:bg-[#171716] dark:text-[#f4f3f1]">
      <header className="sticky top-0 z-20 border-b border-[#e6e5e3]/90 bg-white/95 backdrop-blur-sm dark:border-[#3b3a37]/90 dark:bg-[#171716]/95">
        <div className="mx-auto flex min-h-16 max-w-[1120px] items-center gap-2 px-4 py-2 sm:gap-4 sm:px-6">
          <Link
            href="/"
            className="flex min-w-0 shrink-0 items-center gap-2.5 text-sm font-semibold tracking-tight text-[#2c2c2b] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de] dark:text-[#f4f3f1]"
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#2783de] text-xs font-black text-white">
              {product.mark}
            </span>
            <span className="truncate">{product.name}</span>
          </Link>

          <nav
            className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-0.5 sm:gap-1"
            aria-label="Publication"
          >
            <Link href="/" className={linkClass}>
              Today
            </Link>
            <Link href="/discover" className={linkClass}>
              Discover
            </Link>
            <Link href="/archive" className={linkClass}>
              Archive
            </Link>
            {authenticated && (
              <>
                <Link href="/read-later" className={linkClass}>
                  Read later
                </Link>
                <Link href="/starred" className={linkClass}>
                  Starred
                </Link>
                <Link href="/candidates" className={linkClass}>
                  Candidates
                </Link>
                <Link href="/monitoring" className={linkClass}>
                  Monitoring
                </Link>
                <Link href="/admin/overview" className={linkClass}>
                  Admin
                </Link>
              </>
            )}
            {!authenticated && (
              <Link href="/login" className={linkClass}>
                Sign in
              </Link>
            )}
          </nav>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1120px] px-4 py-8 sm:px-6 sm:py-12">
        {children}
      </main>

      <footer className="border-t border-[#e6e5e3] dark:border-[#3b3a37]">
        <div className="mx-auto max-w-[1120px] px-4 py-6 text-sm text-[#7d7a75] sm:px-6 dark:text-[#b4b1ab]">
          {product.tagline}
        </div>
      </footer>
    </div>
  );
}
