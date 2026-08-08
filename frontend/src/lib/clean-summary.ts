/**
 * Helpers for turning model output into user-facing summary text.
 *
 * Some older records contain the complete structured response in `summary`,
 * while newer records have dedicated fields.  Model providers may also leave
 * reasoning tags, markdown fences, or a short preamble around the answer.
 * These functions keep those transport artifacts out of the reader UI.
 */
const PREFIX_RE =
  /^(?:here\s+is\s+(?:a\s+)?(?:\d+[-\u2013]\d+\s+sentence\s+)?(?:brief\s+)?summary[^:]*:|this\s+(?:is\s+(?:a|an)\s+)?(?:\d+[-\u2013]\d+\s+sentence\s+)?(?:brief\s+)?summary[^:]*:)\s*/i;
const NOTE_SUFFIX_RE = /\n+\s*(?:note|notes|disclaimer)\s*:\s[\s\S]*$/i;
const REASONING_TAG_NAMES =
  '(?:chain-of-thought|chain_of_thought|deliberation|reasoning_content|redacted_thinking|reasoning|reflection|scratchpad|thinking|analysis|thought|think|cot|internal|private)';
const REASONING_TAG_RE = new RegExp(
  `\\s*<${REASONING_TAG_NAMES}\\b[^>]*>[\\s\\S]*?<\\/${REASONING_TAG_NAMES}\\s*>\\s*`,
  'gi',
);
const SELF_CLOSING_REASONING_TAG_RE = new RegExp(
  `<\\/?${REASONING_TAG_NAMES}\\b[^>]*\\/?>`,
  'gi',
);
const UNCLOSED_REASONING_TAG_RE = new RegExp(
  `\\s*<${REASONING_TAG_NAMES}\\b[^>]*>[\\s\\S]*$`,
  'gi',
);
const FENCE_RE = /^\s*```(?:json|text|markdown)?\s*([\s\S]*?)\s*```\s*$/i;
const PLAIN_REASONING_PREFIX_RE =
  /^\s*(?:thinking\s+process|chain\s+of\s+thought|scratchpad|analysis|reasoning|thinking|thought|deliberation|reflection)\s*:\s*/i;
const FINAL_ANSWER_RE =
  /(?:^|\n)\s*(?:final\s+answer|final|answer|response)\s*:\s*/i;

function looksLikePlainReasoning(text: string): boolean {
  return PLAIN_REASONING_PREFIX_RE.test(text);
}



/** Shape of a structured LLM summary that may be stored as raw JSON. */
export interface StructuredSummary {
  tldr?: string;
  key_takeaways?: string[];
  summary?: string;
}

function decodeJsonEscape(next: string, text: string, index: number): string {
  if (next === 'n') return '\n';
  if (next === 'r') return '\r';
  if (next === 't') return '\t';
  if (next === 'b') return '\b';
  if (next === 'f') return '\f';
  if (next === '"') return '"';
  if (next === '\\') return '\\';
  if (next === '/') return '/';
  if (next === 'u' && index + 5 < text.length) {
    const code = Number.parseInt(text.slice(index + 2, index + 6), 16);
    if (Number.isFinite(code)) return String.fromCharCode(code);
  }
  return next;
}

function readQuotedValue(
  text: string,
  openQuoteIdx: number,
): { value: string; nextIndex: number } | null {
  let i = openQuoteIdx + 1;
  let value = '';

  while (i < text.length) {
    const ch = text[i];
    if (ch === '\\' && i + 1 < text.length) {
      value += decodeJsonEscape(text[i + 1], text, i);
      i += text[i + 1] === 'u' ? 6 : 2;
    } else if (ch === '"') {
      return { value, nextIndex: i + 1 };
    } else {
      value += ch;
      i++;
    }
  }

  /* Truncated model output: retain the partial value when it has content. */
  return value ? { value, nextIndex: text.length } : null;
}

function stripReasoningArtifacts(raw: string): string {
  const text = raw
    .replace(REASONING_TAG_RE, '\n')
    .replace(UNCLOSED_REASONING_TAG_RE, '')
    .replace(SELF_CLOSING_REASONING_TAG_RE, '')
    .trim();
  const prefix = text.match(PLAIN_REASONING_PREFIX_RE);
  if (prefix) {
    const remainder = text.slice(prefix[0].length);
    const final = remainder.match(FINAL_ANSWER_RE);
    if (final) return remainder.slice(final.index! + final[0].length).trim();

    /* Keep a structured payload even when the provider omitted a final label. */
    const structured = remainder.search(/```(?:json)?\s*\{|\{/i);
    return structured >= 0 ? remainder.slice(structured).trim() : '';
  }
  return text
    .replace(/^\s*(?:final answer|final|answer|response)\s*:\s*/gim, '')
    .trim();
}

function cleanProseField(raw: string): string {
  let text = stripReasoningArtifacts(raw).trim();
  if (!text || !/[^\s.…]/.test(text)) return '';
  const fenced = text.match(FENCE_RE);
  if (fenced) text = fenced[1].trim();
  if (looksLikePlainReasoning(text)) return '';
  text = text.replace(PREFIX_RE, '').replace(NOTE_SUFFIX_RE, '').trim();
  return text;
}

function findJsonObjects(text: string): string[] {
  const candidates: string[] = [];
  for (let start = text.indexOf('{'); start !== -1; ) {
    let depth = 0;
    let inString = false;
    let escaped = false;
    let end = -1;

    for (let i = start; i < text.length; i++) {
      const ch = text[i];
      if (inString) {
        if (escaped) escaped = false;
        else if (ch === '\\') escaped = true;
        else if (ch === '"') inString = false;
        continue;
      }
      if (ch === '"') {
        inString = true;
      } else if (ch === '{') {
        depth++;
      } else if (ch === '}') {
        depth--;
        if (depth === 0) {
          end = i + 1;
          break;
        }
      }
    }

    candidates.push(text.slice(start, end === -1 ? text.length : end));
    start = text.indexOf('{', start + 1);
  }
  return candidates;
}

function extractJsonField(text: string, field: string): string | null {
  const needle = `"${field}"`;
  let searchFrom = 0;

  while (searchFrom < text.length) {
    const fieldIdx = text.indexOf(needle, searchFrom);
    if (fieldIdx === -1) return null;
    searchFrom = fieldIdx + needle.length;

    const colonIdx = text.indexOf(':', searchFrom);
    if (colonIdx === -1) return null;
    let valueStart = colonIdx + 1;
    while (valueStart < text.length && /\s/.test(text[valueStart])) valueStart++;
    if (text[valueStart] !== '"') continue;

    return readQuotedValue(text, valueStart)?.value ?? null;
  }

  return null;
}

function extractJsonArray(text: string, field: string): string[] {
  const needle = `"${field}"`;
  const fieldIdx = text.indexOf(needle);
  if (fieldIdx === -1) return [];
  const colonIdx = text.indexOf(':', fieldIdx + needle.length);
  if (colonIdx === -1) return [];
  const arrayStart = text.indexOf('[', colonIdx + 1);
  if (arrayStart === -1) return [];

  let depth = 0;
  let inString = false;
  let escaped = false;
  let arrayEnd = text.length;
  for (let i = arrayStart; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === '[') depth++;
    else if (ch === ']') {
      depth--;
      if (depth === 0) {
        arrayEnd = i;
        break;
      }
    }
  }

  const values: string[] = [];
  let cursor = arrayStart + 1;
  while (cursor < arrayEnd) {
    const quote = text.indexOf('"', cursor);
    if (quote === -1 || quote >= arrayEnd) break;
    const value = readQuotedValue(text, quote);
    if (!value) break;
    values.push(value.value);
    cursor = value.nextIndex;
  }
  return values;
}

function normalizeStructuredObject(value: unknown): StructuredSummary | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
  const object = value as Record<string, unknown>;
  const tldr = typeof object.tldr === 'string' ? cleanProseField(object.tldr) : '';
  const summary = typeof object.summary === 'string' ? cleanProseField(object.summary) : '';
  const rawTakeaways = object.key_takeaways;
  const keyTakeaways = Array.isArray(rawTakeaways)
    ? rawTakeaways.flatMap((point) => {
        if (typeof point !== 'string') return [];
        const cleaned = cleanProseField(point);
        return cleaned ? [cleaned] : [];
      })
    : typeof rawTakeaways === 'string'
      ? rawTakeaways
          .split(/\r?\n/)
          .flatMap((point) => {
            const cleaned = cleanProseField(
              point.replace(/^\s*(?:[-*+] |\d+[.)]\s+)/, ''),
            );
            return cleaned ? [cleaned] : [];
          })
      : [];

  if (!tldr && !summary && keyTakeaways.length === 0) return null;
  return {
    tldr: tldr || undefined,
    summary: summary || undefined,
    key_takeaways: keyTakeaways.length > 0 ? keyTakeaways : undefined,
  };
}

/**
 * Attempt to parse a structured summary, including output wrapped in a
 * reasoning block, preamble, Markdown JSON fence, or truncated JSON.
 */
export function tryParseStructuredSummary(raw: string): StructuredSummary | null {
  if (!raw?.trim()) return null;
  const candidate = stripReasoningArtifacts(raw);
  const fenced = candidate.match(FENCE_RE)?.[1]?.trim() ?? candidate;
  const candidates = [fenced, ...findJsonObjects(fenced)];

  for (const objectText of candidates) {
    try {
      const parsed = normalizeStructuredObject(JSON.parse(objectText));
      if (parsed) return parsed;
    } catch {
      /* Fall through to the lenient field extraction below. */
    }
  }

  const tldr = extractJsonField(fenced, 'tldr');
  const summary = extractJsonField(fenced, 'summary');
  const keyTakeaways = extractJsonArray(fenced, 'key_takeaways');
  const cleanedTldr = tldr ? cleanProseField(tldr) : '';
  const cleanedSummary = summary ? cleanProseField(summary) : '';
  const cleanedTakeaways = keyTakeaways.flatMap((point) => {
    const cleaned = cleanProseField(point);
    return cleaned ? [cleaned] : [];
  });
  if (!cleanedTldr && !cleanedSummary && cleanedTakeaways.length === 0) return null;
  return {
    tldr: cleanedTldr || undefined,
    summary: cleanedSummary || undefined,
    key_takeaways: cleanedTakeaways.length > 0 ? cleanedTakeaways : undefined,
  };
}

/** Remove model preambles, notes, reasoning blocks, and raw JSON artifacts. */
export function cleanSummary(raw: string | null | undefined): string {
  if (!raw) return '';

  const structured = tryParseStructuredSummary(raw);
  if (structured) {
    return cleanProseField(structured.summary ?? structured.tldr ?? '');
  }

  const cleaned = cleanProseField(raw);
  if (!cleaned) return '';

  /* Never fall back to displaying an unparseable structured response. */
  if (/^\s*(?:```(?:json|text)?\s*)?\{/.test(cleaned)) return '';
  return cleaned;
}
