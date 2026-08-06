import { useState, useEffect } from 'preact/hooks';
import { Badge, kindVariant } from './Badge';
import { RatingStars } from './RatingStars';
import {
  cleanSummary,
  tryParseStructuredSummary,
} from '../lib/clean-summary';
import type { DigestItem, ScoreBreakdown } from '../lib/types';
import { api } from '../lib/api';
import { formatDateOnly } from '../lib/dates';
import { safeExternalUrl } from '../lib/urls';

/** Human-readable labels for each score signal. */
const SIGNAL_LABELS: Record<string, string> = {
  keyword_high: 'Keyword (high)',
  keyword_negative: 'Keyword (negative)',
  keyword_medium: 'Keyword (medium)',
  term_overlap: 'Topic terms',
  bigram_overlap: 'Topic phrases',
  tfidf_cosine: 'Content similarity',
  category: 'Category',
  source: 'Source',
  implicit_content: 'Read/saved content',
  implicit_category: 'Read/saved category',
  implicit_source: 'Read/saved source',
  synonym_boost: 'Related topics',
  embedding_similarity: 'Semantic similarity',
  topic_score: 'Topic match',
  llm_rerank: 'AI relevance',
};

/** Collapsible score breakdown panel shown at the bottom of each card. */
function ScoreBreakdownPanel({
  breakdown = {},
  score,
}: {
  breakdown?: Partial<ScoreBreakdown>;
  score?: number;
}) {
  const [open, setOpen] = useState(false);
  const nonZero = Object.entries(breakdown).filter(
    ([k, v]) => k !== 'llm_reason' && typeof v === 'number' && Math.abs(v as number) > 0.001,
  ) as [string, number][];

  if (nonZero.length === 0 && typeof score !== 'number') return null;

  const maxAbs = Math.max(...nonZero.map(([, v]) => Math.abs(v as number)), 0.1);
  const llmReason = breakdown.llm_reason;

  return (
    <div className="pt-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className="flex items-center gap-1 text-xs text-[#7d7a75] dark:text-[#b4b1ab] hover:text-[#2c2c2b] dark:hover:text-[#f4f3f1] transition-colors"
      >
        <svg
          className={`w-3 h-3 transition-transform ${open ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2.5"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M8.25 4.5l7.5 7.5-7.5 7.5"
          />
        </svg>
        <span>Why ranked here?</span>
        {typeof score === 'number' && (
          <span className="ml-1 font-mono text-[#2c2c2b] dark:text-[#f4f3f1]">
            Total {score >= 0 ? '+' : ''}
            {score.toFixed(2)}
          </span>
        )}
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {nonZero.length > 0 ? (
            nonZero.map(([key, val]) => {
              const pct = (Math.abs(val) / maxAbs) * 100;
              const isPos = val >= 0;
              const label = SIGNAL_LABELS[key] ?? key;
              return (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-xs text-[#7d7a75] dark:text-[#b4b1ab] w-32 flex-shrink-0 truncate">
                    {label}
                  </span>
                  <div className="flex-1 flex items-center gap-1">
                    <div className="flex-1 bg-[#f0efed] dark:bg-[#2a2927] rounded-full h-1.5 overflow-hidden">
                      <div
                        className={`h-1.5 rounded-full ${isPos ? 'bg-[#2783de] dark:bg-[#63aaf0]' : 'bg-[#b9382f] dark:bg-[#ff9f96]'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span
                      className={`text-xs font-mono w-10 text-right flex-shrink-0 ${isPos ? 'text-[#1d5f9f] dark:text-[#a6d2f8]' : 'text-[#b9382f] dark:text-[#ff9f96]'}`}
                    >
                      {isPos ? '+' : ''}
                      {val.toFixed(2)}
                    </span>
                  </div>
                </div>
              );
            })
          ) : (
            <p className="text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
              No component details available.
            </p>
          )}
          {llmReason && (
            <p className="text-xs text-slate-400 dark:text-slate-500 italic pt-0.5">
              AI: {llmReason}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

interface DigestCardProps {
  item: DigestItem;
  /** Omit every personal action when rendering the public publication. */
  readOnly?: boolean;
  /** Called with (url, newRating) after a successful save so the parent can
   *  update its own state map. */
  onRate?: (url: string, rating: number) => void;
  /** Called with the item URL to toggle its read state. */
  onMarkRead?: (url: string) => void;
  /** Whether this item has been marked as read. */
  isRead?: boolean;
  /** Opens the detail panel for this item. */
  onSelect?: (item: DigestItem) => void;
  /** Called when the user clicks "Read Later" to toggle save state. */
  onReadLater?: (item: DigestItem) => void;
  /** Whether this item is currently saved to read later. */
  isReadLater?: boolean;
  /**
   * Called when the user dismisses this card. Typically marks the item as
   * read so it disappears from the default (hide-read) view.
   */
  onDismiss?: (url: string) => void;
  /** Called when the user toggles the starred state of this item. */
  onToggleStar?: (item: DigestItem) => void;
  /** Whether this item is currently starred. */
  isStarred?: boolean;
}

interface DigestCardActionsProps {
  item: DigestItem;
  readOnly: boolean;
  isRead: boolean;
  isReadLater: boolean;
  isStarred: boolean;
  onMarkRead?: (url: string) => void;
  onReadLater?: (item: DigestItem) => void;
  onToggleStar?: (item: DigestItem) => void;
  handleRate: (rating: number) => void;
  localRating: number | null;
  saving: boolean;
  savedFlash: boolean;
  readLaterFlash: boolean;
  starFlash: boolean;
  setReadLaterFlash: (value: boolean) => void;
  setStarFlash: (value: boolean) => void;
}

function DigestCardActions({
  item,
  readOnly,
  isRead,
  isReadLater,
  isStarred,
  onMarkRead,
  onReadLater,
  onToggleStar,
  handleRate,
  localRating,
  saving,
  savedFlash,
  readLaterFlash,
  starFlash,
  setReadLaterFlash,
  setStarFlash,
}: DigestCardActionsProps) {
  return (
    <>
      {item.url && (
        <div className="mt-1 border-t border-[#e6e5e3] pb-1 pt-3 dark:border-[#3b3a37]">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 shrink-0">
              {onToggleStar && (
                <button
                  type="button"
                  onClick={() => {
                    onToggleStar(item);
                    if (!isStarred) {
                      setStarFlash(true);
                      setTimeout(() => setStarFlash(false), 2000);
                    }
                  }}
                  title={isStarred ? 'Unstar this item' : 'Star to save forever'}
                  className={[
                    'flex items-center gap-1 text-xs px-2 py-1 rounded-md border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors',
                    isStarred
                      ? 'border-yellow-300 dark:border-yellow-700 text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20'
                      : starFlash
                        ? 'border-yellow-300 text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20'
                        : 'border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-500 hover:border-yellow-300 hover:text-yellow-600 dark:hover:text-yellow-400',
                  ].join(' ')}
                >
                  <svg
                    className="w-3 h-3"
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

              {onReadLater && (
                <button
                  type="button"
                  onClick={() => {
                    onReadLater(item);
                    if (!isReadLater) {
                      setReadLaterFlash(true);
                      setTimeout(() => setReadLaterFlash(false), 2000);
                    }
                  }}
                  title={
                    isReadLater ? 'Remove from Read Later' : 'Save to Read Later'
                  }
                  className={[
                    'flex items-center gap-1 text-xs px-2 py-1 rounded-md border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors',
                    isReadLater
                      ? 'border-amber-200 dark:border-amber-800 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20'
                      : readLaterFlash
                        ? 'border-amber-300 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20'
                        : 'border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-500 hover:border-amber-300 hover:text-amber-600 dark:hover:text-amber-400',
                  ].join(' ')}
                >
                  <svg
                    className="w-3 h-3"
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
                  {isReadLater ? 'Saved' : 'Read later'}
                </button>
              )}

              {onMarkRead && (
                <button
                  type="button"
                  onClick={() => onMarkRead(item.url)}
                  title={isRead ? 'Mark as unread' : 'Mark as read'}
                  className={[
                    'flex items-center gap-1 text-xs px-2 py-1 rounded-md border active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[#2783de]',
                    'transition-colors',
                    isRead
                      ? 'border-[#9bcaf2] dark:border-[#4f8fc8] text-[#1d5f9f] dark:text-[#a6d2f8] bg-[#e5f2fc] dark:bg-[#1c3852]'
                      : 'border-[#e6e5e3] dark:border-[#3b3a37] text-[#7d7a75] dark:text-[#b4b1ab] hover:border-[#9bcaf2] hover:text-[#1d5f9f] dark:hover:text-[#a6d2f8]',
                  ].join(' ')}
                >
                  <svg
                    className="w-3 h-3"
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

            {!readOnly && (
              <div className="flex items-center gap-2 shrink-0 sm:ml-auto">
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
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

/**
 * Single article / video / watch card with title, summary,
 * category badge, source, published date, inline star rating,
 * and a mark-as-read toggle.
 */
export function DigestCard({
  item,
  readOnly = false,
  onRate,
  onMarkRead,
  isRead = false,
  onSelect,
  onReadLater,
  isReadLater = false,
  onDismiss,
  onToggleStar,
  isStarred = false,
}: DigestCardProps) {
  const structuredSummary = item.summary
    ? tryParseStructuredSummary(item.summary)
    : null;
  const tldr = item.tldr?.trim() || structuredSummary?.tldr;
  const summary = cleanSummary(tldr || item.summary);
  const externalUrl = safeExternalUrl(item.url);
  const imageUrl = safeExternalUrl(item.image_url);
  const metaParts: string[] = [];
  if (item.source) metaParts.push(item.source);
  const date = formatDateOnly(item.published_at);
  if (date) metaParts.push(date);

  /** Local rating mirrors the parent map so the stars feel instant. */
  const [localRating, setLocalRating] = useState<number | null>(
    item.rating ?? null,
  );
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [readLaterFlash, setReadLaterFlash] = useState(false);
  const [starFlash, setStarFlash] = useState(false);

  /**
   * Sync local star display whenever the parent updates item.rating
   * (e.g. after localStorage or API ratings are loaded post-mount).
   */
  useEffect(() => {
    setLocalRating(item.rating ?? null);
  }, [item.rating]);

  async function handleRate(rating: number) {
    if (readOnly || saving) return;
    setLocalRating(rating);
    setSaving(true);
    try {
      await api.submitRating(item.url, rating);
      onRate?.(item.url, rating);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
    } catch {
      /* best-effort: star UI stays updated even if the network call fails */
    } finally {
      setSaving(false);
    }
  }

  return (
    <article
      className={[
        'relative flex flex-col gap-3 bg-white dark:bg-[#20201e] rounded-lg p-5 pl-6 transition-colors overflow-hidden',
        isRead
          ? 'border border-[#e6e5e3] dark:border-[#3b3a37] opacity-55 hover:opacity-80'
          : 'border border-[#e6e5e3] dark:border-[#3b3a37] hover:bg-[#f9f8f7] dark:hover:bg-[#2a2927]',
      ].join(' ')}
    >
      {/* Left accent strip acts as a clear visual start-of-card marker */}
      <div
        className={[
          'absolute inset-y-0 left-0 w-1',
          isRead
            ? 'bg-[#b8d8f3] dark:bg-[#2d5c87]'
            : 'bg-[#2783de] dark:bg-[#63aaf0]',
        ].join(' ')}
      />

      {/* Dismiss button: top-right corner, icon-only, does not add to the
          bottom-bar clutter and works equally well on touch devices. */}
      {onDismiss && !isRead && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss(item.url);
          }}
          title='Dismiss'
          aria-label='Dismiss this item'
          className={[
            'absolute top-2 right-2 p-1.5 rounded-md',
            'text-slate-300 dark:text-slate-600',
            'hover:text-slate-500 dark:hover:text-slate-400',
            'hover:bg-slate-100 dark:hover:bg-slate-800',
            'transition-colors',
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
        </button>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant={kindVariant(item.kind)}>{item.kind}</Badge>
        {item.category && (
          <span className="text-xs text-[#7d7a75] dark:text-[#b4b1ab] font-medium">
            {item.category}
          </span>
        )}
        {item.highlighted && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
            </svg>
            Highlighted
          </span>
        )}
      </div>

      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-[#2c2c2b] dark:text-[#f4f3f1] leading-snug">
            {/*
             * When a detail panel is available, left-click opens it.
             * The href is still present so right-click / middle-click opens the
             * source URL directly in a new tab.
             */}
            <a
              href={externalUrl}
              target={externalUrl ? '_blank' : undefined}
              rel={externalUrl ? 'noopener noreferrer' : undefined}
              onClick={
                onSelect
                  ? (e) => {
                      e.preventDefault();
                      onSelect(item);
                    }
                  : undefined
              }
              className={[
                'transition-colors',
                onSelect
                  ? 'cursor-pointer hover:text-[#1d5f9f] dark:hover:text-[#a6d2f8]'
                  : 'hover:text-[#1d5f9f] dark:hover:text-[#a6d2f8]',
              ].join(' ')}
            >
              {item.title || 'Untitled'}
            </a>
          </h3>

          {metaParts.length > 0 && (
            <p className="mt-1 text-xs text-[#7d7a75] dark:text-[#b4b1ab]">
              {metaParts.join(' · ')}
            </p>
          )}
        </div>

        {imageUrl && (
          <img
            src={imageUrl}
            alt=""
            loading="lazy"
            className="flex-shrink-0 w-20 h-20 rounded-md object-cover bg-slate-100 dark:bg-slate-800"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = 'none';
            }}
          />
        )}
      </div>

      {summary && (
        <button
          type="button"
          className={[
            'w-full text-left text-base text-[#5f5c57] dark:text-[#d0cdc6] leading-relaxed line-clamp-4',
            onSelect ? 'cursor-pointer' : 'cursor-default',
          ].join(' ')}
          onClick={onSelect ? () => onSelect(item) : undefined}
        >
          {summary}
        </button>
      )}

      {item.relevance_to_you && (
        <p className="text-sm text-[#1d5f9f] dark:text-[#a6d2f8] bg-[#e5f2fc] dark:bg-[#1c3852] rounded-md px-2.5 py-1.5 leading-relaxed">
          {item.relevance_to_you}
        </p>
      )}

      {item.topics && item.topics.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {item.topics.slice(0, 5).map((t) => (
            <span
              key={t}
              className="text-xs px-1.5 py-0.5 rounded-md bg-[#f0efed] dark:bg-[#2a2927] text-[#7d7a75] dark:text-[#b4b1ab]"
            >
              {t}
            </span>
          ))}
          {item.novelty !== undefined && item.novelty >= 4 && (
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400 font-medium">
              novel
            </span>
          )}
        </div>
      )}

      {(item.score_breakdown ||
        typeof item.preference_score === 'number') && (
        <ScoreBreakdownPanel
          breakdown={item.score_breakdown}
          score={item.preference_score}
        />
      )}
      <DigestCardActions
        item={item}
        readOnly={readOnly}
        isRead={isRead}
        isReadLater={isReadLater}
        isStarred={isStarred}
        onMarkRead={onMarkRead}
        onReadLater={onReadLater}
        onToggleStar={onToggleStar}
        handleRate={handleRate}
        localRating={localRating}
        saving={saving}
        savedFlash={savedFlash}
        readLaterFlash={readLaterFlash}
        starFlash={starFlash}
        setReadLaterFlash={setReadLaterFlash}
        setStarFlash={setStarFlash}
      />

    </article>
  );
}
