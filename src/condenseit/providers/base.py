"""LLM provider abstraction."""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


# Map of ISO 639-1 codes (and common langdetect outputs) to human-readable
# language names suitable for embedding in LLM prompts.
_LANG_NAMES: dict[str, str] = {
    "af": "Afrikaans",
    "ar": "Arabic",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "gu": "Gujarati",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ka": "Georgian",
    "kn": "Kannada",
    "ko": "Korean",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mr": "Marathi",
    "nl": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sq": "Albanian",
    "sr": "Serbian",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tl": "Filipino",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "zh-tw": "Chinese",
}


def _lang_code_to_name(code: str) -> str:
    """Map an ISO 639-1 language code to a human-readable name for LLM prompts."""
    code = code.lower().strip()
    if code in _LANG_NAMES:
        return _LANG_NAMES[code]
    # Unknown code: capitalise and return as-is (e.g. "Eo" for Esperanto).
    return code.capitalize()


def resolve_digest_language(digest_language: str, content: str = "") -> str:
    """Resolve a digest_language config value to a human-readable language name.

    - ``"en"`` (default) → ``"English"``
    - ``"source"`` → auto-detect from ``content`` via langdetect; falls back to
      ``"English"`` if detection fails or content is empty
    - Any other ISO 639-1 code (e.g. ``"fr"``) → mapped name (``"French"``)
    """
    code = digest_language.strip().lower()
    if not code or code == "en":
        return "English"
    if code == "source":
        if not content:
            return "English"
        try:
            from langdetect import detect

            detected = detect(content[:1000])
            return _lang_code_to_name(detected)
        except Exception:
            return "English"
    return _lang_code_to_name(code)


class ArticleSummary(TypedDict):
    """Structured output from a single article summarization call."""

    tldr: str
    key_takeaways: list[str]
    summary: str
    topics: list[str]
    entities: list[str]
    novelty: int
    relevance_to_you: str


_EMPTY_SUMMARY = ArticleSummary(
    tldr="",
    key_takeaways=[],
    summary="",
    topics=[],
    entities=[],
    novelty=0,
    relevance_to_you="",
)

# Matches an optional ```json ... ``` or ``` ... ``` fence around JSON.
_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)

# Greedily matches the outermost {...} object in a raw response.
_BRACE_RE = re.compile(r"\{.*\}", re.DOTALL)

# Strips an opening code fence (e.g. ```json\n or ```\n) so we can work on
# the raw JSON content even when the closing fence was never emitted.
_FENCE_OPEN_RE = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_PLAIN_REASONING_PREFIX_RE = re.compile(
    r"^\s*(?:thinking\s+process|chain\s+of\s+thought|scratchpad)\s*:\s*",
    re.IGNORECASE,
)


# Detects the start of a Chinese LLM refusal phrase that some multilingual
# models append mid-response (e.g. "作为一个人工智能语言模型...").
# We strip from the first run of consecutive CJK characters onward when that
# run comprises the majority of the remaining text, so we don't accidentally
# truncate article titles that legitimately contain a single CJK character.
_CJK_BLOCK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]{4,}")
# Reasoning-model delimiters that providers commonly emit around private
# chain-of-thought.  Keep this allowlist deliberately narrow: arbitrary XML or
# angle-bracket text in an article must remain visible.
_REASONING_TAG_NAMES = (
    "chain-of-thought",
    "chain_of_thought",
    "deliberation",
    "reasoning_content",
    "redacted_thinking",
    "reasoning",
    "reflection",
    "scratchpad",
    "thinking",
    "analysis",
    "thought",
    "think",
    "cot",
    "internal",
    "private",
)
_REASONING_TAG_RE = re.compile(
    r"<\s*(?P<closing>/)?\s*(?P<tag>"
    + "|".join(re.escape(tag) for tag in _REASONING_TAG_NAMES)
    + r")(?=\s|/?>)[^<>]*?(?P<self_closing>/?)>",
    re.IGNORECASE,
)


def sanitize_reasoning_content(value: str) -> str:
    """Remove provider reasoning blocks while preserving ordinary text.

    Reasoning models do not agree on one delimiter: common responses use
    ``<think>``, ``<analysis>``, ``<reasoning>``, or similar tags, and some
    stop emitting before a closing tag.  This scanner removes only tags from
    the explicit allowlist above.  A matching block may be nested; an
    unclosed opening tag discards the remainder because it cannot be safely
    classified as visible prose.
    """
    if not isinstance(value, str) or not value:
        return ""

    visible: list[str] = []
    open_tags: list[str] = []
    cursor = 0
    for match in _REASONING_TAG_RE.finditer(value):
        tag = match.group("tag").casefold()
        closing = bool(match.group("closing"))
        self_closing = bool(match.group("self_closing"))

        if not open_tags:
            visible.append(value[cursor : match.start()])
            cursor = match.end()
            if not closing and not self_closing:
                open_tags.append(tag)
            continue

        if closing:
            # A malformed nested block should not make any private text
            # visible.  Close the nearest matching opener, if one exists.
            for index in range(len(open_tags) - 1, -1, -1):
                if open_tags[index] == tag:
                    del open_tags[index:]
                    break
            if not open_tags:
                cursor = match.end()
        elif not self_closing:
            open_tags.append(tag)

    if not open_tags:
        visible.append(value[cursor:])
    return "".join(visible).strip()


def _looks_like_plain_reasoning(value: str) -> bool:
    return bool(_PLAIN_REASONING_PREFIX_RE.match(value))


def _clean_summary_text(value: Any) -> str:
    """Normalize one user-visible prose value from a model response."""
    cleaned = sanitize_reasoning_content(str(value or "")).strip()
    if not cleaned or not cleaned.strip(" .…\t\r\n"):
        return ""
    if _looks_like_plain_reasoning(cleaned):
        return ""
    return _strip_non_latin_tail(cleaned)


# Regex patterns for partial-field extraction from truncated JSON.
# These only match *complete* string values (closed quote, then comma/newline).
_PARTIAL_STR_FIELD_RE = {
    field: re.compile(
        r'"' + re.escape(field) + r'"\s*:\s*"((?:[^"\\]|\\.)*)"',
        re.DOTALL,
    )
    for field in ("tldr", "summary", "relevance_to_you")
}
# key_takeaways: match a fully-closed JSON array value.
_PARTIAL_ARRAY_FIELD_RE = {
    field: re.compile(
        r'"' + re.escape(field) + r'"\s*:\s*(\[[^\[\]]*\])',
        re.DOTALL,
    )
    for field in ("key_takeaways", "topics", "entities")
}
_PARTIAL_INT_FIELD_RE = re.compile(r'"novelty"\s*:\s*(\d+)')
# Some reasoning-capable models prepend a plain-text thinking transcript before
# starting the JSON object. Search for the last real payload object so a
# truncated response can still yield completed fields.
_PARTIAL_OBJECT_START_RE = re.compile(
    r'\{\s*"tldr"\s*:',
    re.IGNORECASE | re.DOTALL,
)


def _strip_non_latin_tail(value: str) -> str:
    """Remove a trailing CJK/non-Latin injection appended by the LLM.

    Some cheap multilingual models start answering in English, then switch
    to a Chinese refusal phrase mid-field.  This function finds the earliest
    CJK run that makes up more than 30 % of the remaining text and truncates
    there, returning a clean Latin-script prefix.
    """
    for m in _CJK_BLOCK_RE.finditer(value):
        tail = value[m.start() :]
        non_ascii_in_tail = sum(1 for c in tail if ord(c) > 127)
        if len(tail) > 0 and non_ascii_in_tail / len(tail) > 0.3:
            return value[: m.start()].rstrip()
    return value


def _extract_partial_fields(text: str) -> ArticleSummary | None:
    """Try to extract individual fields from a truncated JSON string.

    When the LLM response is cut off mid-value (max_tokens hit), the JSON
    object is invalid as a whole, but earlier fields that were fully written
    can still be rescued with targeted regex extraction.

    Returns an :class:`ArticleSummary` if at least ``tldr`` was found,
    otherwise returns ``None`` so the caller can keep trying other strategies.
    """
    # Strip opening code fence if present. Reasoning models may prepend a
    # plain-text transcript, so recover the last object-shaped payload too.
    body = _FENCE_OPEN_RE.sub("", text).strip()
    if not body.startswith("{"):
        matches = list(_PARTIAL_OBJECT_START_RE.finditer(body))
        if not matches:
            return None
        body = body[matches[-1].start() :]

    result: dict[str, Any] = {}

    for field, pat in _PARTIAL_STR_FIELD_RE.items():
        m = pat.search(body)
        if m:
            try:
                # json.loads the quoted value to handle escape sequences.
                result[field] = json.loads('"' + m.group(1) + '"')
            except (json.JSONDecodeError, ValueError):
                result[field] = m.group(1)

    for field, pat in _PARTIAL_ARRAY_FIELD_RE.items():
        m = pat.search(body)
        if m:
            try:
                result[field] = json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                logger.debug("Could not parse partial array field %s", field)

    m_nov = _PARTIAL_INT_FIELD_RE.search(body)
    if m_nov:
        try:
            result["novelty"] = max(1, min(5, int(m_nov.group(1))))
        except (TypeError, ValueError):
            logger.debug("Could not parse novelty score from partial JSON")

    takeaways = result.get("key_takeaways", [])
    if isinstance(takeaways, str):
        takeaways = [t.strip() for t in takeaways.splitlines() if t.strip()]
    elif not isinstance(takeaways, list):
        takeaways = []

    # Sanitize extracted values as well as the source text.  This protects
    # against tags that occur inside a quoted JSON field.
    tldr = _clean_summary_text(result.get("tldr"))
    if not tldr:
        return None

    clean_takeaways: list[str] = []
    for takeaway in takeaways:
        cleaned = _clean_summary_text(takeaway)
        if cleaned:
            clean_takeaways.append(cleaned)
    takeaways = clean_takeaways

    raw_topics = result.get("topics", [])
    topics: list[str] = []
    if isinstance(raw_topics, list):
        for topic in raw_topics:
            cleaned = sanitize_reasoning_content(str(topic)).lower().strip()
            if cleaned:
                topics.append(cleaned)

    raw_entities = result.get("entities", [])
    entities: list[str] = []
    if isinstance(raw_entities, list):
        for entity in raw_entities:
            cleaned = sanitize_reasoning_content(str(entity)).strip()
            if cleaned:
                entities.append(cleaned)
    summary = _clean_summary_text(result.get("summary"))
    relevance = _clean_summary_text(result.get("relevance_to_you"))

    return ArticleSummary(
        tldr=tldr,
        key_takeaways=takeaways,
        summary=summary,
        topics=topics,
        entities=entities[:10],
        novelty=result.get("novelty") or 0,
        relevance_to_you=relevance,
    )


def _looks_like_json(text: str) -> bool:
    """Return True if text looks like raw JSON (starts with { or a code fence)."""
    stripped = _FENCE_OPEN_RE.sub("", text.strip()).strip()
    return stripped.startswith("{")


def parse_summary_response(raw: str) -> ArticleSummary:
    """Parse a JSON article-summary response produced by an LLM.

    Attempts several strategies in order:
      1. Strip whitespace and parse as bare JSON.
      2. Extract JSON from a markdown code fence (complete fence).
      3. Grab the first ``{...}`` substring and parse it.
      4. Partial-field extraction from a truncated JSON response.
      5. Fall back: treat the whole response as the ``summary`` field,
         but only if it doesn't look like raw JSON (refuse to store garbage).

    Always returns a fully-populated :class:`ArticleSummary` dict.
    """
    text = sanitize_reasoning_content(raw if isinstance(raw, str) else "")
    if not text:
        return _EMPTY_SUMMARY

    candidates: list[str] = [
        text,
        text.rstrip(",") + "}",
        text + "}",
    ]
    # Code-fence extraction (only fires when the closing fence was emitted)
    m = _FENCE_RE.search(text)
    if m:
        chunk = m.group(1).strip()
        candidates = [chunk, chunk.rstrip(",") + "}", chunk + "}"] + candidates
    # Raw brace extraction (broader, try last)
    m2 = _BRACE_RE.search(text)
    if m2:
        chunk2 = m2.group(0)
        candidates += [chunk2, chunk2.rstrip(",") + "}", chunk2 + "}"]

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if not isinstance(data, dict):
                continue
            takeaways = data.get("key_takeaways", [])
            if isinstance(takeaways, str):
                # Some models return a newline-separated string instead of an array.
                takeaways = [t.strip() for t in takeaways.splitlines() if t.strip()]
            elif not isinstance(takeaways, list):
                takeaways = []
            clean_takeaways: list[str] = []
            for takeaway in takeaways:
                cleaned = _clean_summary_text(takeaway)
                if cleaned:
                    clean_takeaways.append(cleaned)

            # Parse enrichment fields (new; default to empty when absent).
            topics: list[str] = []
            raw_topics = data.get("topics", [])
            if isinstance(raw_topics, list):
                for topic in raw_topics:
                    cleaned = sanitize_reasoning_content(str(topic)).lower().strip()
                    if cleaned:
                        topics.append(cleaned)

            entities: list[str] = []
            raw_entities = data.get("entities", [])
            if isinstance(raw_entities, list):
                for entity in raw_entities:
                    cleaned = sanitize_reasoning_content(str(entity)).strip()
                    if cleaned:
                        entities.append(cleaned)
            tldr = _clean_summary_text(data.get("tldr"))
            summary = _clean_summary_text(data.get("summary"))
            relevance = _clean_summary_text(data.get("relevance_to_you"))

            try:
                novelty = max(1, min(5, int(data.get("novelty", 0) or 0)))
            except (TypeError, ValueError):
                novelty = 0

            if not (tldr or clean_takeaways or summary or topics or entities or relevance):
                return _EMPTY_SUMMARY

            return ArticleSummary(
                tldr=tldr,
                key_takeaways=clean_takeaways,
                summary=summary,
                topics=topics,
                entities=entities[:10],
                novelty=novelty,
                relevance_to_you=relevance,
            )
        except (json.JSONDecodeError, ValueError):
            continue

    # Partial-field recovery for truncated responses (max_tokens hit).
    partial = _extract_partial_fields(text)
    if partial is not None:
        logger.debug(
            "parse_summary_response: recovered partial fields from truncated JSON"
        )
        return partial

    if _looks_like_plain_reasoning(text):
        return _EMPTY_SUMMARY

    if text:
        non_ascii = sum(1 for c in text if ord(c) > 127)
        if non_ascii / len(text) > 0.2:
            return _EMPTY_SUMMARY

        if _looks_like_json(text):
            logger.warning(
                "parse_summary_response: response looks like raw/truncated JSON "
                "but could not be parsed; discarding to avoid storing garbage"
            )
            return _EMPTY_SUMMARY

    fallback = _clean_summary_text(text)
    if not fallback:
        return _EMPTY_SUMMARY
    return ArticleSummary(
        tldr="",
        key_takeaways=[],
        summary=fallback,
        topics=[],
        entities=[],
        novelty=0,
        relevance_to_you="",
    )


def build_chat_system_prompt(language: str = "English") -> str:
    """Return the system prompt for chat-completions providers.

    ``language`` is a human-readable language name such as ``"English"`` or
    ``"French"``.  All JSON field values in the response will be written in
    that language.
    """
    return (
        "You are a concise news analyst. Respond ONLY with a JSON object — "
        "no markdown, no code fences, no additional text. "
        f"Write all JSON field values in {language} "
        "regardless of the article's language."
    )


# Backward-compatible alias for the default English system prompt.
CHAT_SYSTEM_PROMPT = build_chat_system_prompt("English")


def build_chat_user_prompt(
    title: str,
    content: str,
    max_key_takeaways: int = 5,
    max_summary_paragraphs: int = 5,
    language: str = "English",
) -> str:
    """Build the per-article user prompt for chat-completions providers.

    ``language`` is a human-readable language name such as ``"English"`` or
    ``"French"``.
    """
    takeaway_placeholders = ", ".join(
        f'"<takeaway {i + 1}>"' for i in range(max_key_takeaways)
    )
    para_word = "paragraph" if max_summary_paragraphs == 1 else "paragraphs"

    return (
        "Analyze this article and respond with a JSON object "
        f"in exactly this structure. All values must be written in {language}:\n"
        f"{{\n"
        f'  "tldr": "<one sentence in {language}: what happened and why it matters>",\n'
        f'  "key_takeaways": [{takeaway_placeholders}],\n'
        f'  "summary": "<detailed summary in {language}, {max_summary_paragraphs} {para_word}>",\n'  # noqa: E501
        f'  "topics": ["<topic-1>", "<topic-2>", "<topic-3>"],\n'
        f'  "entities": ["<person-org-product-1>", "<entity-2>"],\n'
        f'  "novelty": <integer 1-5: how surprising or novel vs mainstream coverage>\n'
        f"}}\n\n"
        f"Title: {title}\n"
        f"Content: {content}"
    )


class SummarizerProvider(ABC):
    @abstractmethod
    def summarize_article(
        self,
        article: dict[str, Any],
    ) -> ArticleSummary:
        """Summarize ``article`` and return a structured result."""
        ...

    @abstractmethod
    def generate_digest(
        self,
        categorized: dict[str, list[dict[str, Any]]],
        changes: list[dict[str, str]] | None = None,
        videos: list[dict[str, Any]] | None = None,
    ) -> str: ...

    @property
    def model_name(self) -> str:
        return "unknown"
