type BadgeVariant =
  | 'article'
  | 'video'
  | 'watch'
  | 'rss'
  | 'youtube'
  | 'website'
  | 'google_news'
  | 'hackernews'
  | 'reddit'
  | 'github_releases'
  | 'podcast'
  | 'ok'
  | 'error'
  | 'default';

interface BadgeProps {
  variant?: BadgeVariant;
  children: string;
  className?: string;
}

const COLORS: Record<BadgeVariant, string> = {
  article:
    'bg-[#e5f2fc] dark:bg-[#1c3852] text-[#1d5f9f] dark:text-[#a6d2f8]',
  video:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  watch:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  rss:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  youtube:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  website:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  google_news:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  hackernews:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  reddit:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  github_releases:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  podcast:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
  ok:
    'bg-[#e8f6ee] dark:bg-[#193a29] text-[#23683b] dark:text-[#9ad3ab]',
  error:
    'bg-[#fff1ef] dark:bg-[#4a2521] text-[#b9382f] dark:text-[#ff9f96]',
  default:
    'bg-[#f0efed] dark:bg-[#2a2927] text-[#5f5c57] dark:text-[#d0cdc6]',
};

/** Determines badge variant from a possibly legacy or incomplete item kind. */
export function kindVariant(kind: string | null | undefined): BadgeVariant {
  const k = (kind || 'article').toLowerCase();
  if (k === 'article') return 'article';
  if (k === 'video') return 'video';
  if (k === 'watch') return 'watch';
  if (k === 'rss') return 'rss';
  if (k === 'youtube') return 'youtube';
  if (k === 'website') return 'website';
  if (k === 'google_news') return 'google_news';
  if (k === 'hackernews') return 'hackernews';
  if (k === 'reddit') return 'reddit';
  if (k === 'github_releases') return 'github_releases';
  if (k === 'podcast') return 'podcast';
  if (k === 'ok') return 'ok';
  if (k === 'error' || k === 'err') return 'error';
  return 'default';
}

/** Small label badge with color variants. */
export function Badge({ variant = 'default', children, className = '' }: BadgeProps) {
  return (
    <span
      className={[
        'inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold tracking-wide',
        COLORS[variant],
        className,
      ].join(' ')}
    >
      {children}
    </span>
  );
}
