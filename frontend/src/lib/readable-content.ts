/**
 * Parse feed/article text into safe, readable blocks.
 *
 * Feed content is frequently a mixture of plain text, HTML fragments, and
 * Markdown.  This parser deliberately produces data rather than markup so
 * callers can render it with ordinary JSX text nodes.  Only http(s) links are
 * retained as links; everything else is rendered as text.
 */
import { safeExternalUrl } from './urls';

export type ReadableInline =
  | { type: 'text'; text: string }
  | { type: 'link'; text: string; href: string };

export interface ReadableTextBlock {
  type: 'paragraph' | 'heading' | 'blockquote';
  text: string;
  inlines: ReadableInline[];
  level?: number;
}

export interface ReadableListItem {
  text: string;
  inlines: ReadableInline[];
}

export type ReadableBlock =
  | ReadableTextBlock
  | {
      type: 'list';
      ordered: boolean;
      items: ReadableListItem[];
    }
  | {
      type: 'code';
      text: string;
      language?: string;
    };

interface HtmlCodeBlock {
  text: string;
  language?: string;
}

interface ActiveList {
  ordered: boolean;
  html: boolean;
  items: string[];
  current: string[];
}

const MARKER = '\u0000ELPIS_';
const PARAGRAPH_START = `${MARKER}PARAGRAPH_START${MARKER}`;
const PARAGRAPH_END = `${MARKER}PARAGRAPH_END${MARKER}`;
const LIST_UNORDERED_START = `${MARKER}LIST_UNORDERED_START${MARKER}`;
const LIST_ORDERED_START = `${MARKER}LIST_ORDERED_START${MARKER}`;
const LIST_END = `${MARKER}LIST_END${MARKER}`;
const LIST_ITEM = `${MARKER}LIST_ITEM${MARKER}`;
const QUOTE_START = `${MARKER}QUOTE_START${MARKER}`;
const QUOTE_END = `${MARKER}QUOTE_END${MARKER}`;
const HEADING_START_PREFIX = `${MARKER}HEADING_START:`;
const CODE_PREFIX = `${MARKER}CODE:`;

const HTML_TAG_RE = /<\/?[a-z][^>]*>/gi;
const MARKDOWN_LINK_RE = /^\[([^\]\n]+)\]\(\s*([^\s)]+)(?:\s+["'][^)]*["'])?\s*\)/;
const BARE_URL_RE = /^https?:\/\/[^\s<>"'`]+/i;

function decodeHtmlEntities(value: string): string {
  return value.replace(/&(?:#x([\da-f]+)|#(\d+)|([a-z][\da-z]+));/gi, (full, hex, decimal, name) => {
    if (hex) {
      const codePoint = Number.parseInt(hex, 16);
      if (
        Number.isInteger(codePoint) &&
        codePoint >= 0 &&
        codePoint <= 0x10ffff &&
        (codePoint < 0xd800 || codePoint > 0xdfff)
      ) {
        return String.fromCodePoint(codePoint);
      }
      return full;
    }
    if (decimal) {
      const codePoint = Number.parseInt(decimal, 10);
      if (
        Number.isInteger(codePoint) &&
        codePoint >= 0 &&
        codePoint <= 0x10ffff &&
        (codePoint < 0xd800 || codePoint > 0xdfff)
      ) {
        return String.fromCodePoint(codePoint);
      }
      return full;
    }

    const entities: Record<string, string> = {
      amp: '&',
      apos: "'",
      gt: '>',
      lt: '<',
      nbsp: ' ',
      quot: '"',
      hellip: '\u2026',
      ndash: '\u2013',
      mdash: '\u2014',
      lsquo: '\u2018',
      rsquo: '\u2019',
      ldquo: '\u201c',
      rdquo: '\u201d',
    };
    return entities[name.toLowerCase()] ?? full;
  });
}


function getHtmlAttribute(attrs: string, name: string): string | undefined {
  const match = attrs.match(
    new RegExp(`\\b${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s>]+))`, 'i'),
  );
  return match?.[1] ?? match?.[2] ?? match?.[3];
}

function getCodeLanguage(attrs: string, inner: string): string | undefined {
  const codeAttrs = inner.match(/<code\b([^>]*)>/i)?.[1] ?? '';
  const className = `${getHtmlAttribute(attrs, 'class') ?? ''} ${getHtmlAttribute(codeAttrs, 'class') ?? ''}`;
  const language = className.match(/(?:language|lang)-([\w+-]+)/i)?.[1];
  return language || undefined;
}

function normalizeHtml(value: string): { text: string; code: HtmlCodeBlock[] } {
  let source = value
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, '')
    /* An unclosed executable/style fragment is source noise, not prose. */
    .replace(/<(script|style)\b[^>]*>[\s\S]*$/gi, '');

  const code: HtmlCodeBlock[] = [];

  /* Extract preformatted fragments before stripping anchors/tags. */
  source = source.replace(/<pre\b([^>]*)>([\s\S]*?)<\/pre\s*>/gi, (_full, attrs: string, inner: string) => {
    const text = decodeHtmlEntities(
      inner
        .replace(/<br\s*\/?\s*>/gi, '\n')
        .replace(/<\/?code\b[^>]*>/gi, ''),
    );
    const index = code.push({ text, language: getCodeLanguage(attrs, inner) }) - 1;
    return `\n${CODE_PREFIX}${index}${MARKER}\n`;
  });

  /* Convert safe anchors to Markdown links before removing HTML tags. */
  source = source.replace(/<a\b([^>]*)>([\s\S]*?)<\/a\s*>/gi, (_full, attrs: string, inner: string) => {
    const href = decodeHtmlEntities(getHtmlAttribute(attrs, 'href') ?? '');
    const label = decodeHtmlEntities(
      inner.replace(/<br\s*\/?\s*>/gi, ' ').replace(HTML_TAG_RE, ''),
    ).replace(/\s+/g, ' ').trim();
    const safeHref = safeExternalUrl(href);
    if (!label) return '';
    return safeHref ? `[${label.replace(/[\[\]]/g, '')}](${safeHref})` : label;
  });

  source = source
    .replace(/<br\s*\/?\s*>/gi, '\n')
    .replace(/<h([1-6])\b[^>]*>/gi, (_full, level: string) => `\n\n${HEADING_START_PREFIX}${level}${MARKER}\n`)
    .replace(/<\/h[1-6]\s*>/gi, `\n${MARKER}HEADING_END${MARKER}\n`)
    .replace(/<(?:p|div|section|article|header|footer|main|aside)\b[^>]*>/gi, `\n${PARAGRAPH_START}\n`)
    .replace(/<\/(?:p|div|section|article|header|footer|main|aside)\s*>/gi, `\n${PARAGRAPH_END}\n`)
    .replace(/<hr\b[^>]*\/?\s*>/gi, `\n${PARAGRAPH_END}\n`)
    .replace(/<ol\b[^>]*>/gi, `\n${LIST_ORDERED_START}\n`)
    .replace(/<ul\b[^>]*>/gi, `\n${LIST_UNORDERED_START}\n`)
    .replace(/<\/(?:ol|ul)\s*>/gi, `\n${LIST_END}\n`)
    .replace(/<li\b[^>]*>/gi, `\n${LIST_ITEM}\n`)
    .replace(/<\/li\s*>/gi, '\n')
    .replace(/<blockquote\b[^>]*>/gi, `\n${QUOTE_START}\n`)
    .replace(/<\/blockquote\s*>/gi, `\n${QUOTE_END}\n`)
    .replace(/<\/tr\s*>/gi, '\n')
    .replace(/<\/(?:td|th)\s*>/gi, ' ')
    /* Preserve Markdown autolinks before removing ordinary HTML tags. */
    .replace(/<((?:https?:\/\/)[^>\s]+)>/gi, '$1')
    .replace(HTML_TAG_RE, '');

  return { text: decodeHtmlEntities(source), code };
}

function pushInlineText(target: ReadableInline[], text: string): void {
  if (!text) return;
  const previous = target[target.length - 1];
  if (previous?.type === 'text') {
    previous.text += text;
  } else {
    target.push({ type: 'text', text });
  }
}

function appendSafeBareUrl(target: ReadableInline[], rawUrl: string): void {
  let url = rawUrl;
  let trailing = '';
  while (/[.,!?;:)}\]]$/.test(url)) {
    trailing = url[url.length - 1] + trailing;
    url = url.slice(0, -1);
  }
  const safeUrl = safeExternalUrl(url);
  if (!safeUrl) {
    pushInlineText(target, rawUrl);
    return;
  }
  target.push({ type: 'link', text: url, href: safeUrl });
  pushInlineText(target, trailing);
}

function parseInline(value: string): ReadableInline[] {
  /*
   * normalizeHtml decodes entities once after removing source HTML. Do not
   * decode or strip tags again here: escaped literal markup such as
   * `&lt;strong&gt;tag&lt;/strong&gt;` must remain visible as text.
   */
  let text = value
    .replace(/<((?:https?:\/\/)[^>\s]+)>/gi, '$1')
    .replace(/<br\s*\/?\s*>/gi, '\n')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/`([^`\n]+)`/g, '$1');

  text = text
    .replace(/(\*\*|__)([^*_\n]+)\1/g, '$2')
    .replace(/(~~)([^~\n]+)\1/g, '$2')
    .replace(/(^|\s)[*_]([^*_\n]+)[*_](?=\s|$)/g, '$1$2')
    .replace(/[ \t]+/g, ' ')
    .trim();

  const tokens: ReadableInline[] = [];
  let remaining = text;
  while (remaining) {
    const markdownLink = remaining.match(MARKDOWN_LINK_RE);
    if (markdownLink) {
      const [whole, label, href] = markdownLink;
      const safeHref = safeExternalUrl(href);
      if (safeHref) {
        tokens.push({ type: 'link', text: label, href: safeHref });
      } else {
        pushInlineText(tokens, label);
      }
      remaining = remaining.slice(whole.length);
      continue;
    }

    const bareUrl = remaining.match(BARE_URL_RE);
    if (bareUrl) {
      appendSafeBareUrl(tokens, bareUrl[0]);
      remaining = remaining.slice(bareUrl[0].length);
      continue;
    }

    const nextMarkdown = remaining.search(/\[|https?:\/\//i);
    if (nextMarkdown <= 0) {
      pushInlineText(tokens, remaining);
      break;
    }
    pushInlineText(tokens, remaining.slice(0, nextMarkdown));
    remaining = remaining.slice(nextMarkdown);
  }
  return tokens;
}
function endsSentence(value: string): boolean {
  return /[.!?\u2026][\s"'”’)}\]]*$/.test(value.trim());
}

function startsNewThought(value: string): boolean {
  return /^[A-ZÀ-ÖØ-Þ0-9]/.test(value) && !/[,;:]$/.test(value.trim());
}

function isMarkerLine(value: string): boolean {
  return value.includes(MARKER);
}

function headingLevel(value: string): number | null {
  if (!value.startsWith(HEADING_START_PREFIX) || !value.endsWith(MARKER)) return null;
  const level = Number(value.slice(HEADING_START_PREFIX.length, -MARKER.length));
  return level >= 1 && level <= 6 ? level : null;
}

function codeIndex(value: string): number | null {
  if (!value.startsWith(CODE_PREFIX) || !value.endsWith(MARKER)) return null;
  const index = Number(value.slice(CODE_PREFIX.length, -MARKER.length));
  return Number.isInteger(index) && index >= 0 ? index : null;
}

function makeTextBlock(
  type: ReadableTextBlock['type'],
  text: string,
  level?: number,
): ReadableTextBlock {
  const normalized = text.trim();
  return {
    type,
    text: normalized,
    inlines: parseInline(normalized),
    ...(level === undefined ? {} : { level }),
  };
}

function makeListBlock(active: ActiveList): ReadableBlock | null {
  const current = active.current.join(' ').trim();
  if (current) active.items.push(current);
  active.current = [];
  if (active.items.length === 0) return null;
  return {
    type: 'list',
    ordered: active.ordered,
    items: active.items.map((text) => ({ text, inlines: parseInline(text) })),
  };
}
function joinNonEmpty(lines: string[], separator: string): string {
  const parts: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed) parts.push(trimmed);
  }
  return parts.join(separator).trim();
}

/** Parse mixed plain text, HTML fragments, and Markdown into safe blocks. */
export function parseReadableContent(value: string | null | undefined): ReadableBlock[] {
  if (!value?.trim()) return [];
  const normalized = normalizeHtml(value);
  const lines = normalized.text.replace(/\r\n?/g, '\n').split('\n');
  const blocks: ReadableBlock[] = [];
  let prose: string[] = [];
  let list: ActiveList | null = null;
  let quote: string[] | null = null;
  let quoteHtml = false;
  let heading: { level: number; lines: string[] } | null = null;

  const flushProse = () => {
    if (prose.length === 0) return;
    const text = joinNonEmpty(prose, ' ');
    if (text) blocks.push(makeTextBlock('paragraph', text));
    prose = [];
  };

  const flushList = () => {
    if (!list) return;
    const block = makeListBlock(list);
    if (block) blocks.push(block);
    list = null;
  };

  const flushQuote = () => {
    if (!quote || quote.length === 0) {
      quote = null;
      quoteHtml = false;
      return;
    }
    const text = joinNonEmpty(quote, '\n');
    if (text) blocks.push(makeTextBlock('blockquote', text));
    quote = null;
    quoteHtml = false;
  };

  const flushHeading = () => {
    if (!heading || heading.lines.length === 0) {
      heading = null;
      return;
    }
    const text = joinNonEmpty(heading.lines, ' ');
    if (text) blocks.push(makeTextBlock('heading', text, heading.level));
    heading = null;
  };

  const flushAll = () => {
    flushHeading();
    flushQuote();
    flushList();
    flushProse();
  };

  const startList = (ordered: boolean, html: boolean) => {
    flushHeading();
    flushQuote();
    flushProse();
    flushList();
    list = { ordered, html, items: [], current: [] };
  };

  for (let index = 0; index < lines.length; index++) {
    const rawLine = lines[index];
    const trimmed = rawLine.trim();

    const fence = rawLine.match(/^\s{0,3}(`{3,}|~{3,})(.*)$/);
    if (!heading && !quote && !list && fence) {
      flushProse();
      const marker = fence[1];
      const info = fence[2].trim().split(/\s+/)[0] || undefined;
      const codeLines: string[] = [];
      const close = new RegExp(`^\\s{0,3}${marker[0]}{${marker.length},}\\s*$`);
      index++;
      while (index < lines.length && !close.test(lines[index])) {
        codeLines.push(lines[index]);
        index++;
      }
      blocks.push({
        type: 'code',
        text: codeLines.join('\n').replace(/^\n|\n$/g, ''),
        ...(info ? { language: info } : {}),
      });
      continue;
    }

    const parsedCodeIndex = codeIndex(trimmed);
    if (parsedCodeIndex !== null) {
      flushAll();
      const code = normalized.code[parsedCodeIndex];
      if (code) blocks.push({ type: 'code', ...code });
      continue;
    }

    const headingStart = headingLevel(trimmed);
    if (headingStart !== null) {
      flushAll();
      heading = { level: headingStart, lines: [] };
      continue;
    }
    if (trimmed === `${MARKER}HEADING_END${MARKER}`) {
      flushHeading();
      continue;
    }
    if (heading) {
      if (!trimmed || isMarkerLine(trimmed)) flushHeading();
      else {
        heading.lines.push(trimmed);
        continue;
      }
    }

    if (trimmed === QUOTE_START) {
      flushHeading();
      flushList();
      flushProse();
      quote = [];
      quoteHtml = true;
      continue;
    }
    if (trimmed === QUOTE_END) {
      flushQuote();
      continue;
    }
    const markdownQuote = trimmed.match(/^>\s?(.*)$/);
    if (markdownQuote) {
      if (!quote) {
        flushHeading();
        flushList();
        flushProse();
        quote = [];
        quoteHtml = false;
      }
      quote.push(markdownQuote[1]);
      continue;
    }
    if (quote) {
      if (quoteHtml) {
        /*
         * HTML block markers describe nested structure, not visible prose.
         * Ignore them while retaining the text inside the quote.
         */
        if (isMarkerLine(trimmed)) continue;
        if (trimmed) quote.push(trimmed);
        continue;
      }
      if (!trimmed) {
        flushQuote();
        continue;
      }
      flushQuote();
    }

    if (trimmed === LIST_UNORDERED_START) {
      startList(false, true);
      continue;
    }
    if (trimmed === LIST_ORDERED_START) {
      startList(true, true);
      continue;
    }
    if (trimmed === LIST_END) {
      flushList();
      continue;
    }
    if (trimmed === LIST_ITEM) {
      if (!list) startList(false, true);
      const activeList = list as ActiveList | null;
      if (activeList && activeList.current.length > 0) {
        const current = activeList.current.join(' ').trim();
        if (current) activeList.items.push(current);
        activeList.current = [];
      }
      continue;
    }

    const markdownList = trimmed.match(/^(?:[-+*]|(\d+)[.)])\s+(.+)$/);
    if (markdownList) {
      const ordered = markdownList[1] !== undefined;
      const existingList = list as ActiveList | null;
      if (!existingList || existingList.ordered !== ordered) startList(ordered, false);
      const activeList = list as ActiveList | null;
      if (!activeList) continue;
      if (activeList.current.length > 0) {
        const current = activeList.current.join(' ').trim();
        if (current) activeList.items.push(current);
        activeList.current = [];
      }
      activeList.current.push(markdownList[2].trim());
      continue;
    }
    const activeList = list as ActiveList | null;
    if (activeList && (trimmed === PARAGRAPH_START || trimmed === PARAGRAPH_END)) {
      continue;
    }
    if (activeList) {
      if (!trimmed) {
        if (activeList.html) {
          if (activeList.current.length > 0) {
            const current = activeList.current.join(' ').trim();
            if (current) activeList.items.push(current);
            activeList.current = [];
          }
        } else {
          flushList();
        }
        continue;
      }
      if (activeList.html || /^\s{2,}/.test(rawLine)) {
        activeList.current.push(trimmed);
        continue;
      }
      flushList();
    }

    if (trimmed === PARAGRAPH_START || trimmed === PARAGRAPH_END || !trimmed) {
      flushProse();
      continue;
    }

    const markdownHeading = trimmed.match(/^(#{1,6})\s+(.+?)\s*#*$/);
    if (markdownHeading) {
      flushAll();
      blocks.push(makeTextBlock('heading', markdownHeading[2], markdownHeading[1].length));
      continue;
    }

    if (prose.length > 0) {
      const previous = prose[prose.length - 1].trim();
      if (endsSentence(previous) || startsNewThought(trimmed)) flushProse();
    }
    prose.push(trimmed);
  }

  flushAll();
  return blocks;
}
