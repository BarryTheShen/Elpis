import { useEffect, useState } from 'preact/hooks';
import { Badge, kindVariant } from './Badge';
import { RatingStars } from './RatingStars';
import { cleanSummary, tryParseStructuredSummary } from '../lib/clean-summary';
import type { DigestItem } from '../lib/types';
import { api } from '../lib/api';
import { formatDateOnly } from '../lib/dates';

interface ItemDetailPanelProps {
  item: DigestItem;
  isRead: boolean;
  rating?: number | null;
  onClose: () => void;
  onRate?: (url: string, rating: number) => void;
  onMarkRead?: (url: string) => void;
  /** Called when the user toggles the read-later bookmark. */
  onReadLater?: (item: DigestItem) => void;
  /** Whether this item is currently saved to read later. */
  isReadLater?: boolean;
  /**
   * Called when the user dismisses the item from the panel. Marks as read
   * and closes the panel so the card disappears from the grid.
   */
  onDismiss?: (url: string) => void;
  /** Called when the user toggles the starred state. */
  onToggleStar?: (item: DigestItem) => void;
  /** Whether this item is currently starred. */
  isStarred?: boolean;
}

/** A single segment of parsed summary content. */
type SummarySegment =
  | { type: 'paragraph'; text: string }
  | { type: 'list'; items: string[] };

/**
 * Parse the LLM-generated summary into renderable segments.
 *
 * Paragraph detection strategy:
 *   - Double-newline (blank line) always starts a new paragraph.
 *   - A single-newline line that ends with sentence-terminal punctuation
 *     (. ! ?) is treated as its own paragraph, since the LLM often emits
 *     3-paragraph summaries separated by only a single newline.
 *   - Lines beginning with "- " or "* " become bullet list items.
 */
function parseSummary(raw: string): SummarySegment[] {
  const cleaned = cleanSummary(raw);
  if (!cleaned) return [];

  const lines = cleaned.split('\n');
  const segments: SummarySegment[] = [];
  let proseBuf: string[] = [];
  let listBuf: string[] = [];

  const flushProse = () => {
    const text = proseBuf.join(' ').trim();
    if (text) segments.push({ type: 'paragraph', text });
    proseBuf = [];
  };

  const flushList = () => {
    if (listBuf.length > 0) {
      segments.push({ type: 'list', items: [...listBuf] });
      listBuf = [];
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();

    if (!trimmed) {
      flushProse();
      flushList();
      continue;
    }

    const isBullet = /^[-*]\s+/.test(trimmed);

    if (isBullet) {
      flushProse();
      listBuf.push(trimmed.replace(/^[-*]\s+/, ''));
      continue;
    }

    flushList();

    /*
     * Treat a non-bullet line that ends with sentence-terminal punctuation
     * as a self-contained paragraph.  This handles LLM output where the three
     * summary paragraphs are separated by single newlines rather than blank
     * lines.
     */
    const endsWithSentence = /[.!?]['"]?$/.test(trimmed);
    if (endsWithSentence && proseBuf.length === 0) {
      segments.push({ type: 'paragraph', text: trimmed });
    } else if (endsWithSentence && proseBuf.length > 0) {
      proseBuf.push(trimmed);
      flushProse();
    } else {
      proseBuf.push(trimmed);
    }
  }

  flushProse();
  flushList();

  return segments;
}

/**
 * Full-screen slide-over panel showing all detail for a single DigestItem.
 * Rendered as a portal-like fixed overlay; Escape key or backdrop click closes it.
 */
export function ItemDetailPanel({
  item,
  isRead,
  rating,
  onClose,
  onRate,
  onMarkRead,
  onReadLater,
  isReadLater = false,
  onDismiss,
  onToggleStar,
  isStarred = false,
}: ItemDetailPanelProps) {
  /*
   * Some older items have the LLM's structured output stored as a raw JSON
   * blob in `summary` rather than being split into the dedicated fields.
   * Fall back to the parsed JSON values when the dedicated fields are absent.
   */
  const jsonFallback = item.summary
    ? tryParseStructuredSummary(item.summary)
    : null;
  const tldr = item.tldr ?? jsonFallback?.tldr;
  const keyTakeaways =
    item.key_takeaways?.length
      ? item.key_takeaways
      : jsonFallback?.key_takeaways;

  const segments = parseSummary(item.summary);
  const date = formatDateOnly(item.published_at, { year: true });
  const metaParts: string[] = [];
  if (item.source) metaParts.push(item.source);
  if (date) metaParts.push(date);

  const [localRating, setLocalRating] = useState<number | null>(
    rating ?? null,
  );
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);

  /** Keep local star state in sync when the parent's ratings map updates. */
  useEffect(() => {
    setLocalRating(rating ?? null);
  }, [rating]);

  /** Lock body scroll and listen for Escape while panel is open. */
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);

    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  async function handleRate(r: number) {
    if (saving) return;
    setLocalRating(r);
    setSaving(true);
    try {
      await api.submitRating(item.url, r);
      onRate?.(item.url, r);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
    } catch {
      /* best-effort */
    } finally {
      setSaving(false);
    }
  }

  return (
    /* Backdrop */
    <div
      class="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-labelledby="detail-title"
    >
      {/* Semi-transparent backdrop - click closes */}
      <div
        class="absolute inset-0 bg-[#2c2c2b]/45"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div class="relative z-10 flex h-full w-full max-w-2xl flex-col overflow-y-auto border-l border-[#e6e5e3] bg-white dark:border-[#3b3a37] dark:bg-[#20201e]">

        {/* Top bar */}
        <div class="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-[#e6e5e3] bg-white/95 px-5 py-3 backdrop-blur-sm dark:border-[#3b3a37] dark:bg-[#20201e]/95">
          <button
            type="button"
            onClick={onClose}
            class="flex items-center gap-1.5 text-sm text-[#7d7a75] dark:text-[#b4b1ab] hover:text-[#2c2c2b] dark:hover:text-[#f4f3f1] transition-colors"
            aria-label="Close detail panel"
          >
            <svg
              class="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18"
              />
            </svg>
            Back
          </button>

          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            class="flex items-center gap-1.5 text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8] hover:text-[#2783de] dark:hover:text-[#63aaf0] transition-colors"
          >
            Open original
            <svg
              class="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
              />
            </svg>
          </a>
        </div>

        {/* Hero image (if available) */}
        {item.image_url && (
          <img
            src={item.image_url}
            alt=""
            loading="lazy"
            class="w-full max-h-64 object-cover bg-[#f0efed] dark:bg-[#2a2927]"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = 'none';
            }}
          />
        )}

        {/* Content */}
        <div class="flex-1 px-6 py-6 space-y-5">

          {/* Badges */}
          <div class="flex items-center gap-2 flex-wrap">
            <Badge variant={kindVariant(item.kind)}>{item.kind}</Badge>
            {item.category && (
              <span class="text-xs font-medium text-[#7d7a75] dark:text-[#b4b1ab]">
                {item.category}
              </span>
            )}
          </div>

          {/* Title */}
          <h1 id="detail-title" class="text-3xl font-semibold tracking-tight text-[#2c2c2b] dark:text-[#f4f3f1] leading-tight">
            {item.title || 'Untitled'}
          </h1>

          {/* Meta */}
          {metaParts.length > 0 && (
            <p class="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
              {metaParts.join(' · ')}
            </p>
          )}

          {/* Divider */}
          <hr class="border-[#e6e5e3] dark:border-[#3b3a37]" />

          {/* TL;DR */}
          {tldr && (
            <div class="space-y-2">
              <h2 class="text-sm font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
                TL;DR
              </h2>
              <p class="text-base font-medium text-[#2c2c2b] dark:text-[#f4f3f1] leading-relaxed">
                {tldr}
              </p>
            </div>
          )}

          {/* Key Takeaways */}
          {keyTakeaways && keyTakeaways.length > 0 && (
            <div class="space-y-2">
              <h2 class="text-sm font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
                Key Takeaways
              </h2>
              <ul class="space-y-2 pl-0 list-none">
                {keyTakeaways.map((point, i) => (
                  <li key={i} class="flex gap-2.5 text-base text-[#5f5c57] dark:text-[#d0cdc6] leading-relaxed">
                    <span
                      class="mt-[0.45em] flex-shrink-0 w-1.5 h-1.5 rounded-full bg-[#2783de] dark:bg-[#63aaf0]"
                      aria-hidden="true"
                    />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Divider before summary, shown only when structured fields are present */}
          {(tldr || (keyTakeaways && keyTakeaways.length > 0)) && (
            <hr class="border-[#e6e5e3] dark:border-[#3b3a37]" />
          )}

          {/* Summary */}
          {segments.length > 0 ? (
            <div class="space-y-3">
              <h2 class="text-sm font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
                Summary
              </h2>
              <div class="space-y-3 text-base text-[#5f5c57] dark:text-[#d0cdc6] leading-relaxed">
                {segments.map((seg, i) => {
                  if (seg.type === 'paragraph') {
                    return <p key={i}>{seg.text}</p>;
                  }
                  return (
                    <ul key={i} class="space-y-1.5 pl-0 list-none">
                      {seg.items.map((bullet, j) => (
                        <li key={j} class="flex gap-2.5">
                          <span
                            class="mt-[0.4em] flex-shrink-0 w-1.5 h-1.5 rounded-full bg-[#2783de] dark:bg-[#63aaf0]"
                            aria-hidden="true"
                          />
                          <span>{bullet}</span>
                        </li>
                      ))}
                    </ul>
                  );
                })}
              </div>
            </div>
          ) : (
            !tldr && !keyTakeaways?.length && (
              <p class="text-base text-[#7d7a75] dark:text-[#b4b1ab] italic">
                No summary available.
              </p>
            )
          )}
        </div>

        {/* Footer actions */}
        <div class="sticky bottom-0 border-t border-[#e6e5e3] bg-white/95 px-6 py-4 backdrop-blur-sm dark:border-[#3b3a37] dark:bg-[#20201e]/95">
          <div class="flex items-center justify-between gap-4 flex-wrap">
            <div class="flex items-center gap-3">
              <RatingStars
                value={localRating}
                onChange={handleRate}
                disabled={saving}
              />
              {savedFlash && (
                <span class="text-xs text-[#1d5f9f] dark:text-[#a6d2f8] font-medium">
                  Saved
                </span>
              )}
            </div>

            <div class="flex items-center gap-2 flex-wrap">
              {/* Dismiss: marks as read and closes the panel so the card
                  vanishes from the default grid view. Only shown while the
                  item has not yet been read. */}
              {onToggleStar && (
                <button
                  type="button"
                  onClick={() => onToggleStar(item)}
                  title={isStarred ? 'Unstar this item' : 'Star to save forever'}
                  class={[
                    'flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors font-medium',
                    isStarred
                      ? 'border-yellow-300 dark:border-yellow-700 text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20'
                      : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-yellow-300 hover:text-yellow-600 dark:hover:text-yellow-400',
                  ].join(' ')}
                >
                  <svg
                    class="w-3.5 h-3.5"
                    fill={isStarred ? 'currentColor' : 'none'}
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.562.562 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"
                    />
                  </svg>
                  {isStarred ? 'Starred' : 'Star'}
                </button>
              )}

              {onDismiss && !isRead && (
                <button
                  type="button"
                  onClick={() => {
                    onDismiss(item.url);
                    onClose();
                  }}
                  title='Dismiss this item'
                  class={[
                    'flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors font-medium',
                    'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400',
                    'hover:border-rose-300 hover:text-rose-600 dark:hover:text-rose-400',
                  ].join(' ')}
                >
                  <svg
                    class='w-3.5 h-3.5'
                    viewBox='0 0 24 24'
                    fill='none'
                    stroke='currentColor'
                    stroke-width='2.5'
                  >
                    <path
                      stroke-linecap='round'
                      stroke-linejoin='round'
                      d='M6 18L18 6M6 6l12 12'
                    />
                  </svg>
                  Dismiss
                </button>
              )}

              {onReadLater && (
                <button
                  type="button"
                  onClick={() => onReadLater(item)}
                  title={
                    isReadLater
                      ? 'Remove from Read Later'
                      : 'Save to Read Later'
                  }
                  class={[
                    'flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors font-medium',
                    isReadLater
                      ? 'border-amber-200 dark:border-amber-800 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20'
                      : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-amber-300 hover:text-amber-600 dark:hover:text-amber-400',
                  ].join(' ')}
                >
                  <svg
                    class="w-3.5 h-3.5"
                    fill={isReadLater ? 'currentColor' : 'none'}
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z"
                    />
                  </svg>
                  {isReadLater ? 'Saved for later' : 'Read later'}
                </button>
              )}

              {onMarkRead && (
                <button
                  type="button"
                  onClick={() => {
                    onMarkRead(item.url);
                    if (!isRead) onClose();
                  }}
                  title={isRead ? 'Mark as unread' : 'Mark as read'}
                  class={[
                    'flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors font-medium',
                    isRead
                      ? 'border-[#9bcaf2] dark:border-[#4f8fc8] text-[#1d5f9f] dark:text-[#a6d2f8] bg-[#e5f2fc] dark:bg-[#1c3852]'
                      : 'border-[#e6e5e3] dark:border-[#3b3a37] text-[#7d7a75] dark:text-[#b4b1ab] hover:border-[#9bcaf2] hover:text-[#1d5f9f] dark:hover:text-[#a6d2f8]',
                  ].join(' ')}
                >
                  <svg
                    class="w-3.5 h-3.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    stroke-width="2.5"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      d="M4.5 12.75l6 6 9-13.5"
                    />
                  </svg>
                  {isRead ? 'Read' : 'Mark read'}
                </button>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
