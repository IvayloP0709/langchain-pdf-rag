---
title: Containerize and deploy the FastAPI backend to ECS Fargate
status: ready-for-agent
---

## Problem Statement

The FastAPI backend (`src/api/app.py`) currently only runs locally (`uvicorn`, or via `python -m src.main`/pytest's `test_api_smoke.py`). There is no Dockerfile, no container registry setup, and no running cloud deployment — CLAUDE.md's "Not started" list explicitly calls out Terraform/CI-CD-deploy/CloudWatch as not begun, and Phase 2's goal is a real cloud-deployed backend, not just localhost. The backend also needs to consume the credentials/endpoints produced by the other Phase 2 tracks (Qdrant, RDS Postgres, SageMaker reranker endpoint) once those exist.

## Solution

Containerize the FastAPI app with Docker, publish the image to a container registry (ECR), and run it on ECS Fargate in a public subnet with a security group restricting inbound traffic to the expected ports/sources (no NAT Gateway, no streaming — plain REST, per CLAUDE.md). Secrets (Qdrant API key, DB credentials, OpenAI API key, reranker endpoint name) are injected into the ECS task definition from SSM Parameter Store rather than baked into the image or task definition in plaintext. This is the track that wires together the outputs of `docs/specs/qdrant-vectorstore-migration.md`, `docs/specs/postgres-chat-memory-migration.md`, and `docs/specs/reranker-sagemaker-endpoint.md` into one running service — it should be sequenced after (or with clear stubs/fallbacks for) those three, since the deployed task definition needs real values for their env vars to actually work end-to-end.

## User Stories

1. As the developer, I want a `Dockerfile` for the FastAPI backend that installs dependencies from `pyproject.toml`/`requirements.txt` and runs `uvicorn` against `src.api.app:app`, so the backend can be built into a portable container image.
2. As the developer, I want the Docker image built on a slim Python base matching the project's supported version (`>=3.8`, CI currently pins `3.9`), so image size and behavior stay predictable and consistent with what CI already tests against.
3. As the developer, I want a `.dockerignore` excluding `data/`, `chroma_db/`, `models/`, `.venv/`, test caches, and other local-only artifacts, so the built image doesn't unnecessarily bundle multi-hundred-MB of local corpus/model data that production instead reaches via Qdrant/S3/SageMaker.
4. As the developer, I want the image published to Amazon ECR, so ECS Fargate has a registry to pull from.
5. As the developer, I want an ECS Fargate cluster, task definition, and service created (manually, per CLAUDE.md's "manual provisioning this phase" decision) in `eu-central-1`, running the published image with a public subnet and a security group that only allows inbound traffic on the API port from the expected source (initially: open for direct testing, tightened once CloudFront/the frontend's origin is known — document the actual rule chosen), and no NAT Gateway.
6. As the developer, I want the ECS task definition's environment injected from SSM Parameter Store (SecureString) for all secrets — `OPENAI_API_KEY`, `QDRANT_API_KEY`, DB credentials, reranker endpoint name — rather than plaintext task-definition env vars, consistent with CLAUDE.md's secrets decision.
7. As the developer, I want the ECS task's IAM task role scoped to exactly what the running app needs at runtime (SSM `GetParameter`(s) for its own secrets, `sagemaker:InvokeEndpoint` on the reranker endpoint's ARN per `docs/specs/reranker-sagemaker-endpoint.md`), and the task execution role scoped to what ECS itself needs (ECR pull, CloudWatch log group write), so neither role is broader than necessary.
8. As the developer, I want the container's `/health` endpoint (already implemented) wired as the ECS task/service health check, so unhealthy tasks are detected and replaced automatically.
9. As the developer, I want container stdout/stderr shipped to CloudWatch Logs (the default `awslogs` driver in the task definition), so I have basic visibility into the running service even though the full CloudWatch dashboards/alarms work is deferred to Phase 5.
10. As the developer, I want `validate_runtime_config()` to run at container startup (it already does, via the app's existing request-time check, or ideally a startup-time check) so a misconfigured task definition (missing secret, bad env var) surfaces immediately as an unhealthy task rather than a confusing first-request failure.
11. As the developer, I want the running service's `/health`, `/ask`, and `/chat/{session_id}` endpoints manually verified against the deployed task (curl or equivalent) after each of the dependent tracks (Qdrant, RDS, SageMaker reranker) lands, so I have concrete confirmation the wiring works end-to-end, not just that each piece works in isolation.
12. As the developer, I want a documented build-and-deploy procedure (a script under `scripts/` or a documented manual sequence — implementer's call, note that full CI/CD automation is explicitly out of scope/deferred to Phase 5) for building the image, pushing to ECR, and updating the ECS service, so redeploying after a code change isn't a from-scratch improvisation each time.
13. As the developer, I want the deployed backend's default `persist_directory`/`DATABASE_URL`/`QDRANT_*`/reranker env vars set to point at the real Qdrant/RDS/SageMaker resources (once those tracks are done), so this is genuinely the "everything wired together" milestone for Phase 2, not just an isolated container running with nothing behind it.
14. As the developer, I want the AWS resource choices (ECS Fargate over Lambda, public-subnet-no-NAT over private-subnet-with-NAT, plain REST over streaming) documented in `docs/decisions.md` with their cost/complexity rationale, so the tradeoffs are preserved for interview talking points per CLAUDE.md's convention.
15. As a future maintainer, I want the Dockerfile and task definition kept simple enough that Phase 5's GitHub Actions CI/CD deploy step and Terraform retrofit can build on top of this without a rewrite (e.g. the image build doesn't depend on manual pre-steps that a pipeline couldn't reproduce), so this phase's "manual is fine for now" approach doesn't create throwaway work later.

## Implementation Decisions

**New files:**
- `Dockerfile` — multi-stage or single-stage build (implementer's call, document tradeoff) installing the project via `pip install .` (or `-r requirements.txt`) and running `uvicorn src.api.app:app --host 0.0.0.0 --port 8000` (or the chosen port).
- `.dockerignore` — excludes `data/`, `chroma_db/`, `models/`, `.venv/`, `.git/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, test fixtures not needed at runtime.
- A deploy script/documented procedure (e.g. `scripts/deploy_backend.sh` or a `docs/deploy.md` runbook) covering: `docker build`, `docker push` to ECR, and `aws ecs update-service --force-new-deployment` (or task-definition-revision update) — implementer's call on exact mechanics, but it must be repeatable without re-deriving each command from scratch.

**Modified modules:**
- `src/config.py` — if not already sufficient, ensure `validate_runtime_config()` covers every env var the deployed task definition will supply, so a bad SSM value fails fast.
- `.env.example` — reconcile with the full set of env vars introduced by this and the three dependent tracks, so it's an accurate single reference for what the deployed environment needs.

**Config additions:**
- Backend port (e.g. `PORT` or hardcoded `8000`, implementer's call, document it).
- No new application-level env vars beyond what the Qdrant/RDS/SageMaker tracks already introduce — this ticket is about deployment plumbing, not new app config.

**Provisioning (manual, this phase):** ECR repository; ECS cluster, task definition, service (Fargate, public subnet, security group); IAM task role and task execution role; CloudWatch log group. All in `eu-central-1`, via console/CLI, per CLAUDE.md.

## Testing Decisions

- **Existing API tests** (`tests/test_api_smoke.py`): should continue to pass unmodified against the containerized app locally (`docker build` + `docker run` + smoke-test the endpoints, or run the existing pytest suite inside the built container) — this is the primary automated check that containerization didn't change app behavior.
- **Dockerfile build**: add a CI step (or documented local step, since full CI/CD deploy automation is deferred to Phase 5 — implementer's call whether this belongs in `.github/workflows/ci.yml` now or is manual for this phase) that runs `docker build .` to catch build breakage early, without necessarily pushing/deploying from CI yet.
- **Deployed-service verification**: not a unit test — the manual endpoint checks in story #11 are the acceptance check for this ticket, documented as a runbook/checklist rather than automated.
- **IAM policy scoping**: no automated test; manually verify (e.g. via `aws iam simulate-principal-policy` or just observed behavior) that the task role can do what it needs and nothing obviously broader, documented as part of the provisioning notes.

## Out of Scope

- GitHub Actions CI/CD deploy automation (Phase 5) — this ticket covers manual build/push/deploy only.
- Terraform for any of these AWS resources (Phase 5).
- CloudWatch dashboards/alarms beyond basic log shipping (Phase 5).
- Custom domain / ACM cert for the backend itself (CLAUDE.md: default AWS domain, no custom domain for now — that decision is scoped to the frontend's CloudFront distribution, not the backend).
- Streaming responses / WebSocket support — plain REST only, per CLAUDE.md.
- Autoscaling configuration beyond whatever ECS Fargate service defaults to.
- The Qdrant, RDS, and SageMaker reranker tracks themselves (separate specs) — this ticket consumes their outputs but doesn't implement them.
- Frontend deploy (separate spec: `docs/specs/frontend-react-vite-migration.md`).

## Further Notes

- This is the integration point for the other three Phase 2 backend tracks — it's reasonable to start the Dockerfile/ECR/ECS scaffolding in parallel with them, but the "everything wired together and manually verified" acceptance bar (story #11/#13) can't fully close until Qdrant, RDS, and the SageMaker endpoint are live.
- Security-group inbound rules should be revisited once the frontend's CloudFront distribution exists (`docs/specs/frontend-react-vite-migration.md`) — CLAUDE.md specifies "security-group-restricted inbound" without pinning down the exact source, so document whatever rule is actually implemented and why.
