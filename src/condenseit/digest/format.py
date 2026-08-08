"""Deterministic digest markdown with links to every source."""

from datetime import UTC, datetime
from html import escape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import markdown

_SAFE_HTML_TAGS = frozenset(
    {
        "a",
        "blockquote",
        "br",
        "code",
        "del",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "pre",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_VOID_HTML_TAGS = frozenset({"br", "hr"})
_DROP_CONTENT_TAGS = frozenset({"iframe", "object", "script", "style", "template"})


def _safe_http_href(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        _ = parsed.port
    except (TypeError, ValueError):
        return None
    return value


class _SafeHtmlParser(HTMLParser):
    """Render Markdown HTML with a small, inert tag and attribute allowlist."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._open_tags: list[str | None] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if self._skip_depth:
            if tag in _DROP_CONTENT_TAGS:
                self._skip_depth += 1
            return
        if tag in _DROP_CONTENT_TAGS:
            self._skip_depth = 1
            return
        if tag not in _SAFE_HTML_TAGS:
            return
        if tag in _VOID_HTML_TAGS:
            self.parts.append(f"<{tag}>")
            return
        if tag == "a":
            href = next(
                (
                    value
                    for name, value in attrs
                    if name.casefold() == "href" and value
                ),
                None,
            )
            safe_href = _safe_http_href(href or "")
            if safe_href:
                self.parts.append(f'<a href="{escape(safe_href, quote=True)}">')
                self._open_tags.append(tag)
            else:
                self._open_tags.append(None)
            return
        self.parts.append(f"<{tag}>")
        self._open_tags.append(tag)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in _VOID_HTML_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._skip_depth:
            if tag in _DROP_CONTENT_TAGS:
                self._skip_depth = max(0, self._skip_depth - 1)
            return
        for index in range(len(self._open_tags) - 1, -1, -1):
            emitted = self._open_tags[index]
            if emitted == tag:
                self._open_tags.pop(index)
                self.parts.append(f"</{tag}>")
                return
            if tag == "a" and emitted is None:
                self._open_tags.pop(index)
                return

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        return


def render_digest_html(markdown_text: str) -> str:
    """Convert digest Markdown to inert HTML for the legacy server reader."""
    rendered = markdown.markdown(
        markdown_text or "",
        extensions=["tables", "fenced_code"],
    )
    parser = _SafeHtmlParser()
    parser.feed(rendered)
    parser.close()
    return "".join(parser.parts)

def order_digest_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return items in descending preference-score order.

    Items without a score retain their input order.  This keeps older digests
    deterministic while making scored digests visibly match the ranking
    engine's output.
    """
    return sorted(items, key=_preference_score, reverse=True)


def order_digest_categories(categorized: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Order category sections by the best score they contain."""
    return sorted(
        categorized,
        key=lambda category: (
            -max(
                (_preference_score(item) for item in categorized[category]),
                default=float("-inf"),
            ),
            category,
        ),
    )


def _preference_score(item: dict[str, Any]) -> float:
    raw = item.get("preference_score")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float("-inf")


def build_digest_markdown(
    categorized: dict[str, list[dict[str, Any]]],
    changes: list[dict[str, str]] | None = None,
    videos: list[dict[str, Any]] | None = None,
) -> str:
    """Build digest markdown; every article/video includes a clickable link."""
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# Elpis Digest",
        "",
        f"_{stamp}_",
        "",
    ]

    for category in order_digest_categories(categorized):
        items = order_digest_items(categorized[category])
        if not items:
            continue
        lines.append(f"## {category}")
        lines.append("")
        for item in items:
            lines.extend(_format_item(item))
        lines.append("")

    if videos:
        lines.append("## Videos")
        lines.append("")
        for item in videos:
            lines.extend(_format_item(item))
        lines.append("")

    if changes:
        lines.append("## Website changes")
        lines.append("")
        for change in changes:
            url = change.get("url", "")
            status = change.get("status", "updated")
            lines.append(f"- **[{status}]({url})** — {url}")
        lines.append("")

    if len(lines) <= 4:
        lines.append("_No new items in this run._")

    return "\n".join(lines).strip() + "\n"


def _format_item(item: dict[str, Any]) -> list[str]:
    title = (item.get("title") or "Untitled").strip()
    url = (item.get("url") or "").strip()
    summary = (item.get("summary") or "").strip()
    source = (item.get("source") or "").strip()

    if url:
        bullet = f"- **[{title}]({url})**"
    else:
        bullet = f"- **{title}**"

    out = [bullet]
    if summary:
        out.append(f"  {summary}")
    if source:
        out.append(f"  _via {source}_")
    return out
