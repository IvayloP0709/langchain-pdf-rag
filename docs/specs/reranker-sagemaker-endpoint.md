---
title: Serve the fine-tuned reranker behind a SageMaker Serverless Inference endpoint
status: ready-for-agent
---

## Problem Statement

The fine-tuned cross-encoder reranker (`src/retrieval/reranker.py`, `models/reranker/finetuned/`, delivered in Phase 4 / issues #1-#5) runs in-process today: `create_reranker("finetuned")` loads the local checkpoint directly into whatever process calls it (CLI, API, eval runner). CLAUDE.md flags this as the one piece of Phase 4 left open — a trained model with its own served inference endpoint is explicitly what differentiates this project from "just an API wrapper" for ML engineering portfolio purposes, and in-process loading doesn't demonstrate that. It's also operationally awkward for ECS Fargate: every backend task would need to load and hold the model in memory itself, coupling the API container's resource footprint to the reranker's.

## Solution

Deploy the existing fine-tuned checkpoint behind a SageMaker Serverless Inference endpoint (chosen over always-on real-time inference to stay within free/low-cost bounds for a portfolio project with intermittent traffic), and add a remote-serving implementation of the existing `Reranker` protocol (`src/retrieval/reranker.py`) that calls the endpoint over HTTP instead of loading the model locally. `create_reranker`'s factory interface is the seam — `RERANKER_MODE=finetuned` in the deployed environment resolves to the remote implementation, while `pretrained`/local-`finetuned` remain available for local dev/testing without needing live AWS credentials.

## User Stories

1. As the developer, I want the fine-tuned cross-encoder checkpoint (`models/reranker/finetuned/`) packaged and deployed to a SageMaker Serverless Inference endpoint, so the reranker has its own served inference endpoint as CLAUDE.md's ML engineering layer requires.
2. As the developer, I want a `RemoteReranker` (or similarly named) class implementing the existing `Reranker` protocol's `rerank(query, docs) -> List[Document]` method by calling the SageMaker endpoint's invocation API, so that call sites (`create_retriever`'s `_RerankingRetriever`) don't need to know or care whether reranking happens locally or remotely.
3. As the developer, I want `create_reranker` to return the `RemoteReranker` when a new mode/flag (e.g. `RERANKER_MODE=finetuned` combined with a `RERANKER_ENDPOINT_URL` env var being set, or a distinct `RERANKER_MODE=finetuned_remote` value — implementer's call, document the choice) is active, so switching between local and remote serving is a config change, not a code change.
4. As the developer, I want the SageMaker endpoint's request/response contract documented (input: query + list of candidate doc texts; output: relevance scores in the same order), so the `RemoteReranker`'s HTTP call shape is a clear, testable contract independent of the SageMaker plumbing itself.
5. As the developer, I want the SageMaker inference container/entry-point script to load the exact checkpoint from `models/reranker/finetuned/` (or an S3-uploaded copy of it) and run the same `CrossEncoder.predict()` call the in-process `CrossEncoderReranker` uses today, so remote-served scores are equivalent to local scores for the same input, not a re-implementation that could silently diverge.
6. As the developer, I want the model artifact uploaded to S3 (SageMaker Serverless Inference requires model artifacts in S3, not local disk) as part of the deploy process, so the endpoint has something to load at cold start.
7. As the developer, I want SageMaker Serverless Inference's memory size and max-concurrency settings chosen appropriately for a MiniLM-class cross-encoder model, so cold-start latency and cost stay reasonable for a low-traffic portfolio deployment.
8. As the developer, I want the endpoint invoked with the AWS SDK (`boto3`'s `sagemaker-runtime` client) using IAM credentials available to the ECS task (via its task role), not a long-lived static access key baked into config, so credential handling follows least-privilege AWS practice.
9. As the developer, I want a clear timeout and error-handling path in `RemoteReranker.rerank` for SageMaker cold-start latency or endpoint unavailability, so a slow/failed reranking call degrades gracefully (e.g. falls back to unreranked candidates with a logged warning) rather than hanging or crashing the whole `search_documents` tool call.
10. As the developer, I want the eval harness able to run against the remote-served reranker (not just local `finetuned` mode), so I can confirm end-to-end that the deployed endpoint produces retrieval quality consistent with the local three-way comparison already recorded in `docs/decisions.md`.
11. As the developer, I want a documented, repeatable deploy script/procedure (e.g. `scripts/deploy_reranker_endpoint.py` or a documented manual console/CLI procedure — implementer's call given "manual provisioning this phase" per CLAUDE.md) for creating/updating the SageMaker model, endpoint config, and serverless endpoint, so re-deploying after a future reranker re-training run isn't a from-scratch improvisation.
12. As the developer, I want the endpoint's IAM execution role scoped to only what SageMaker inference needs (read the model artifact from its S3 location, write CloudWatch logs), so it doesn't carry broader permissions than necessary.
13. As the developer, I want local dev and CI to keep working without live AWS credentials by defaulting to local `pretrained`/`finetuned` reranker modes, so the SageMaker dependency is opt-in for anyone testing the remote path specifically, not a hard requirement for running the test suite.
14. As the developer, I want the SageMaker deployment decision (serverless vs. real-time inference, memory/concurrency sizing, cost estimate) documented in `docs/decisions.md`, so the rationale is preserved for interview talking points per CLAUDE.md's convention.
15. As a future maintainer, I want the local (`CrossEncoderReranker`) and remote (`RemoteReranker`) implementations to share the same `Reranker` protocol and same test doubles' expected behavior (given fixed scores, output order matches descending score), so a future re-training or endpoint swap doesn't require touching `create_retriever` or `search_documents` at all.

## Implementation Decisions

**New modules:**
- `src/retrieval/reranker.py` (extended) — new `RemoteReranker` class implementing the `Reranker` protocol, backed by a `boto3` `sagemaker-runtime` client's `invoke_endpoint` call. Takes an endpoint name (from `RERANKER_ENDPOINT_NAME`/`RERANKER_ENDPOINT_URL` env var) and constructs the request payload (query + candidate doc texts), parses the response into per-doc scores, and sorts descending — mirroring `CrossEncoderReranker.rerank`'s sort logic so both implementations are provably equivalent in behavior given the same scores.
- A SageMaker inference entry-point script (e.g. `scripts/sagemaker/inference.py` or `deploy/reranker/inference.py` — implementer's call on location) implementing the SageMaker inference container contract (`model_fn`/`input_fn`/`predict_fn`/`output_fn` for a scikit-learn/PyTorch-style container, or a custom container's equivalent), loading the fine-tuned `CrossEncoder` checkpoint and running `.predict(pairs)` the same way `_load_cross_encoder`/`CrossEncoderReranker` do today.
- A deploy script or documented procedure to: upload `models/reranker/finetuned/` to S3, create/update the SageMaker Model, EndpointConfig (serverless), and Endpoint resources.

**Modified modules:**
- `src/retrieval/reranker.py` — `create_reranker` factory gains branching to return `RemoteReranker` when the deployed/remote mode is selected, alongside the existing `none`/`pretrained`/local-`finetuned` branches.
- `src/config.py` — `validate_runtime_config()` gains validation for the new remote-reranker env vars when that mode is selected (e.g. `RERANKER_ENDPOINT_NAME` required if `RERANKER_MODE` selects remote serving).
- `.env.example` — add the new reranker-endpoint env vars with comments distinguishing local vs. remote modes.
- `requirements.txt` / `pyproject.toml` — add `boto3` as a runtime dependency (currently absent) for the `RemoteReranker`'s SageMaker Runtime client.

**Config additions:**
- `RERANKER_ENDPOINT_NAME` (env var): SageMaker endpoint name, consulted only when remote serving mode is active.
- AWS region for the `boto3` client sourced consistently with the rest of the deployment (`eu-central-1`).

**Provisioning (manual, this phase):** S3 bucket/prefix for the model artifact, SageMaker Model/EndpointConfig/Endpoint (serverless), IAM execution role scoped to S3 read + CloudWatch logs, all created via console/CLI per CLAUDE.md's "manual provisioning this phase" decision.

## Testing Decisions

- **`RemoteReranker.rerank`** (`src/retrieval/reranker.py`): unit test with a stubbed/mocked `boto3` SageMaker Runtime client (no real endpoint call) — given a fixed mocked response payload of scores, assert the returned doc order matches descending score, mirroring the existing `CrossEncoderReranker` test pattern in `tests/test_reranker.py`. Also test the timeout/error-handling fallback path (mocked client raises/times out → graceful degradation, not a crash).
- **`create_reranker` remote-mode branching** (`tests/test_reranker.py`): extend the existing factory tests to cover the new mode, asserting it returns a `RemoteReranker` instance configured from the expected env vars, without making a real network call.
- **`validate_runtime_config` additions** (`src/config.py`/`tests/test_config.py`): add cases for the new remote-reranker env vars.
- **Inference entry-point script**: not unit tested against a real SageMaker container build (too slow/environment-specific for CI); a lightweight local smoke test invoking the `model_fn`/`predict_fn`-equivalent functions directly against a tiny fixture input, confirming output shape, is sufficient — following the existing smoke-test convention used for `scripts/train_reranker.py`.
- **End-to-end endpoint verification**: not part of automated CI (requires a live deployed endpoint); documented as a manual verification step — invoke the deployed endpoint with a known query/candidate set and confirm scores are consistent with the local `finetuned` mode's scores for the same input, then optionally re-run the eval harness against the remote mode per story #10.

## Out of Scope

- Re-training or improving the reranker model itself — this ticket serves the existing fine-tuned checkpoint, it doesn't retrain it.
- Real-time (always-on) SageMaker inference — Serverless Inference is the explicit Phase 2 decision.
- Terraform for SageMaker resources (Phase 5).
- Vector store or chat memory migrations (separate specs).
- ECS/container/deploy work for the FastAPI backend itself (separate spec: `docs/specs/backend-ecs-fargate-deploy.md`), though that spec's IAM task role will need permission to invoke this endpoint — noted as a dependency, not implemented here.

## Further Notes

- This ticket is naturally sequenced after the reranker fine-tuning work (already done, issues #1-#5) but is independent of the vector store and chat memory migrations — it can be implemented in parallel with those.
- The ECS backend deploy spec will need an IAM task role permission (`sagemaker:InvokeEndpoint` scoped to this endpoint's ARN) — call this out explicitly when writing that spec/ticket so it isn't missed.
- Cold-start latency for SageMaker Serverless Inference can be a few seconds on first invocation after idle; document observed cold-start numbers in `docs/decisions.md` since they matter for the "why we chose Serverless over real-time" interview talking point.
