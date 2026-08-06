# AI Daily Debrief — Product Architecture & AI Handoff

<aside>
🎯

**Instructional header — source of truth for implementation**

This page is the canonical architecture and requirements document for the new AI daily-debrief product. Any AI coding agent must read this page completely before planning or editing code.

**Locked requirements:** one Docker-hosted product, one externally accessible port/origin, desktop and mobile support, authenticated desktop admin panel, no mobile admin interface, read-focused mobile publication, source-grounded AI chat, clean minimal visual design, no “AI slop” aesthetics, deployment-provider independence, regular coherent Git commits, and complete shipping-ready repository documentation.

Use the **Taste / artifact-design skill** before every visible UI change. Do not make Tailscale or any private network a runtime dependency. Do not change locked requirements, add user-facing ports, expose admin functions on mobile, or broaden chat beyond its configured sources without Barry’s explicit approval.

</aside>

## 1. Product definition

This product is a self-hostable daily publication for general users. Each deployment turns the user’s selected information sources and interests into a coherent debrief of what matters to that user that day. It must work as a real distributable project, not as a one-off setup tied to Barry’s personal infrastructure.

It is a **new independent product**, not merely a visual skin. The inherited ingestion, ranking, scheduling, storage, and LLM plumbing remain available while the new product replaces the identity and user experience, then adds dual editions, grounded chat, podcasts, and later an advisory discovery scout.

### Core promise

> One trusted daily issue, available on computer and phone, with a quick edition, a deeper edition, traceable sources, grounded follow-up chat, and eventually conversational audio.
>

### Source-code basis

- Start from a full independent copy of [CondenseIt](https://github.com/wildlifechorus/condenseit), preserving its Git history.
- Elpis is an independent product and GitHub repository, not a GitHub fork; keep CondenseIt only as the optional `upstream` remote.
- Retain CondenseIt’s original MIT `LICENSE` and copyright notice.
- Rebrand the repository, UI, navigation, README, icons, and product name as Elpis.
- Never commit `.env` files, API keys, production databases, generated private content, or other secrets.

---

## 2. Non-negotiable requirements

1. **Computer and mobile access**
    - The same hosted product and data must work from desktop/laptop browsers and phone browsers/Home Screen web apps.
    - Both clients use the same origin, API, issue archive, and authentication system.
2. **Desktop admin panel**
    - Desktop provides the full daily-publication experience plus an authenticated admin panel.
    - Admin capabilities include sources, categories, filters, schedules, prompts, models, ranking preferences, issue generation, logs, backups, and system health.
3. **No mobile admin interface**
    - Mobile is a read-focused publication, not a compressed admin dashboard.
    - Mobile includes Today, archive, quick/deep editions, source links, save/rating actions if retained, grounded chat, and podcast playback.
    - Mobile navigation must not show source management, model configuration, schedules, logs, backups, or other operational controls.
    - Hiding admin UI is not the security boundary: every admin API remains authenticated and authorized server-side.
4. **Taste-led redesign**
    - Visible UI work requires the Taste / artifact-design skill.
    - The interface must feel clean, quiet, intentional, and publication-like—not like a generic AI dashboard.
    - Avoid obvious AI-generated visual clichés and template-heavy “AI slop.”
5. **Docker-only hosting**
    - The complete application runs from Docker Compose.
    - Runtime data persists in mounted volumes.
    - Installation, update, backup, restore, and rollback must be possible without installing application dependencies directly on the host.
6. **One externally accessible port**
    - Exactly one application port/origin is exposed to the host and users.
    - The frontend, public API, admin API, chat streaming, media, and health endpoints all share that origin.
    - Internal workers or future supporting containers must remain on the private Docker network with no published host ports.

---

## 3. Experience model

### Desktop experience

Desktop combines publication and operations.

| Area | Desktop behavior |
| --- | --- |
| Today | Read the current issue; switch between quick and deep editions; open sources; launch chat; play audio. |
| Archive | Browse past issues by date, topic, or search. |
| Chat | Ask grounded questions about the selected issue; receive source-linked answers. |
| Admin | Manage sources, ingestion, ranking, prompts, models, schedules, generation jobs, backups, and logs. |

### Mobile experience

Mobile is a quiet, read-only daily publication with interactive understanding tools.

| Included | Excluded |
| --- | --- |
| Today’s issue | Source configuration |
| Quick/deep switch | LLM/provider configuration |
| Issue archive | Prompt editing |
| Source links | Schedules and jobs |
| Grounded chat | Logs, backups, and system health controls |
| Podcast player | Any admin forms or destructive actions |

### Responsive behavior

- Use one responsive frontend codebase.
- At narrow widths, render the publication shell only.
- `/admin` is authenticated and designed for desktop widths; mobile requests should redirect to the publication or show a clear “Desktop required” state.
- Do not rely only on user-agent or viewport detection for authorization.
- Test at approximately **390 px mobile** and **1440 px desktop**.
- No horizontal page scrolling. Touch targets must be at least 44×44 px.

---

## 4. Information architecture and routes

All routes share one origin and one externally accessible port.

| Route | Purpose | Mobile |
| --- | --- | --- |
| `/` | Today’s published issue | Yes |
| `/issues/:date` | A dated archived issue | Yes |
| `/chat/:issueId` | Source-grounded chat for one issue | Yes |
| `/media/:assetId` | Podcast/audio assets and permitted media | Yes |
| `/admin` | Admin overview | Redirect / desktop required |
| `/admin/sources` | Source and category management | No |
| `/admin/generation` | Prompts, models, schedules, and issue jobs | No |
| `/admin/system` | Logs, backups, health, and maintenance | No |
| `/api/public/*` | Publication, archive, source, chat, and media APIs | Yes |
| `/api/admin/*` | Authenticated administration APIs | No UI; server-protected |
| `/health` | Container health check | Operational |

The exact route names may change during implementation, but the **single-origin split between publication and admin capabilities is locked**.

---

## 5. System architecture

```
Computer browser ─┐
                  ├── one HTTPS origin / one external port
Mobile web app ───┘                 │
                                    ▼
                    ┌──────────────────────────────┐
                    │ Docker: application gateway │
                    │ + Elpis Python server       │
                    │ + built Preact frontend     │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
       SQLite + volumes     Built-in scheduler     Local media store
              │                    │                    │
              └──────────────┬─────┴─────────────┬──────┘
                             ▼                   ▼
                    Source connectors     Configured LLM endpoint
                    RSS / web / social    local, LAN, or remote API
```

### Initial deployment shape

- Prefer one application image/process initially because Elpis already serves its built frontend and backend together.
- Publish one configurable host port, defaulting to Elpis’s `8899` unless the project intentionally changes it.
- Run without Tailscale. Users may access the port directly over [localhost/LAN](http://localhost/LAN), place it behind a standard HTTPS reverse proxy or tunnel, or optionally use Tailscale; none of those access methods may be required by application code.
- Store SQLite, generated issues, podcast audio, and backups in named volumes or bind mounts.
- Reach a user-configured OpenAI-compatible LLM endpoint through outbound network access; do not expose the model endpoint through the product’s published port.

### Future internal workers

Podcast generation or heavy ingestion may later run in internal worker containers. If added:

- They use the same Docker network and persistent storage.
- They publish **zero** host ports.
- Users still access only the main application origin.
- Job status appears through the main API/admin panel.

---

## 6. One-port Docker contract

The Compose stack must satisfy all of the following:

- `docker compose up -d` starts the complete product.
- Only one service has a `ports:` mapping.
- All UI and API traffic uses that published service.
- Internal services use `expose:` or the private Compose network, never host mappings.
- Static frontend assets, API requests, streaming chat, audio files, and admin routes are served through the same origin.
- Health checks must cover the application and required storage.
- Secrets come from environment variables or secret files excluded from Git.
- Persistent state is outside ephemeral container layers.

### Conceptual Compose shape

```yaml
services:
  app:
    build: .
    restart: unless-stopped
    ports:
      - "${BIND_ADDRESS:-0.0.0.0}:${PORT:-8899}:8899" # the only published application port
    env_file:
      - .env
    volumes:
      - app-data:/app/data
      - app-media:/app/media
      - app-backups:/app/backups

  worker: # optional later; no published ports
    build: .
    command: ["elpis", "worker"]
    env_file:
      - .env
    volumes:
      - app-data:/app/data
      - app-media:/app/media

volumes:
  app-data:
  app-media:
  app-backups:
```

This is an architectural contract, not a claim that the application currently provides a
`worker` command. Do not add a worker container until the code has an explicit safe worker
entry point and SQLite concurrency has been reviewed.

---

## 7. Daily issue model

A daily issue is the central product object.

### Issue

- `id`
- `publication_date`
- `status`: collecting, selecting, generating, ready, failed
- `title`
- `quick_edition`
- `deep_edition`
- `selected_story_ids`
- `generated_at`
- `prompt/model provenance`
- `podcast_status`
- `podcast_asset_id`

### Story

- Existing article/source identity
- Canonical URL
- Headline and publisher
- Publication timestamp
- Extracted content/summary
- Category/topic
- Ranking score and rationale
- Duplicate cluster
- Inclusion/exclusion decision
- Citation metadata

### Chat session

- `id`
- `issue_id`
- `created_at`
- Message history
- Retrieved story/source identifiers per answer

### Podcast asset

- `issue_id`
- Script
- Voice/TTS configuration
- Audio file path
- Duration
- Generation status and error

The first implementation should avoid unnecessary schema complexity. Extend existing storage where practical, but do not force the new product model into ambiguous legacy fields.

---

## 8. Content pipeline

```
Configured sources
    ↓
Fetch and normalize
    ↓
Deduplicate and cluster
    ↓
Rank against the user’s configured interests
    ↓
Freeze one selected story set for the day
    ↓
Generate quick edition + deep edition from that same set
    ↓
Validate links, citations, and coverage
    ↓
Publish one dated issue
    ├── grounded chat becomes available
    └── podcast job may generate audio
```

### Locked editorial rule

The quick and deep editions must derive from the **same frozen story selection** so they remain two depths of one issue, not two contradictory briefings.

### Quick edition

- Target: approximately five minutes.
- Prioritize the most important developments and the minimum context needed to understand them.
- Preserve links to deeper coverage and sources.

### Deep edition

- Target: approximately 20–25 minutes.
- Expand context, cross-story relationships, differing source angles, and why each development matters.
- Do not pad the issue merely to hit a length target.

### Source layer

Sources are the evidence layer beneath both editions, not a third summary tier. Every factual claim should be traceable to one or more stored source articles.

---

## 9. Source-grounded AI chat

### Purpose

Chat helps the user understand the selected daily issue. It is not a general-purpose chatbot placed beside the news.

### Required behavior

- Chat is scoped to the currently selected issue in the initial release.
- Retrieval includes the issue’s quick/deep text, selected articles, extracted source text, and citation metadata.
- Answers distinguish sourced facts from interpretation.
- Every substantive factual answer includes article/source links.
- If the issue does not contain enough evidence, the assistant says so rather than inventing an answer.
- The configured local OpenAI-compatible model is used through the existing backend provider abstraction.
- Chat supports streaming through the same application origin and port.

### Explicit non-goals for the first release

- Searching the entire historical archive
- General web search during chat
- Autonomous source subscription changes
- Writing to admin settings

---

## 10. Podcast architecture

Podcast generation is a derived format of a published issue.

1. Wait until the daily story selection and deep edition are final.
2. Generate a conversational script grounded in the same issue and sources.
3. Run TTS as a background job.
4. Store the audio file and metadata in persistent media storage.
5. Attach the audio player to that issue.
6. Surface generation failures in desktop admin, never as a broken mobile page.

Potential implementation reference: [Podcastfy](https://github.com/souzatharsis/podcastfy). Treat it as an implementation option, not a locked dependency, until its current API, license, voices, and local-model fit are verified during the podcast phase.

---

## 11. Advisory discovery scout — later phase

The scout is separate from trusted RSS ingestion.

- Input: the user’s configured topic list and known source coverage.
- Output: candidate missed articles and candidate permanent journals/feeds.
- It does not silently subscribe to sources.
- It does not directly publish unsupported claims.
- Candidates enter an admin review queue before becoming trusted sources or appearing in an issue.

This is intentionally later than the core publication, chat, and podcast loop.

---

## 12. Visual system — Taste requirements

### Design goal

A quiet modern publication: **Think Apple, Think Notion**—clean, industrial, minimal, readable, and intentional.

### Foundation

- System sans-serif font stack
- Body text at least 16 px / 1.5 on web and mobile
- Reading column approximately 680–760 px on desktop
- Mobile gutters 16–24 px
- Desktop maximum content width 900–1120 px
- Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64
- 8 px default radius; 12 px only for larger surfaces
- Borders before shadows; shadows subtle and rare
- White canvas, restrained soft-gray surfaces, dark neutral text, one blue accent
- Respect dark-mode and reduced-motion preferences
- WCAG AA contrast and visible keyboard focus

### Recommended palette

| Role | Value |
| --- | --- |
| Primary text | `#2C2C2B` |
| Secondary text | `#7D7A75` |
| Canvas | `#FFFFFF` |
| Soft surface | `#F9F8F7` |
| Secondary surface | `#F0EFED` |
| Border | `#E6E5E3` |
| Primary accent | `#2783DE` |
| Soft accent | `#E5F2FC` |

### Anti-“AI slop” rules

Do **not** use:

- Purple/blue neon gradients as the default identity
- Glassmorphism everywhere
- Floating glowing orbs, grids, star fields, or abstract neural-network backgrounds
- Sparkle icons as generic decoration
- Excessive pills, badges, cards, and nested rounded rectangles
- Giant empty hero headings that push the actual issue below the fold
- Fake metrics, decorative charts, or AI-generated placeholder copy
- Over-animated page transitions, bouncing controls, or required motion
- Generic assistant avatars or robot imagery
- Dense dashboard layouts on mobile
- Every section in a separate card when typography and spacing would suffice

### Required visual QA

Every visible UI change must be reviewed at:

- Desktop: approximately 1440 px width
- Mobile: approximately 390 px width
- Today page, archived issue, chat open, source expanded, empty state, loading state, error state, and admin authentication state

Reject any build with overflow, overlap, cramped spacing, horizontal page scrolling, inaccessible contrast, or a generic template/AI-generated appearance.

---

## 13. Security and access control

- The application is deployment-provider independent. It must work over direct host/LAN access and behind any standards-compliant reverse proxy; Tailscale is optional only.
- Document secure [localhost](http://localhost), LAN, and public-domain deployment patterns without hardcoding any vendor.
- Keep application authentication enabled regardless of network placement.
- Admin routes and APIs require explicit admin authorization.
- Mobile UI omission is not authorization.
- When publicly exposed, HTTPS must terminate at the application gateway or the operator’s reverse proxy.
- Never expose LLM, SQLite, workers, or internal service ports directly.
- Sanitize source HTML before rendering.
- Validate and constrain outbound fetches to mitigate SSRF and unsafe local-network access.
- Preserve source attribution and prevent prompt content in fetched articles from becoming executable instructions.
- Keep secrets outside images and Git history.
- Back up the SQLite database and media before migrations.

---

## 13A. Engineering and shipping discipline

### Commit discipline

AI coding agents must commit work regularly rather than accumulating one large final commit.

- Commit after each coherent, reviewable unit: scaffolding, one route, one migration, one feature slice, one bug fix, or one documentation update.
- Create a checkpoint commit before risky migrations, dependency upgrades, large refactors, or upstream synchronization.
- Keep commits focused; do not mix unrelated formatting, refactors, features, and data migrations.
- Use descriptive imperative commit messages, preferably Conventional Commit style such as `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `build:`, and `chore:`.
- Run the relevant tests, type checks, linters, build, and visual checks before committing.
- Never commit secrets, generated private content, production databases, temporary debug artifacts, or knowingly broken code to the stable branch.
- Push working checkpoints regularly so the project can be recovered if an agent session fails.

### Shipping-ready repository artifacts

The AI is responsible for creating and maintaining every ordinary project artifact needed to install, understand, operate, contribute to, and release the product. At minimum, keep current:

- `README.md`: product purpose, screenshots, features, architecture summary, quick start, configuration, access model, and links to deeper docs
- Original upstream `LICENSE` plus clear attribution for the derived product
- `CHANGELOG.md` using a consistent release format
- `CONTRIBUTING.md` with development, testing, design-review, and commit expectations
- `SECURITY.md` with supported versions and vulnerability-reporting instructions
- `.env.example` containing every supported variable with safe placeholder values and comments
- `.gitignore` and `.dockerignore` that exclude secrets, databases, media, caches, and build artifacts
- Production `Dockerfile` and `docker-compose.yml`
- Container health checks and startup/readiness behavior
- Installation, upgrade, rollback, backup, and restore documentation
- Reverse-proxy and deployment examples that are vendor-neutral; optional Tailscale guidance may live in a separate example
- Data migration documentation and safe rollback notes
- API/route documentation for public, chat, media, and admin surfaces
- Automated tests, responsive UI tests, and CI that runs build/type/lint/test checks
- Release checklist, semantic versioning/tagging procedure, and reproducible release notes
- Architecture decision records when a major decision changes the source-of-truth design

### Definition of shipping-ready

A release is not complete merely because it works on the developer’s machine. A clean environment must be able to clone the repository, configure documented environment variables, run `docker compose up -d`, complete setup, pass health checks, and access the full product through the single published port. Documentation, tests, backups, security defaults, versioning, and rollback instructions must match the release.

---

## 14. Build phases

### Phase 0 — Independent repository and untouched baseline

- Copy the upstream baseline with full Git history.
- Point `origin` to the independent Elpis repository and `upstream` to the source repository.
- Retain MIT license/attribution.
- Confirm the upstream application works unchanged in Docker.
- Tag the untouched baseline.

### Phase 1 — One-port Docker and responsive product shell

- Establish one Compose stack and one published port.
- Rebrand the product.
- Build responsive publication navigation.
- Separate desktop admin and mobile publication surfaces.
- Add manifest/icons/Home Screen web-app polish.

### Phase 2 — Daily issue + dual editions

- Add issue model and frozen story selection.
- Generate/store quick and deep editions.
- Build Today and archive views.

### Phase 3 — Grounded chat

- Add issue-scoped retrieval, streaming, and source citations.
- Add mobile/desktop chat UI.

### Phase 4 — Podcast

- Add background script/TTS job, media persistence, failure handling, and issue player.

### Phase 5 — Advisory scout

- Add missed-article/feed discovery and desktop review queue.

---

## 15. Acceptance criteria

### Platform

- [ ]  `docker compose up -d` starts the full product in a clean documented environment.
- [ ]  Exactly one host port is published.
- [ ]  Computer and mobile use the same origin and issue data.
- [ ]  The application works without Tailscale and has no vendor-specific network dependency.
- [ ]  Direct host/LAN access and generic reverse-proxy deployment are documented and tested.
- [ ]  No internal worker/model/storage port is publicly exposed.
- [ ]  Required README, configuration, operations, security, contribution, changelog, backup/restore, and release artifacts exist and match the shipped version.
- [ ]  CI passes build, type, lint, test, and other configured release gates.

### Desktop

- [ ]  Publication features work at desktop width.
- [ ]  Authenticated admin panel can manage sources, generation, and operations.
- [ ]  Admin APIs reject unauthorized requests.

### Mobile

- [ ]  Today, archive, quick/deep editions, sources, chat, and podcast work at ~390 px.
- [ ]  No admin navigation, forms, or destructive actions are shown.
- [ ]  Direct mobile visits to admin routes do not expose admin UI.
- [ ]  Site installs/opens cleanly as a Home Screen web app.

### Content and AI

- [ ]  Quick and deep editions share one selected story set.
- [ ]  Claims retain source links.
- [ ]  Chat is grounded in one issue and cites supporting articles.
- [ ]  Insufficient evidence produces an explicit limitation, not fabrication.
- [ ]  Podcast uses the finalized issue as its source.

### Design

- [ ]  Taste / artifact-design skill was applied.
- [ ]  No AI-slop patterns listed above are present.
- [ ]  Mobile and desktop visual QA passed.
- [ ]  Typography, spacing, contrast, focus, and touch targets meet the visual contract.

---

## 16. Instructions for AI coding agents

When receiving this page as context:

1. Read the complete document before proposing code.
2. Inspect the current repository and verify the existing application behavior before changing it.
3. Diagnose current architecture from code; do not guess framework APIs, routes, commands, or data models.
4. Preserve working upstream behavior unless a requirement explicitly replaces it.
5. Present a scoped implementation plan tied to the build phases above.
6. Do not add new user-facing ports or separate mobile/desktop backends.
7. Do not make Tailscale, Barry’s hardware, or any specific hosting provider a dependency. Implement generic standards-based networking and configuration; document Tailscale only as an optional deployment example.
8. Do not implement admin authorization only through responsive hiding.
9. Use Taste / artifact-design instructions for every visible UI change.
10. Keep changes small, testable, and reversible; separate migrations from visual work.
11. Commit regularly after coherent tested units, create checkpoint commits before risky work, and push recoverable working states. Do not wait until the end of the project to commit.
12. Proactively create and maintain all README, license/attribution, environment examples, Docker, CI, test, security, contribution, changelog, deployment, backup/restore, upgrade, rollback, API, and release files needed for a genuinely shippable repository.
13. Explain every command and configuration change, and include a revert path.
14. Run automated tests plus real browser visual QA at desktop and mobile widths.
15. Before declaring a feature or release complete, verify clean-clone Docker startup, one-port access, health checks, documentation accuracy, security defaults, and rollback.
16. Update this architecture page when Barry approves an architectural decision that supersedes it.

---

## 17. References

- CondenseIt repository: [github.com/wildlifechorus/condenseit](https://github.com/wildlifechorus/condenseit)
- CondenseIt MIT license: [LICENSE](https://github.com/wildlifechorus/condenseit/blob/main/LICENSE)
- GitHub fork documentation: [Fork a repository](https://docs.github.com/articles/fork-a-repo)
- GitHub upstream remote documentation: [Configuring a remote repository for a fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/configuring-a-remote-repository-for-a-fork)
- Optional deployment example only — Tailscale Serve: [Tailscale Serve documentation](https://tailscale.com/docs/features/tailscale-serve)
- iPhone Home Screen web apps: [Apple Support](https://support.apple.com/guide/iphone/open-as-web-app-iphea86e5236/ios)
- Podcast implementation reference: [Podcastfy](https://github.com/souzatharsis/podcastfy)

*Architecture created: 2026-07-12. Product name approved as Elpis; it is an independent product with preserved upstream history.*