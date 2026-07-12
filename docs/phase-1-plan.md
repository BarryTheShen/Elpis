# Phase 1 implementation plan

## Scope

Deliver the one-port, responsive publication shell without changing CondenseIt's
collection, ranking, generation, storage, scheduling, or provider behavior.
Product naming remains intentionally neutral until an approved identity exists.

## Reuse map

| Existing seam | Phase 1 decision |
| --- | --- |
| `docker-compose.yml`, `Dockerfile`, FastAPI SPA serving | Retain the single `8899` host port and single application process; add only readiness metadata required by the new deployment contract. |
| `web.app.create_app`, `SessionMiddleware`, `web.admin` router | Retain session/password authentication and server-side admin protection; split read-only publication access from mutable/admin APIs. |
| `store.database.ContentStore` and `./data` volume | Retain SQLite storage and the persisted volume unchanged. No issue schema or migration in this phase. |
| `pipeline.DigestPipeline`, collectors, `PreferenceEngine` | Retain ingestion, normalization, ranking, and digest generation unchanged. |
| `web.scheduler` and `web.digest_job` | Retain scheduling and job execution unchanged. |
| `providers.factory` and provider implementations | Retain configured local/OpenAI-compatible provider selection unchanged. |
| Preact/Vite frontend and current PWA assets | Rework only the routing shell and navigation. Preserve the existing digest rendering as the temporary publication content surface. |

## Changes

1. Centralize neutral visitor-facing UI metadata so a later approved name can
   replace it in one place; keep static package and URL metadata unchanged.
2. Make only read-only digest publication endpoints public. Keep source,
   scheduler, configuration, run, ratings, and other state-changing endpoints
   authenticated on the server.
3. Replace the global frontend login gate with public publication routes and an
   admin-only authentication boundary.
4. Introduce a responsive publication layout: desktop may expose the admin
   entry point after authentication; narrow screens show no admin navigation or
   destructive controls, including on direct `/admin/*` visits.
5. Preserve the single-origin PWA mechanics. Defer manifest identity and icon
   replacement until the product name and an approved asset package exist.
6. Add focused API and frontend-build coverage for the public/private boundary;
   exercise the shell at desktop and 390 px widths.

## Explicit deferrals

- Daily issue persistence and quick/deep editions (Phase 2)
- Issue-scoped retrieval and chat (Phase 3)
- Podcast jobs and media persistence (Phase 4)
- Advisory source discovery (Phase 5)
- Final product name, branded icons, and GitHub `origin` configuration

## Verification and rollback

Verification is: targeted FastAPI authorization tests, `npm run build`, local
Docker startup on the existing single `8899` port, `/health`, and desktop/mobile
browser checks. A coherent Phase 1 commit is recoverable by reverting that
commit; deployment config remains compatible with the tagged
`condenseit-upstream-baseline`.