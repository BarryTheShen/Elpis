# Changelog

## Unreleased

- Branding: reintroduced the project as Elpis, with independent repository
  documentation, PWA identity, and retained CondenseIt MIT attribution.
- Publication: exposed read-only digest routes while withholding raw rendered
  HTML and personal ratings from anonymous responses.
- Security: moved desktop admin access behind server-side authorization and
  added SQLite-aware health checks for the mounted data store.

- Admin: OPML import/export, HTMX-enhanced sources table, per-source health after collects.
- Admin: Ollama pull/delete from LLM settings (host from config).
- Preferences: TF-IDF style cosine boost from ratings (`relevance.tfidf_preference_weight`).
- OpenRouter: optional cheapest-model picker (`llm.openrouter_pick_cheapest`).
- Digest pipeline: weekly model advisor snapshot stored in settings (at most every 7 days).
- Docs: `docs/` guides, `launchd/` example plist, `scripts/export-config.sh`.
- Repository: MIT `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`.
