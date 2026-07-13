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
    <div class="min-h-screen bg-white text-[#2c2c2b] dark:bg-[#171716] dark:text-[#f4f3f1]">
      <header class="sticky top-0 z-20 border-b border-[#e6e5e3]/90 bg-white/95 backdrop-blur-sm dark:border-[#3b3a37]/90 dark:bg-[#171716]/95">
        <div class="mx-auto flex min-h-16 max-w-[1120px] items-center justify-between gap-4 px-4 sm:px-6">
          <Link
            href="/"
            class="flex min-w-0 items-center gap-2.5 text-sm font-semibold tracking-tight text-[#2c2c2b] dark:text-[#f4f3f1]"
          >
            <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#2783de] text-xs font-black text-white">
              {product.mark}
            </span>
            <span>{product.name}</span>
          </Link>

          <nav class="flex items-center gap-1" aria-label="Publication">
            <Link
              href="/"
              class="rounded-md px-3 py-2 text-sm font-medium text-[#2c2c2b] transition-colors hover:bg-[#f0efed] focus-visible:outline-none dark:text-[#f4f3f1] dark:hover:bg-[#2a2927]"
            >
              Today
            </Link>
            <Link
              href="/login"
              class="hidden rounded-md px-3 py-2 text-sm font-medium text-[#1d5f9f] transition-colors hover:bg-[#e5f2fc] focus-visible:outline-none md:inline-flex dark:text-[#a6d2f8] dark:hover:bg-[#1c3852]"
            >
              Admin
            </Link>
            <ThemeToggle />
          </nav>
        </div>
      </header>

      <main class="mx-auto w-full max-w-[1120px] px-4 py-8 sm:px-6 sm:py-12">
        {children}
      </main>

      <footer class="border-t border-[#e6e5e3] dark:border-[#3b3a37]">
        <div class="mx-auto max-w-[1120px] px-4 py-6 text-sm text-[#7d7a75] sm:px-6 dark:text-[#b4b1ab]">
          {product.tagline}
        </div>
      </footer>
    </div>
  );
}
