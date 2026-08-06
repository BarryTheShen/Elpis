const LOCAL_DATE_PARTS = new Intl.DateTimeFormat('en-CA', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});
const DATE_ONLY_FORMATTER = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
});
const DATE_ONLY_YEAR_FORMATTER = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});
const DIGEST_LABEL_FORMATTER = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const DIGEST_SUBTITLE_TIME_ZONE =
  Intl.DateTimeFormat().resolvedOptions().timeZone;
const DIGEST_SUBTITLE_DATE_FORMATTER = new Intl.DateTimeFormat(undefined, {
  timeZone: DIGEST_SUBTITLE_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const DIGEST_SUBTITLE_ZONE_FORMATTER = new Intl.DateTimeFormat(undefined, {
  timeZone: DIGEST_SUBTITLE_TIME_ZONE,
  timeZoneName: 'short',
});

/** YYYY-MM-DD in the user's local timezone (for date-range filters). */
export function localDateKey(iso?: string): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
    const parts = LOCAL_DATE_PARTS.formatToParts(d);
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
    return `${get('year')}-${get('month')}-${get('day')}`;
  } catch {
    return iso.slice(0, 10);
  }
}

/** Locale-aware calendar date (no time). */
export function formatDateOnly(
  iso?: string,
  opts: { year?: boolean } = {},
): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
    const formatter = opts.year
      ? DATE_ONLY_YEAR_FORMATTER
      : DATE_ONLY_FORMATTER;
    return formatter.format(d);
  } catch {
    return iso.slice(0, 10);
  }
}

/** Format a UTC ISO timestamp for the digest sidebar (locale date/time, local TZ). */
export function formatDigestLabel(utcIso: string): string {
  try {
    const d = new Date(utcIso);
    if (Number.isNaN(d.getTime())) {
      return utcIso.slice(0, 16).replace('T', ' ');
    }
    return DIGEST_LABEL_FORMATTER.format(d);
  } catch {
    return utcIso.slice(0, 16).replace('T', ' ');
  }
}

/** Format a UTC ISO timestamp for the digest page subtitle (with TZ abbreviation). */
export function formatDigestSubtitle(utcIso: string): string {
  try {
    const d = new Date(utcIso);
    const parts = DIGEST_SUBTITLE_DATE_FORMATTER.formatToParts(d);
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
    const dateStr = `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`;
    const tzAbbr =
      DIGEST_SUBTITLE_ZONE_FORMATTER.formatToParts(d)
        .find((p) => p.type === 'timeZoneName')?.value ??
      DIGEST_SUBTITLE_TIME_ZONE;
    return `${dateStr} ${tzAbbr}`;
  } catch {
    return utcIso.slice(0, 16).replace('T', ' ') + ' UTC';
  }
}
