/** Return only web URLs that are safe to use in external links. */
export function safeExternalUrl(
  value: string | null | undefined,
): string | undefined {
  const raw = (value ?? '').trim();
  if (!raw) return undefined;

  try {
    const parsed = new URL(raw);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
      ? raw
      : undefined;
  } catch {
    return undefined;
  }
}
