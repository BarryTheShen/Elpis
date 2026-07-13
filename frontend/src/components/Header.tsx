import { Link, useLocation } from 'wouter';

import { JobBanner } from './JobBanner';
import { ThemeToggle } from './ThemeToggle';
import { product } from '../lib/product';

interface NavLink {
  href: string;
  label: string;
}

interface HeaderProps {
  onMobileMenuToggle?: () => void;
  mobileMenuOpen?: boolean;
}

const NAV_LINKS: NavLink[] = [
  { href: '/', label: 'Digest' },
  { href: '/admin', label: 'Admin' },
];

/** Sticky top header with brand, nav links, and digest job banner. */
export function Header({
  onMobileMenuToggle,
  mobileMenuOpen = false,
}: HeaderProps) {
  const [location] = useLocation();

  return (
    <div class="sticky top-0 z-40">
      <header class="h-16 flex items-center justify-between gap-3 px-4 sm:px-6 bg-white dark:bg-[#171716] border-b border-[#e6e5e3] dark:border-[#3b3a37]">
        {/* Left: hamburger (mobile) + brand */}
        <div class="flex items-center gap-3">
          <button
            type="button"
            class="lg:hidden p-1.5 rounded-md text-[#7d7a75] hover:bg-[#f0efed] dark:text-[#b4b1ab] dark:hover:bg-[#2a2927] transition-colors"
            onClick={onMobileMenuToggle}
            aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
          >
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              {mobileMenuOpen ? (
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>

          <Link
            href="/"
            class="flex items-center gap-2 font-semibold text-[#2c2c2b] dark:text-[#f4f3f1] hover:text-[#2783de] dark:hover:text-[#63aaf0] transition-colors no-underline"
          >
            <BrandMark />
            <span class="hidden sm:inline">{product.name}</span>
          </Link>
        </div>

        {/* Right: nav + job banner */}
        <div class="flex items-center gap-2">
          <nav class="hidden lg:flex items-center mr-2">
            {NAV_LINKS.map(({ href, label }) => {
              const active =
                href === '/'
                  ? location === '/'
                  : location.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  class={[
                    'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors no-underline',
                    active
                      ? 'text-[#1d5f9f] dark:text-[#a6d2f8] bg-[#e5f2fc] dark:bg-[#1c3852]'
                      : 'text-[#7d7a75] dark:text-[#b4b1ab] hover:text-[#2c2c2b] dark:hover:text-[#f4f3f1] hover:bg-[#f0efed] dark:hover:bg-[#2a2927]',
                  ].join(' ')}
                >
                  {label}
                </Link>
              );
            })}
          </nav>

          <JobBanner />
          <ThemeToggle />
          <RefreshButton />
        </div>
      </header>
    </div>
  );
}

/** Mobile refresh button for installed PWA/browser chrome-free use. */
function RefreshButton() {
  return (
    <button
      type="button"
      class="lg:hidden inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md border border-[#e6e5e3] bg-white text-[#2c2c2b] transition-colors hover:bg-[#f0efed] dark:border-[#3b3a37] dark:bg-[#20201e] dark:text-[#f4f3f1] dark:hover:bg-[#2a2927]"
      onClick={() => window.location.reload()}
      title="Refresh"
      aria-label="Refresh"
    >
      <svg
        class="w-4 h-4"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        stroke-width="2"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
    </button>
  );
}

function BrandMark() {
  return (
    <span
      class="w-7 h-7 rounded-md flex-shrink-0 flex items-center justify-center text-white font-black text-xs"
      style={{ background: '#2783de' }}
    >
      {product.mark}
    </span>
  );
}
