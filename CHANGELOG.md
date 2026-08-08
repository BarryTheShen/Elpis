# Changelog

## Unreleased

- Ranking: broad candidate pools now pass through a deterministic title/lead
  relevance gate before balancing and publication. Configured intent terms and
  synonyms are recorded as compact evidence; body-only incidental matches
  (the observed Wired TV `security`/`go`/`drone` false positives) are rejected,
  while no-intent discovery stays open.
- Digest: `max_articles_per_digest` remains the summary/publication budget while
  the complete sanitized ranked candidate list is retained and exposed to
  authenticated readers as metadata/snippet cards. Numeric score evidence is
  shown without provider reasoning or raw model output.
- Discovery and monitoring: general Google News discovery is isolated from daily
  ranking, and persisted monitoring questions/results support scoped searches,
  Check now, URL deduplication, and new/seen/dismissed state.
- Evaluation: added offline profile fixtures for security, developer/infra,
  Qwen release research, FPV/drone, and general technology consumers, including
  near-duplicates and body-only negatives with precision@5/10, recall, nDCG/MRR,
  false-positive, abstention, and coverage metrics.

- Collection: RSS/Atom, Google News, GitHub Releases, and podcast sources now
  collect up to 50 entries by default (configurable to 200) before ranking;
  ordered concurrent article extraction preserves feed order and records
  collected, filtered, candidate, and selected counts.
- Reader: publication history moved to a paginated public archive, while admin
  routes remain configuration/operations only; article and summary views now
  render safe paragraphs, headings, lists, links, code, and blockquotes without
  exposing provider reasoning or raw structured JSON.
- Archive: published issues are bounded to the newest 100 by default
  (`digest_history_limit`, configurable from Admin > Digest settings); older
  issue rows are pruned without deleting article, rating, saved-item, or run
  history.
- Summaries: truncated reasoning-model responses now recover completed visible
  fields, while ellipsis placeholders and plain thinking transcripts stay out
  of publication cards and reader panels.
- Ranking: category balancing now preserves descending preference-score output
  order, persisted/public API items normalize legacy digest order, dry-run
  digests serialize the same order, and configured keywords use word
  boundaries so short terms such as `go` do not match `Google`.

- Branding: reintroduced the project as Elpis, with independent repository
  documentation, PWA identity, and retained CondenseIt MIT attribution.
- Publication: exposed read-only digest routes while withholding raw rendered
  HTML and personal ratings from anonymous responses.
- Security: moved desktop admin access behind server-side authorization and
  added SQLite-aware health checks for the mounted data store.
- Operations: persistent digest run history, terminal success/failure alerts in
  the admin header, an overview dashboard, and status labels in run logs.
- Deployment: unsafe Firebase/Cloud Run SQLite storage path disabled; the
  supported production target remains the stable local-disk VPS deployment
  until a transactional database backend is available.
- Security: password changes rotate a persisted auth-session generation,
  keeping the requester active while revoking other sessions.

- Networking: Advanced settings now persist an encrypted HTTP(S)/SOCKS5 proxy
  policy, route all Elpis-managed HTTPX/urllib/requests/yt-dlp calls with
  per-host bypasses, and expose credential-safe connection tests.
- Admin: OPML import/export, HTMX-enhanced sources table, per-source health after collects.
- Admin: Ollama pull/delete from LLM settings (host from config).
- Preferences: TF-IDF style cosine boost from ratings (`relevance.tfidf_preference_weight`).
- OpenRouter: optional cheapest-model picker (`llm.openrouter_pick_cheapest`).
- Digest pipeline: weekly model advisor snapshot stored in settings (at most every 7 days).
- Docs: `docs/` guides, `launchd/` example plist, `scripts/export-config.sh`.
- Repository: MIT `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`.
