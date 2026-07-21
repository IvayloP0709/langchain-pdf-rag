---
title: Chat memory migration — local SQLite to RDS Postgres
status: ready-for-agent
---

## Problem Statement

Chat memory (`src/agent/memory.py`) currently persists conversation history to a local SQLite file (`chat_history.db`, via `SQLChatMessageHistory`). Once the FastAPI backend runs on ECS Fargate, that file lives on ephemeral task storage and is silently lost on every restart or redeploy — a user's conversation history would vanish without warning, and horizontally-scaled tasks wouldn't even share the same file to begin with. The project's tech stack also commits to Postgres via RDS + SQLAlchemy + Alembic (chosen over Prisma because its Python client is a community wrapper, not first-party) as the standard data layer, and chat memory is the first concrete schema that layer needs to own.

## Solution

Provision a small, single-AZ, free-tier-eligible RDS Postgres instance (manual provisioning this phase, per CLAUDE.md) and point `SQLChatMessageHistory` at it via a Postgres connection string instead of SQLite, introducing SQLAlchemy + Alembic for schema management even though `SQLChatMessageHistory` itself manages its own table — Alembic is set up now so it's the established pattern for any future schema (session metadata, document metadata) rather than retrofitting migrations later. The `create_agent_with_memory`/`get_chat_history` seam in `src/agent/memory.py` stays the integration point; call sites (`src/api/app.py`, `src/main.py`'s `run_chat`) shouldn't need to change beyond how the connection string is sourced.

## User Stories

1. As the developer, I want `get_chat_history`'s default connection string to point at RDS Postgres instead of local SQLite, so that chat history survives ECS Fargate task restarts and redeploys.
2. As the developer, I want the Postgres connection string built from env vars (`DATABASE_URL` or discrete `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`) rather than hardcoded, following the same pattern as `QDRANT_URL`/`OPENAI_API_KEY`, so local dev and deployed environments configure identically to the rest of `src/config.py`.
3. As the developer, I want `validate_runtime_config()` to fail fast with a clear message when the Postgres connection details are missing, so a misconfigured deployment fails at startup rather than on the first chat message.
4. As the developer, I want an RDS Postgres instance provisioned manually (smallest free-tier-eligible class, single-AZ, `eu-central-1`) via the AWS console/CLI, so the running deployment has somewhere to connect to — Terraform for this is deferred to Phase 5 per CLAUDE.md.
5. As the developer, I want the RDS instance's security group to allow inbound Postgres traffic only from the ECS Fargate backend's security group (not the public internet), so chat history isn't exposed to unauthenticated network access.
6. As the developer, I want the DB credentials (host, port, database name, username, password) stored in SSM Parameter Store (SecureString), consistent with CLAUDE.md's secrets decision, rather than committed anywhere or passed as plaintext task-definition env vars.
7. As the developer, I want SQLAlchemy + Alembic introduced into the project (even though `SQLChatMessageHistory` manages its own table automatically) so that a migrations workflow exists before the next schema need (session metadata, document metadata) arrives, rather than retrofitting it later under time pressure.
8. As the developer, I want an initial Alembic migration environment set up (`alembic init` scaffolding, `alembic.ini`, `env.py` wired to read `DATABASE_URL` from the same config source as the rest of the app) even if its first migration is a no-op or just documents the `SQLChatMessageHistory`-managed table, so the tooling is proven end-to-end before it's load-bearing.
9. As the developer, I want local development to be able to run against a local/dockerized Postgres instance (or the real RDS instance, developer's choice) using the same `DATABASE_URL`-shaped config as production, so there isn't a SQLite-vs-Postgres code fork between environments.
10. As the developer, I want the existing `SimpleMemory`/in-memory fallback class in `src/agent/memory.py` (if still used anywhere) reviewed for whether it should be retired now that persistent memory is the default path, so dead code doesn't linger — document the decision either way.
11. As the developer, I want `tests/test_memory.py`'s existing pattern (spin up an isolated SQLite DB per test via `tmp_path`, monkeypatch `get_chat_history`) preserved but adapted to Postgres, so tests stay fast and hermetic — using a local/dockerized Postgres test instance or a lightweight Postgres-compatible test double, whichever keeps CI from depending on live RDS credentials.
12. As the developer, I want connection pooling/timeout behavior sane for a serverless-ish Fargate deployment (short-lived task lifecycle, potential cold starts), so the app doesn't hang or leak connections against the small free-tier RDS instance's connection limit.
13. As the developer, I want the migration documented in `docs/decisions.md` (why RDS Postgres over alternatives, why Alembic set up now rather than deferred, any gotchas with `SQLChatMessageHistory`'s Postgres dialect support), so the rationale is preserved for interview talking points per CLAUDE.md's convention.
14. As a future maintainer, I want the Postgres-specific connection details isolated to config/`memory.py` rather than leaking into `src/api/app.py`'s route handlers or `src/main.py`'s CLI commands beyond how they source the connection string, so the memory backend stays swappable behind one seam like the vectorstore backend does.

## Implementation Decisions

**New/added tooling:**
- Alembic scaffolding (`alembic.ini`, `alembic/env.py`, `alembic/versions/`) added to the repo root, `env.py` wired to build its DB URL from the same env-var source as `src/config.py`/`src/agent/memory.py` rather than a separate hardcoded config, so there's exactly one place connection details are assembled.
- `psycopg` (or `psycopg2-binary`, implementer's call — document which and why) added as the Postgres DB driver dependency alongside the already-present `sqlalchemy`.

**Modified modules:**
- `src/agent/memory.py` — `get_chat_history`'s default `connection_string` changes from `"sqlite:///chat_history.db"` to a value built from `DATABASE_URL`/discrete DB env vars (via a small helper, e.g. `build_connection_string()`, colocated in this module or `src/config.py`). `SQLChatMessageHistory` itself is unchanged (it already supports any SQLAlchemy-compatible connection string, including Postgres).
- `src/config.py` — `validate_runtime_config()` gains checks for the Postgres connection env vars, following the existing `OPENAI_API_KEY`/`QDRANT_URL` check pattern.
- `.env.example` — add `DATABASE_URL` (or discrete `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`) with comments; note that `sqlite:///chat_history.db` remains a valid override for quick local iteration if the implementer decides to keep that escape hatch (document the decision either way).
- `.gitignore` — `chat_history.db` entry can stay (harmless if nothing writes there by default) or be removed if the SQLite path is fully retired — implementer's call.
- `requirements.txt` / `pyproject.toml` — add the chosen Postgres driver and `alembic`.

**Provisioning (manual, this phase):** RDS Postgres instance (smallest free-tier class, single-AZ, `eu-central-1`), security group restricting inbound to the ECS backend's security group, credentials stored in SSM Parameter Store (SecureString).

## Testing Decisions

- **`get_chat_history`/connection-string construction** (`src/agent/memory.py`): unit test the connection-string-building helper directly (given env vars, assert the resulting connection string shape) without needing a real DB connection.
- **`test_memory_persistence`** (`tests/test_memory.py`): keep the existing structure (monkeypatch `memory.get_chat_history`, run a fake 2-turn conversation, assert history persists and grows) but point it at a Postgres test database instead of a `tmp_path` SQLite file. If CI can't reasonably run a live Postgres instance, mark this test with a `slow`/`integration`-style marker (mirroring the existing `slow` marker convention in `pyproject.toml`) and document how to run it locally against a dockerized Postgres, so CI doesn't require live RDS credentials.
- **Alembic wiring**: a lightweight smoke test (or manual verification step, documented) confirming `alembic upgrade head` runs cleanly against a throwaway Postgres database — doesn't need to be part of the default `pytest` run if it requires a live DB, but should be runnable on demand.
- **`validate_runtime_config` additions** (`src/config.py`/`tests/test_config.py`): add cases for missing Postgres connection env vars, following the existing test style.

## Out of Scope

- Session metadata or document metadata schemas beyond what `SQLChatMessageHistory` already manages — Alembic is introduced now so it's ready for those, but no new schema is designed in this ticket.
- Terraform for RDS (Phase 5).
- Vector store migration (separate spec: `docs/specs/qdrant-vectorstore-migration.md`).
- ECS/container/deploy work itself (separate spec: `docs/specs/backend-ecs-fargate-deploy.md`) — this spec only makes the backend code and RDS instance ready, it doesn't deploy the backend.
- Multi-AZ/high-availability RDS configuration — single-AZ is the explicit Phase 2 decision.

## Further Notes

- `SQLChatMessageHistory` (from `langchain_community.chat_message_histories`) is built on SQLAlchemy under the hood and is documented to support Postgres connection strings directly — confirm the exact dialect string format (`postgresql+psycopg://...` vs `postgresql://...`) matches whichever driver is chosen before assuming parity with the SQLite path.
- The free-tier RDS instance has a low max-connections ceiling; if the ECS task scales beyond one instance later, connection pooling behavior here is worth revisiting (noted for awareness, not blocking for this ticket since Phase 2 doesn't specify autoscaling).
