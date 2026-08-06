import { useState, useEffect, useRef } from 'preact/hooks';
import { localDateKey } from '../lib/dates';
import type { DigestItem } from '../lib/types';

interface Filters {
  search: string;
  category: string;
  source: string;
  kind: string;
  dateFrom: string;
  dateTo: string;
}

interface FilterPanelProps {
  items: DigestItem[];
  onFiltered: (filtered: DigestItem[]) => void;
  readCount?: number;
  hideRead?: boolean;
  onToggleHideRead?: () => void;
}

const EMPTY_FILTERS: Filters = {
  search: '',
  category: '',
  source: '',
  kind: '',
  dateFrom: '',
  dateTo: '',
};

function unique(items: DigestItem[], key: keyof DigestItem): string[] {
  const set = new Set<string>();
  items.forEach((it) => {
    const v = String(it[key] ?? '');
    if (v) set.add(v);
  });
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

function passes(it: DigestItem, f: Filters): boolean {
  if (f.search) {
    const q = f.search.toLowerCase();
    const hay = [it.title, it.summary, it.source, it.category, it.url]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    if (!hay.includes(q)) return false;
  }
  if (f.category && it.category !== f.category) return false;
  if (f.source && it.source !== f.source) return false;
  if (f.kind && it.kind !== f.kind) return false;
  if (f.dateFrom || f.dateTo) {
    const d = localDateKey(it.published_at);
    if (!d) return false;
    if (f.dateFrom && d < f.dateFrom) return false;
    if (f.dateTo && d > f.dateTo) return false;
  }
  return true;
}

export function FilterPanel({
  items,
  onFiltered,
  readCount = 0,
  hideRead = true,
  onToggleHideRead,
}: FilterPanelProps) {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [open, setOpen] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const categories = unique(items, 'category');
  const sources = unique(items, 'source');

  useEffect(() => {
    const filtered = items.filter((it) => passes(it, filters));
    onFiltered(filtered);
  }, [filters, items, onFiltered]);

  function set<K extends keyof Filters>(key: K, val: Filters[K]) {
    setFilters((prev) => ({ ...prev, [key]: val }));
  }

  function handleSearch(val: string) {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => set('search', val), 160);
  }

  function reset() {
    setFilters(EMPTY_FILTERS);
  }

  const activeCount = Object.values(filters).filter(Boolean).length;

  return (
    <div className="border-y border-[#e6e5e3] dark:border-[#3b3a37] bg-[#f9f8f7] dark:bg-[#20201e]">
      <div className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z"
            />
          </svg>
          <input
            type="search"
            aria-label="Search digest"
            placeholder="Search title, summary, source..."
            className="w-full rounded-md border border-[#e6e5e3] bg-white py-2.5 pl-9 pr-3 text-sm text-[#2c2c2b] placeholder-[#7d7a75] outline-none transition-colors focus:border-[#2783de] focus:ring-2 focus:ring-[#2783de]/20 dark:border-[#3b3a37] dark:bg-[#171716] dark:text-[#f4f3f1] dark:placeholder-[#b4b1ab]"
            onInput={(e) => handleSearch((e.target as HTMLInputElement).value)}
          />
        </div>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className={[
            'flex items-center gap-1.5 px-3 py-2 text-sm rounded-md border transition-colors active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
            open
              ? 'bg-[#e5f2fc] dark:bg-[#1c3852] border-[#9bcaf2] dark:border-[#4f8fc8] text-[#1d5f9f] dark:text-[#a6d2f8]'
              : 'bg-white dark:bg-[#171716] border-[#e6e5e3] dark:border-[#3b3a37] text-[#7d7a75] dark:text-[#b4b1ab] hover:bg-[#f0efed] dark:hover:bg-[#2a2927]',
          ].join(' ')}
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"
            />
          </svg>
          Filters
          {activeCount > 0 && (
            <span className="ml-0.5 bg-[#2783de] text-white text-xs font-bold rounded-md min-w-4 h-4 px-1 flex items-center justify-center">
              {activeCount}
            </span>
          )}
        </button>
        {activeCount > 0 && (
          <button
            type="button"
            onClick={reset}
            className="px-3 py-2 text-sm text-[#7d7a75] dark:text-[#b4b1ab] hover:text-[#2c2c2b] dark:hover:text-[#f4f3f1] transition-colors"
          >
            Clear
          </button>
        )}

        {readCount > 0 && onToggleHideRead && (
          <button
            type="button"
            onClick={onToggleHideRead}
            className={[
            'flex items-center gap-1.5 px-3 py-2 text-sm rounded-md border transition-colors active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
            hideRead
              ? 'bg-[#e5f2fc] dark:bg-[#1c3852] border-[#9bcaf2] dark:border-[#4f8fc8] text-[#1d5f9f] dark:text-[#a6d2f8] hover:bg-[#d8ecfa] dark:hover:bg-[#244867]'
              : 'bg-white dark:bg-[#171716] border-[#e6e5e3] dark:border-[#3b3a37] text-[#7d7a75] dark:text-[#b4b1ab] hover:bg-[#f0efed] dark:hover:bg-[#2a2927]',
            ].join(' ')}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2"
            >
              {hideRead ? (
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
                />
              ) : (
                <>
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                  />
                </>
              )}
            </svg>
            {hideRead
              ? `Show ${readCount} hidden`
              : `Hide ${readCount} hidden`}
          </button>
        )}
      </div>

      {open && (
        <div className="px-3 pb-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
              Category
            </span>
            <select
              className="rounded-md border border-[#e6e5e3] bg-white px-2.5 py-2 text-sm text-[#2c2c2b] outline-none transition-colors focus:border-[#2783de] focus:ring-2 focus:ring-[#2783de]/20 dark:border-[#3b3a37] dark:bg-[#171716] dark:text-[#f4f3f1]"
              value={filters.category}
              onChange={(e) =>
                set('category', (e.target as HTMLSelectElement).value)
              }
            >
              <option value="">All</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
              Source
            </span>
            <select
              className="rounded-md border border-[#e6e5e3] bg-white px-2.5 py-2 text-sm text-[#2c2c2b] outline-none transition-colors focus:border-[#2783de] focus:ring-2 focus:ring-[#2783de]/20 dark:border-[#3b3a37] dark:bg-[#171716] dark:text-[#f4f3f1]"
              value={filters.source}
              onChange={(e) =>
                set('source', (e.target as HTMLSelectElement).value)
              }
            >
              <option value="">All</option>
              {sources.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
              Type
            </span>
            <select
              className="rounded-md border border-[#e6e5e3] bg-white px-2.5 py-2 text-sm text-[#2c2c2b] outline-none transition-colors focus:border-[#2783de] focus:ring-2 focus:ring-[#2783de]/20 dark:border-[#3b3a37] dark:bg-[#171716] dark:text-[#f4f3f1]"
              value={filters.kind}
              onChange={(e) =>
                set('kind', (e.target as HTMLSelectElement).value)
              }
            >
              <option value="">All types</option>
              <option value="article">Article</option>
              <option value="video">Video</option>
              <option value="watch">Website watch</option>
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
              From
            </span>
            <input
              type="date"
              className="rounded-md border border-[#e6e5e3] bg-white px-2.5 py-2 text-sm text-[#2c2c2b] outline-none transition-colors focus:border-[#2783de] focus:ring-2 focus:ring-[#2783de]/20 dark:border-[#3b3a37] dark:bg-[#171716] dark:text-[#f4f3f1]"
              value={filters.dateFrom}
              onChange={(e) =>
                set('dateFrom', (e.target as HTMLInputElement).value)
              }
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
              To
            </span>
            <input
              type="date"
              className="rounded-md border border-[#e6e5e3] bg-white px-2.5 py-2 text-sm text-[#2c2c2b] outline-none transition-colors focus:border-[#2783de] focus:ring-2 focus:ring-[#2783de]/20 dark:border-[#3b3a37] dark:bg-[#171716] dark:text-[#f4f3f1]"
              value={filters.dateTo}
              onChange={(e) =>
                set('dateTo', (e.target as HTMLInputElement).value)
              }
            />
          </label>
        </div>
      )}
    </div>
  );
}
