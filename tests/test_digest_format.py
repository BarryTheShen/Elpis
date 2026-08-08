from condenseit.digest.format import build_digest_markdown, render_digest_html


def test_digest_includes_markdown_links() -> None:
    md = build_digest_markdown(
        {
            "Infosec News": [
                {
                    "title": "Example CVE",
                    "url": "https://example.com/article",
                    "summary": "A critical patch was released.",
                    "source": "Example Blog",
                },
            ],
        },
        changes=[{"url": "https://status.example.com", "status": "changed"}],
        videos=[
            {
                "title": "AI roundup",
                "url": "https://youtube.com/watch?v=abc",
                "summary": "Weekly models overview.",
            },
        ],
    )
    assert "[Example CVE](https://example.com/article)" in md
    assert "[AI roundup](https://youtube.com/watch?v=abc)" in md
    assert "[changed](https://status.example.com)" in md
    assert "https://example.com/article" in md



def test_render_digest_html_strips_unsafe_markup_and_links() -> None:
    html = render_digest_html(
        "- **[<script>alert(1)</script>](javascript:alert(1))**\n"
        "  <img src=x onerror=alert(2)>\n\n"
        "[Safe](https://example.com/article)",
    )

    assert "<script" not in html.lower()
    assert "onerror" not in html.lower()
    assert "javascript:" not in html.lower()
    assert '<a href="https://example.com/article">Safe</a>' in html
