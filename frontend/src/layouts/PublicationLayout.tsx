import type { ComponentChildren } from 'preact';
import { Link } from 'wouter';

import { product } from '../lib/product';
import { ThemeToggle } from '../components/ThemeToggle';

interface PublicationLayoutProps {
  children: ComponentChildren;
}

/**
 * The read-only publication frame shared by desktop and mobile visitors.
 * Administrative tools intentionally live behind a separate route boundary.
 */
export function PublicationLayout({ children }: PublicationLayoutProps) {
  return (
    <div class="min-h-screen bg-white text-[#2c2c2b] dark:bg-slate-950 dark:text-slate-100">
      <header class="border-b border-[#e6e5e3] bg-white dark:border-slate-800 dark:bg-slate-950">
        <div class="mx-auto flex min-h-16 max-w-[1120px] items-center justify-between gap-4 px-4 sm:px-6">
          <Link
            href="/"
            class="min-w-0 text-sm font-semibold tracking-tight text-[#2c2c2b] dark:text-slate-100"
          >
            {product.name}
          </Link>

          <nav class="flex items-center gap-1" aria-label="Publication">
            <Link
              href="/"
              class="rounded-md px-3 py-2 text-sm font-medium text-[#2c2c2b] transition-colors hover:bg-[#f0efed] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2783de] dark:text-slate-100 dark:hover:bg-slate-800"
            >
              Today
            </Link>
            <Link
              href="/admin"
              class="hidden rounded-md px-3 py-2 text-sm font-medium text-[#2783de] transition-colors hover:bg-[#e5f2fc] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2783de] md:inline-flex dark:hover:bg-slate-800"
            >
              Admin
            </Link>
            <ThemeToggle />
          </nav>
        </div>
      </header>
      <main class="mx-auto w-full max-w-[1120px] px-4 py-8 sm:px-6 sm:py-10">
        {children}
      </main>

      <footer class="border-t border-[#e6e5e3] dark:border-slate-800">
        <div class="mx-auto max-w-[1120px] px-4 py-6 text-sm text-[#7d7a75] sm:px-6 dark:text-slate-400">
          {product.tagline}
        </div>
      </footer>
    </div>
  );
}
