import { useEffect, useState } from 'preact/hooks';
import { Badge, kindVariant } from './Badge';
import { RatingStars } from './RatingStars';
import { cleanSummary, tryParseStructuredSummary } from '../lib/clean-summary';
import {
  parseReadableContent,
} from '../lib/readable-content';
import type {
  ReadableBlock,
  ReadableInline,
} from '../lib/readable-content';
import type { ArticleContent, DigestItem } from '../lib/types';
import { api } from '../lib/api';
import { formatDateOnly } from '../lib/dates';
import { safeExternalUrl } from '../lib/urls';

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

function makeContentKey(
  prefix: string,
  content: string,
  seen: Map<string, number>,
): string {
  const base = `${prefix}-${content.slice(0, 96)}`;
  const occurrence = seen.get(base) ?? 0;
  seen.set(base, occurrence + 1);
  return `${base}-${occurrence}`;
}

function renderInline(inlines: ReadableInline[], keyPrefix: string) {
  const seen = new Map<string, number>();
  return inlines.map((inline) => {
    if (inline.type !== 'link') return inline.text;
    const href = safeExternalUrl(inline.href);
    const key = makeContentKey(
      keyPrefix,
      `${inline.type}:${inline.href}:${inline.text}`,
      seen,
    );
    return href ? (
      <a
        key={key}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-[#1d5f9f] underline decoration-[#9bcaf2] underline-offset-2 hover:text-[#2783de] dark:text-[#a6d2f8] dark:decoration-[#4f8fc8] dark:hover:text-[#63aaf0]"
      >
        {inline.text}
      </a>
    ) : (
      inline.text
    );
  });
}

function readableBlocks(
  blocks: ReadableBlock[],
  keyPrefix: string,
  compact = false,
) {
  const seen = new Map<string, number>();
  return blocks.map((block) => {
    const identity =
      block.type === 'list'
        ? `${block.type}:${block.items.map((item) => item.text).join('|')}`
        : `${block.type}:${block.text}`;
    const key = makeContentKey(keyPrefix, identity, seen);
    if (block.type === 'heading') {
      const HeadingTag = (
        `h${Math.min(6, Math.max(2, block.level ?? 3))}`
      ) as 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
      return (
        <HeadingTag
          key={key}
          className={[
            'break-words font-semibold text-[#2c2c2b] dark:text-[#f4f3f1]',
            compact ? 'text-base' : 'text-lg',
          ].join(' ')}
        >
          {renderInline(block.inlines, key)}
        </HeadingTag>
      );
    }
    if (block.type === 'paragraph') {
      return (
        <p
          key={key}
          className={[
            'break-words [overflow-wrap:anywhere] whitespace-pre-line',
            compact ? '' : 'text-base',
          ].join(' ')}
        >
          {renderInline(block.inlines, key)}
        </p>
      );
    }
    if (block.type === 'blockquote') {
      return (
        <blockquote
          key={key}
          className="break-words [overflow-wrap:anywhere] border-l-2 border-[#9bcaf2] pl-4 italic whitespace-pre-line dark:border-[#4f8fc8]"
        >
          {renderInline(block.inlines, key)}
        </blockquote>
      );
    }
    if (block.type === 'code') {
      return (
        <pre
          key={key}
          className="overflow-x-auto rounded-md bg-[#f0efed] p-3 text-sm leading-relaxed whitespace-pre-wrap dark:bg-[#2a2927]"
        >
          <code>{block.text}</code>
        </pre>
      );
    }
    if (block.type !== 'list') return null;
    const ListTag = block.ordered ? 'ol' : 'ul';
    const itemSeen = new Map<string, number>();
    return (
      <ListTag
        key={key}
        className={[
          'space-y-1.5 pl-5',
          block.ordered ? 'list-decimal' : 'list-disc',
        ].join(' ')}
      >
        {block.items.map((item) => {
          const itemKey = makeContentKey(key, item.text, itemSeen);
          return (
            <li key={itemKey} className="break-words [overflow-wrap:anywhere] pl-1">
              {renderInline(item.inlines, itemKey)}
            </li>
          );
        })}
      </ListTag>
    );
  });
}


function removeLeadingDuplicate(summary: string, tldr: string): string {
  const summaryText = summary.trim();
  const tldrText = tldr.trim();
  if (!summaryText || !tldrText) return summaryText;

  const normalizedSummary = summaryText.toLocaleLowerCase();
  const normalizedTldr = tldrText.toLocaleLowerCase();
  if (!normalizedSummary.startsWith(normalizedTldr)) return summaryText;

  const remainder = summaryText.slice(tldrText.length);
  if (remainder && !/^[\s.!?…,:;)\]}]/u.test(remainder)) return summaryText;
  return remainder.replace(/^[\s.!?…,:;)\]}]+/u, '').trim();
}

interface ItemDetailContentProps {
  item: DigestItem;
  metaParts: string[];
  tldr?: string;
  keyTakeaways?: string[];
  segments: ReadableBlock[];
  takeawaySeen: Map<string, number>;
  articleLoading: boolean;
  articleError: string | null;
  articleBlocks: ReadableBlock[];
}

function ItemDetailContent({
  item,
  metaParts,
  tldr,
  keyTakeaways,
  segments,
  takeawaySeen,
  articleLoading,
  articleError,
  articleBlocks,
}: ItemDetailContentProps) {
  return (
    <>
        {/* Content */}
        <div className="flex-1 px-6 py-6 space-y-5">

          {/* Badges */}
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={kindVariant(item.kind || 'article')}>
              {item.kind || 'article'}
            </Badge>
            {item.category && (
              <span className="text-xs font-medium text-[#7d7a75] dark:text-[#b4b1ab]">
                {item.category}
              </span>
            )}
          </div>

          {/* Title */}
          <h1 id="detail-title" className="break-words [overflow-wrap:anywhere] text-3xl font-semibold tracking-tight text-[#2c2c2b] dark:text-[#f4f3f1] leading-tight">
            {item.title || 'Untitled'}
          </h1>

          {/* Meta */}
          {metaParts.length > 0 && (
            <p className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
              {metaParts.join(' · ')}
            </p>
          )}


          {/* TL;DR */}
          {tldr && (
            <div className="space-y-2">
              <h2 className="text-sm font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
                TL;DR
              </h2>
              <p className="break-words [overflow-wrap:anywhere] text-base font-medium text-[#2c2c2b] dark:text-[#f4f3f1] leading-relaxed">
                {tldr}
              </p>
            </div>
          )}

          {/* Key Takeaways */}
          {keyTakeaways && keyTakeaways.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-sm font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
                Key Takeaways
              </h2>
              <ul className="space-y-2 pl-0 list-none">
                {keyTakeaways.map((point) => (
                  <li key={makeContentKey('takeaway', point, takeawaySeen)} className="break-words [overflow-wrap:anywhere] flex gap-2.5 text-base text-[#5f5c57] dark:text-[#d0cdc6] leading-relaxed">
                    <span
                      className="mt-[0.45em] flex-shrink-0 w-1.5 h-1.5 rounded-full bg-[#2783de] dark:bg-[#63aaf0]"
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
            <hr className="border-[#e6e5e3] dark:border-[#3b3a37]" />
          )}

          {/* Summary */}
          {segments.length > 0 ? (
            <div className="space-y-3">
              <h2 className="text-sm font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
                Summary
              </h2>
              <div className="break-words [overflow-wrap:anywhere] space-y-3 text-base text-[#5f5c57] dark:text-[#d0cdc6] leading-relaxed">
                {readableBlocks(segments, 'summary', true)}
              </div>
            </div>
          ) : (
            !tldr && !keyTakeaways?.length && (
              <p className="text-base text-[#7d7a75] dark:text-[#b4b1ab] italic">
                No summary available.
              </p>
            )
          )}
          {/* Full stored article text */}
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-[#7d7a75] dark:text-[#b4b1ab]">
                Full article
              </h2>
              <span className="text-xs text-[#9a9791] dark:text-[#8d8a84]">
                Reader view
              </span>
            </div>
            {articleLoading && (
              <p
                className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]"
                aria-live="polite"
              >
                Loading full article...
              </p>
            )}
            {!articleLoading && articleError && (
              <p className="text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
                {articleError}
              </p>
            )}
            {!articleLoading && !articleError && (
              <div className="break-words [overflow-wrap:anywhere] space-y-4 text-base leading-relaxed text-[#5f5c57] dark:text-[#d0cdc6]">
                {articleBlocks.length > 0 ? (
                  readableBlocks(articleBlocks, 'article')
                ) : (
                  <p>Full article text is not available for this source.</p>
                )}
              </div>
            )}
          </section>

          {/* Divider */}
          <hr className="border-[#e6e5e3] dark:border-[#3b3a37]" />
        </div>
        </>
  );
}

interface ItemDetailFooterProps {
  item: DigestItem;
  isRead: boolean;
  onClose: () => void;
  onRate?: (url: string, rating: number) => void;
  onMarkRead?: (url: string) => void;
  onReadLater?: (item: DigestItem) => void;
  isReadLater: boolean;
  onDismiss?: (url: string) => void;
  onToggleStar?: (item: DigestItem) => void;
  isStarred: boolean;
  handleRate: (rating: number) => void;
  localRating: number | null;
  saving: boolean;
  savedFlash: boolean;
}

function ItemDetailFooter({
  item,
  isRead,
  onClose,
  onRate,
  onMarkRead,
  onReadLater,
  isReadLater,
  onDismiss,
  onToggleStar,
  isStarred,
  handleRate,
  localRating,
  saving,
  savedFlash,
}: ItemDetailFooterProps) {
  return (
    <>
        {/* Footer actions */}
        <div className="sticky bottom-0 border-t border-[#e6e5e3] bg-white/95 px-6 py-4 backdrop-blur-sm dark:border-[#3b3a37] dark:bg-[#20201e]/95">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              {onRate && (
                <>
                  <RatingStars
                    value={localRating}
                    onChange={handleRate}
                    disabled={saving}
                  />
                  {savedFlash && (
                    <span className="text-xs text-[#1d5f9f] dark:text-[#a6d2f8] font-medium">
                      Saved
                    </span>
                  )}
                </>
              )}
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {/* Dismiss: marks as read and closes the panel so the card
                  vanishes from the default grid view. Only shown while the
                  item has not yet been read. */}
              {onToggleStar && (
                <button
                  type="button"
                  onClick={() => onToggleStar(item)}
                  title={isStarred ? 'Unstar this item' : 'Star to save forever'}
                  className={[
                    'flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors font-medium',
                    isStarred
                      ? 'border-yellow-300 dark:border-yellow-700 text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20'
                      : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-yellow-300 hover:text-yellow-600 dark:hover:text-yellow-400',
                  ].join(' ')}
                >
                  <svg
                    className="w-3.5 h-3.5"
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
                  className={[
                    'flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors font-medium',
                    'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400',
                    'hover:border-rose-300 hover:text-rose-600 dark:hover:text-rose-400',
                  ].join(' ')}
                >
                  <svg
                    className='w-3.5 h-3.5'
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
                  className={[
                    'flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors font-medium',
                    isReadLater
                      ? 'border-amber-200 dark:border-amber-800 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20'
                      : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-amber-300 hover:text-amber-600 dark:hover:text-amber-400',
                  ].join(' ')}
                >
                  <svg
                    className="w-3.5 h-3.5"
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
                  className={[
                    'flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors font-medium',
                    isRead
                      ? 'border-[#9bcaf2] dark:border-[#4f8fc8] text-[#1d5f9f] dark:text-[#a6d2f8] bg-[#e5f2fc] dark:bg-[#1c3852]'
                      : 'border-[#e6e5e3] dark:border-[#3b3a37] text-[#7d7a75] dark:text-[#b4b1ab] hover:border-[#9bcaf2] hover:text-[#1d5f9f] dark:hover:text-[#a6d2f8]',
                  ].join(' ')}
                >
                  <svg
                    className="w-3.5 h-3.5"
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
    </>
  );
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
  const directTldr = item.tldr ? cleanSummary(item.tldr) : '';
  const fallbackTldr = jsonFallback?.tldr
    ? cleanSummary(jsonFallback.tldr)
    : '';
  const tldr = directTldr || fallbackTldr;
  const directTakeaways = item.key_takeaways?.flatMap((point) => {
    const cleaned = cleanSummary(point);
    return cleaned ? [cleaned] : [];
  });
  const fallbackTakeaways = jsonFallback?.key_takeaways?.flatMap((point) => {
    const cleaned = cleanSummary(point);
    return cleaned ? [cleaned] : [];
  });
  const keyTakeaways =
    directTakeaways && directTakeaways.length > 0
      ? directTakeaways
      : fallbackTakeaways;
  const rawSummary = jsonFallback?.summary ?? (jsonFallback ? '' : item.summary);
  const summaryText = cleanSummary(rawSummary);
  const dedupedSummary = removeLeadingDuplicate(summaryText, tldr);
  const segments = parseReadableContent(dedupedSummary);
  const date = formatDateOnly(item.published_at, { year: true });
  const metaParts: string[] = [];
  if (item.source) metaParts.push(item.source);
  if (date) metaParts.push(date);
  const externalUrl = safeExternalUrl(item.url);
  const imageUrl = safeExternalUrl(item.image_url);
  const takeawaySeen = new Map<string, number>();

  const [localRating, setLocalRating] = useState<number | null>(
    rating ?? null,
  );
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [articleContent, setArticleContent] = useState<ArticleContent | null>(
    null,
  );
  const [articleLoading, setArticleLoading] = useState(true);
  const [articleError, setArticleError] = useState<string | null>(null);

  /** Keep local star state in sync when the parent's ratings map updates. */
  useEffect(() => {
    setLocalRating(rating ?? null);
  }, [rating]);

  useEffect(() => {
    let active = true;
    setArticleContent(null);
    setArticleError(null);
    setArticleLoading(true);

    api
      .getArticleContent(item.url)
      .then((content) => {
        if (active) setArticleContent(content);
      })
      .catch(() => {
        if (active) {
          setArticleError(
            'Full article text is not available for this source.',
          );
        }
      })
      .finally(() => {
        if (active) setArticleLoading(false);
      });

    return () => {
      active = false;
    };
  }, [item.url]);

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

  const articleBlocks = articleContent
    ? parseReadableContent(articleContent.content)
    : [];

  return (
    /* Backdrop */
    <dialog
      open
      className="fixed inset-0 z-50 m-0 flex h-full w-full max-w-none justify-end border-0 bg-transparent p-0"
      aria-modal="true"
      aria-labelledby="detail-title"
    >
      {/* Semi-transparent backdrop - click closes */}
      <div
        className="absolute inset-0 bg-[#2c2c2b]/45"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div className="relative z-10 flex h-full w-full max-w-2xl flex-col overflow-y-auto border-l border-[#e6e5e3] bg-white dark:border-[#3b3a37] dark:bg-[#20201e]">

        {/* Top bar */}
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-[#e6e5e3] bg-white/95 px-5 py-3 backdrop-blur-sm dark:border-[#3b3a37] dark:bg-[#20201e]/95">
          <button
            type="button"
            onClick={onClose}
            className="flex items-center gap-1.5 text-sm text-[#7d7a75] dark:text-[#b4b1ab] hover:text-[#2c2c2b] dark:hover:text-[#f4f3f1] transition-colors"
            aria-label="Close detail panel"
          >
            <svg
              className="w-4 h-4"
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
            href={externalUrl}
            target={externalUrl ? '_blank' : undefined}
            rel={externalUrl ? 'noopener noreferrer' : undefined}
            className="flex items-center gap-1.5 text-sm font-medium text-[#1d5f9f] dark:text-[#a6d2f8] hover:text-[#2783de] dark:hover:text-[#63aaf0] transition-colors"
          >
            Open original
            <svg
              className="w-3.5 h-3.5"
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
        {imageUrl && (
          <img
            src={imageUrl}
            alt=""
            loading="lazy"
            className="w-full max-h-64 object-cover bg-[#f0efed] dark:bg-[#2a2927]"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = 'none';
            }}
          />
        )}
        <ItemDetailContent
          item={item}
          metaParts={metaParts}
          tldr={tldr}
          keyTakeaways={keyTakeaways}
          segments={segments}
          takeawaySeen={takeawaySeen}
          articleLoading={articleLoading}
          articleError={articleError}
          articleBlocks={articleBlocks}
        />
        <ItemDetailFooter
          item={item}
          isRead={isRead}
          onClose={onClose}
          onRate={onRate}
          onMarkRead={onMarkRead}
          onReadLater={onReadLater}
          isReadLater={isReadLater}
          onDismiss={onDismiss}
          onToggleStar={onToggleStar}
          isStarred={isStarred}
          handleRate={handleRate}
          localRating={localRating}
          saving={saving}
          savedFlash={savedFlash}
        />



      </div>
    </dialog>
  );
}
