---
title: Frontend migration — Streamlit to React + Vite, deployed to S3 + CloudFront
status: ready-for-agent
---

## Problem Statement

The current UI (`src/ui/app.py`) is a Streamlit app — always described in CLAUDE.md as "a stand-in for the planned React+Vite frontend," a Phase 1 open decision now resolved in favor of migrating. Streamlit is also not a natural fit for the intended deployment shape (static build to S3 + CloudFront) — it needs a running Python server, coupling frontend hosting to backend-style compute. The project's stated tech stack and "what this should let the candidate truthfully claim" both name a decoupled React + FastAPI architecture explicitly, which the current Streamlit UI doesn't demonstrate.

## Solution

Build a React + Vite single-page app that replicates the existing Streamlit UI's three workflows (ingest, ask, chat) against the same FastAPI backend (`/health`, `/ingest`, `/ask`, `/chat/{session_id}`) via a small isolated API client module, matching the existing `_api_get`/`_api_post` helper pattern in spirit. Deploy the production build as a static site to S3 + CloudFront, using CloudFront's default AWS-provided domain (no custom domain/Route 53 for now, per CLAUDE.md). The Streamlit app is retired once the React app reaches parity, not kept as a second maintained UI.

## User Stories

1. As a user, I want a chat-style message list showing my questions and the assistant's answers in order, so that a multi-turn conversation reads naturally instead of as disconnected request/response pairs.
2. As a user, I want to see source/citation info (document name, snippet) attached to each assistant answer, so that I can verify where an answer's claims came from — matching the existing Streamlit "Sources" expander behavior.
3. As a user, I want to upload PDF files and trigger ingestion from the UI, so that I can add documents to the corpus without using the CLI directly — matching the existing Streamlit "Ingest" tab.
4. As a user, I want to ask a one-off question (no persisted session) as well as have a persistent chat session, so both the `/ask` and `/chat/{session_id}` backend workflows remain reachable from the UI, matching today's Streamlit tabs.
5. As a user, I want a visible health-check indicator for the backend API, so I know immediately if the backend is unreachable rather than getting a confusing failure on my first request.
6. As a user, I want the chat session ID and API base URL configurable in the UI (defaulting sensibly), so I can point the frontend at different backend deployments (local vs. deployed) without rebuilding, matching today's Streamlit sidebar settings.
7. As a developer, I want the API client logic isolated in a small `api/` module (per CLAUDE.md's TypeScript/React conventions) with typed request/response shapes mirroring `src/api/schemas.py`'s Pydantic models, so route handlers/components don't each hand-rig `fetch` calls.
8. As a developer, I want functional components and hooks throughout (per CLAUDE.md's conventions), with no class components, so the codebase style is consistent and idiomatic modern React.
9. As a developer, I want the app built with Vite (not Next.js — the backend is a separate FastAPI service, keep frontend decoupled per CLAUDE.md), so the build stays a plain static SPA compatible with S3 + CloudFront hosting.
10. As a developer, I want loading and error states handled explicitly for each API call (ingest/ask/chat/health), so failures surface as clear UI feedback instead of silent hangs or unhandled promise rejections — matching the existing Streamlit `try/except` + `st.error` pattern's intent.
11. As a developer, I want the production build's API base URL configurable at build/deploy time (e.g. via a Vite env var baked in at build, or a small runtime-config fetch), so the same codebase can point at different backend deployments without a source change — mirroring the `API_BASE_URL` env var pattern already used by Streamlit and the CLI.
12. As a developer, I want the built static assets (`dist/`) uploaded to an S3 bucket configured for static website hosting or as a CloudFront origin, so the frontend is served entirely from static infra with no server process to run/scale.
13. As a developer, I want a CloudFront distribution in front of the S3 bucket using CloudFront's default `*.cloudfront.net` domain (no custom domain/Route 53/ACM cert for the frontend itself, per CLAUDE.md), so the frontend is reachable over HTTPS without extra DNS/cert setup this phase.
14. As a developer, I want CloudFront configured to serve `index.html` for SPA client-side routing fallback (if client-side routes beyond `/` are introduced) or explicitly confirmed unnecessary if the app stays single-route, so deep links/refreshes don't 404 against S3's default behavior.
15. As a developer, I want the S3 bucket's access restricted to CloudFront only (Origin Access Control/Identity, not public bucket access), so the storage layer isn't directly exposed.
16. As a developer, I want a documented build-and-deploy procedure (a script under `scripts/` or a `docs/` runbook) for building the Vite app and syncing/invalidating S3 + CloudFront, so redeploying after a frontend change isn't a from-scratch improvisation — full CI/CD automation for this is deferred to Phase 5 per CLAUDE.md.
17. As a developer, I want the Streamlit app (`src/ui/app.py`) removed (or clearly marked deprecated and excluded from any deploy path) once the React app reaches feature parity, so the project doesn't carry two maintained UIs.
18. As a developer, I want the CORS configuration on the FastAPI backend (`src/api/app.py`) updated to allow requests from the deployed CloudFront origin (and `localhost` for local dev), so the deployed frontend can actually call the deployed backend — noting FastAPI currently has no CORS middleware configured at all, so this needs to be added, not just adjusted.
19. As the developer, I want the frontend/backend URL choices and any deployment gotchas (CloudFront cache invalidation, CORS, base-URL config) documented in `docs/decisions.md`, so the rationale and any pitfalls are preserved for interview talking points per CLAUDE.md's convention.

## Implementation Decisions

**New project structure:**
- A new frontend project directory (e.g. `frontend/` at repo root — implementer's call on exact name/location, document it) scaffolded via Vite's React (+ TypeScript, per CLAUDE.md's "TypeScript/React" convention) template.
- `frontend/src/api/` module — typed client functions (`getHealth`, `postIngest`, `postAsk`, `postChat`) mirroring `src/api/schemas.py`'s `HealthResponse`/`IngestRequest`/`IngestResponse`/`AskRequest`/`AskResponse`/`ChatRequest`/`ChatResponse` shapes as TypeScript types, isolated from UI components per CLAUDE.md's convention.
- Components covering: message list/chat view, source/citation display, PDF upload + ingest trigger, settings (API base URL, session ID), health-check indicator — component boundaries are the implementer's call, but should map cleanly onto the existing Streamlit tabs' functionality (ingest / ask / chat) as a checklist for parity.

**Modified backend modules:**
- `src/api/app.py` — add `fastapi.middleware.cors.CORSMiddleware` configured to allow the deployed CloudFront origin and `http://localhost:*` for local dev, sourced from an env var (e.g. `ALLOWED_ORIGINS`) rather than hardcoded, so the allowed origin list doesn't need a code change when the CloudFront domain is known.
- `src/config.py` — optionally validate `ALLOWED_ORIGINS` is set in the deployed environment (implementer's call on strictness).

**Retired:**
- `src/ui/app.py` (Streamlit UI) and its `streamlit` dependency in `requirements.txt`/`pyproject.toml`, once the React app reaches parity — remove rather than leave as unmaintained dead code, per repo conventions against lingering half-migrated code.

**Provisioning (manual, this phase):** S3 bucket (private, CloudFront-origin-only via OAC), CloudFront distribution (default domain, HTTPS via the default CloudFront certificate — no ACM cert needed since there's no custom domain), all in `eu-central-1` for the S3 bucket (CloudFront itself is a global service — no region choice there, and note per CLAUDE.md that only a future custom-domain ACM cert would need to be in `us-east-1`, which doesn't apply here since no custom domain is used this phase).

## Testing Decisions

- **API client module** (`frontend/src/api/`): unit tests (Vitest, the natural Vite-ecosystem test runner — implementer's call to confirm, but should be introduced since no frontend test tooling exists yet) mocking `fetch`, asserting request shapes and response parsing match the backend's actual Pydantic schemas, so a schema drift between frontend and backend fails a test rather than surfacing as a runtime bug.
- **Components**: lightweight rendering/interaction tests (React Testing Library, paired with Vitest) for the core flows — sending a chat message updates the message list, uploading a file + clicking ingest calls the API client, an API error surfaces a visible error state — prioritizing behavior over implementation detail, consistent with this repo's Python testing philosophy of testing through the same seams the app itself uses.
- **CORS configuration** (`src/api/app.py`): extend `tests/test_api_smoke.py` (or add a focused test) asserting the CORS middleware is present and configured, following the existing smoke-test pattern for the FastAPI app.
- **End-to-end parity check**: not automated — a manual checklist comparing the deployed React app's ingest/ask/chat flows against the retired Streamlit app's behavior, run once before removing `src/ui/app.py`, documented as the acceptance step for this ticket.
- **CI**: `.github/workflows/ci.yml` gains a frontend job (lint/typecheck/test the Vite app, e.g. `npm ci && npm run lint && npm run test`) alongside the existing Python job, so frontend regressions are caught the same way backend ones are — full deploy automation stays deferred to Phase 5, this is just the test/build gate.

## Out of Scope

- Custom domain / Route 53 / ACM certificate for the frontend — CloudFront's default domain only, per CLAUDE.md.
- GitHub Actions CI/CD deploy automation to S3/CloudFront (Phase 5) — this ticket covers manual build/sync/invalidate only, plus a CI *test* job (not deploy).
- Streaming responses in the UI — the backend serves plain REST, no WebSocket/SSE UI work.
- Auth/billing (Stripe) — explicitly an optional stretch goal elsewhere in CLAUDE.md, not part of this migration.
- Redesigning the UX beyond what the existing Streamlit tabs already cover — this is a framework migration for parity plus the stated tech-stack requirements (message list, streaming-capable display even if not used yet, source/citation display), not a UX overhaul.
- Backend deploy itself (separate spec: `docs/specs/backend-ecs-fargate-deploy.md`) — this ticket assumes the backend is reachable at some URL, whether local or deployed, and only wires the frontend build's API base URL to it.

## Further Notes

- This track is independent of the Qdrant/Postgres/SageMaker backend tracks and can be built and even deployed in parallel with them — the frontend only needs *a* reachable backend URL (local during development, the deployed ECS URL once `docs/specs/backend-ecs-fargate-deploy.md` lands) to function.
- CORS is currently entirely unconfigured on the FastAPI app (no middleware at all) — this is a real gap this ticket must close, not an existing setting to merely adjust; without it, the deployed CloudFront-origin frontend cannot call the backend at all.
