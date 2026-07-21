---
title: Vector store migration — local Chroma to Qdrant Cloud
status: ready-for-agent
---

## Problem Statement

The vectorstore is currently a local ChromaDB directory (`chroma_db/`, `persist_directory` param threaded through `create_vectorstore`/`load_vectorstore`/CLI/API). Phase 2 moves the FastAPI backend onto ECS Fargate, whose task storage is ephemeral — any local Chroma directory would silently vanish on every task restart or redeploy, destroying the ingested corpus with no error at deploy time, only a confusing empty-retrieval failure sometime after. The project also wants to demonstrate cloud vector infra as part of its MLOps/cloud-engineering story, which a local embedded vectorstore doesn't provide.

## Solution

Swap the vectorstore backend from local Chroma to Qdrant Cloud (free tier), keeping the existing `create_vectorstore`/`load_vectorstore` seam in `src/retrieval/vectorstore.py` as the single integration point. Everything downstream of that seam — `create_retriever`, the reranking wrapper, the agent's `search_documents` tool, the eval runner's `retrieval_direct` measurement, ingestion — continues to work against whatever `Document`-yielding retriever object the seam returns, so this migration should not require changes outside `src/retrieval/vectorstore.py`, its call sites' connection parameters, and config/env plumbing. Qdrant connection details (cluster URL, API key) are read from env vars and provisioned manually in Qdrant Cloud's console for this phase (per CLAUDE.md, Terraform for all infra is deferred to Phase 5).

## User Stories

1. As the developer, I want `create_vectorstore`/`load_vectorstore` to talk to a Qdrant Cloud collection instead of a local Chroma directory, so that the ingested corpus survives ECS Fargate task restarts and redeploys.
2. As the developer, I want the existing `create_vectorstore(documents, embeddings, ...)` / `load_vectorstore(embeddings, ...)` function signatures preserved as closely as possible, so that `populate_vectorstore.py`, `src/main.py`, and `src/api/app.py` need minimal changes beyond swapping the persistence-location parameter for Qdrant connection parameters.
3. As the developer, I want Qdrant connection details (`QDRANT_URL`, `QDRANT_API_KEY`, collection name) read from environment variables following the same pattern as `EMBEDDING_PROVIDER`/`OPENAI_API_KEY`, so that local dev and deployed environments configure the same way as everything else in `src/config.py`.
4. As the developer, I want `validate_runtime_config()` to fail fast with a clear message if `QDRANT_URL` or `QDRANT_API_KEY` is missing, so that a misconfigured deployment fails at startup rather than on the first retrieval call.
5. As the developer, I want a Qdrant Cloud free-tier cluster provisioned manually in `eu-central-1`-adjacent region (closest available free-tier region) via the Qdrant Cloud console, so that latency from the `eu-central-1` ECS backend stays low, consistent with CLAUDE.md's region decision.
6. As the developer, I want the Qdrant collection created with the correct vector size and distance metric matching the embedding model in use (`OPENAI_EMBEDDING_MODEL`/`LOCAL_EMBEDDING_MODEL`), so that ingestion doesn't fail on a dimension mismatch.
7. As the developer, I want collection creation/existence-checking handled idempotently (create-if-not-exists) inside `create_vectorstore`/ingestion rather than requiring a manual pre-step every time, so that `python -m src.main ingest` keeps working as a single command like it does today.
8. As the developer, I want the existing `--clean` ingestion flag (`src/main.py`'s `run_ingest`) to translate to "delete and recreate the Qdrant collection" instead of "rmtree the local directory," so that re-ingestion after document changes still avoids duplicate chunks.
9. As the developer, I want `load_vectorstore`'s current "not found, run ingestion first" error (`FileNotFoundError` today) preserved as an equivalent, clear error when the configured Qdrant collection doesn't exist, so that the CLI/API error messages users see today don't regress.
10. As the developer, I want the eval harness's `retrieval_direct` and `retrieval_agent` metrics re-measured once against Qdrant with the same frozen `eval_set.jsonl` and same corpus, so that I can confirm the migration doesn't silently regress retrieval quality relative to the recorded Chroma baseline (`data/eval/runs/history.csv`).
11. As the developer, I want local development to still work without depending on network access to Qdrant Cloud for quick iteration, so I want to evaluate (and document the decision either way) whether local dev keeps using free-tier Qdrant Cloud directly or a local Qdrant Docker container pointed at by the same `QDRANT_URL`/`QDRANT_API_KEY`-shaped config.
12. As the developer, I want the Qdrant API key stored in SSM Parameter Store (SecureString) for the deployed environment, consistent with CLAUDE.md's secrets decision, and documented as a local `.env` value for local dev, so that the credential handling is consistent with how `OPENAI_API_KEY` is already handled.
13. As the developer, I want the `langchain-qdrant` (or equivalent) integration package added to `requirements.txt`/`pyproject.toml` dependencies, so that the new vectorstore client is available the same way `langchain_chroma`/`chromadb` are today.
14. As the developer, I want `chromadb`/`langchain_chroma` removed from the hard dependency set once the migration is complete (or clearly marked as no-longer-used-by-default), so the dependency list reflects what's actually running in production.
15. As the developer, I want existing tests that monkeypatch or stub the vectorstore seam (e.g. `tests/test_retrievers.py`, `tests/test_main_ingest.py`) updated to reflect the new Qdrant-backed `create_vectorstore`/`load_vectorstore` signatures, so the test suite keeps passing without depending on real network calls to Qdrant Cloud.
16. As the developer, I want the migration documented in `docs/decisions.md` (why Qdrant Cloud, what changed, any retrieval-quality delta observed), so the rationale is preserved for interview talking points per CLAUDE.md's stated convention.
17. As a future maintainer, I want the Qdrant-specific client details isolated inside `src/retrieval/vectorstore.py` rather than leaking into `src/retrieval/retrievers.py`, `src/agent/tools.py`, or `src/eval/runner.py`, so that a future vector-store swap (if ever needed) stays a single-seam change like this one.

## Implementation Decisions

**Modified modules:**
- `src/retrieval/vectorstore.py` — `create_vectorstore(documents, embeddings, ...)` and `load_vectorstore(embeddings, ...)` reimplemented against `langchain_qdrant.QdrantVectorStore` (or the current idiomatic LangChain Qdrant integration package), reading `QDRANT_URL`, `QDRANT_API_KEY`, and a collection-name parameter (default sourced from a `QDRANT_COLLECTION` env var) instead of `persist_directory`. Collection creation is idempotent — check-and-create rather than assuming pre-existence. `load_vectorstore` raises a clear, typed error (mirroring today's `FileNotFoundError` semantics) when the collection doesn't exist or is empty.
- `populate_vectorstore.py` — `persist_directory` parameter and its "Saved to: {persist_directory}" messaging replaced with the Qdrant collection name/URL equivalent; the rest of the loading/chunking pipeline (Steps 1–2) is unaffected.
- `src/main.py` — `run_ingest`'s `--clean` handling changes from `shutil.rmtree(persist_directory)` to a "delete Qdrant collection if it exists" call before ingestion; `--persist-directory` CLI flags across `ingest`/`ask`/`chat`/`eval` subcommands either get renamed/repurposed to a collection-name flag or dropped in favor of the env-var-driven Qdrant config, whichever keeps the CLI surface smallest — implementer's call, document the choice in `docs/decisions.md`.
- `src/api/app.py` — `_ensure_vectorstore_loaded(persist_directory)` and the `IngestRequest`/`AskRequest`/`ChatRequest` schemas' `persist_directory` field updated to match whatever CLI-level naming decision is made above, so the API and CLI stay consistent.
- `src/config.py` — `validate_runtime_config()` gains checks for `QDRANT_URL`/`QDRANT_API_KEY` presence, following the existing `OPENAI_API_KEY` check pattern.
- `.env.example` — add `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` with comments; retire the Chroma-specific persistence comments if the CLI flag is renamed.
- `requirements.txt` / `pyproject.toml` — add the Qdrant LangChain integration dependency; remove `chromadb`/`langchain_chroma` if nothing else in the codebase still needs them (check `src/eval/`, tests, and scripts before removing).
- `.gitignore` — `chroma_db/` entry can be removed once nothing writes there by default (verify no other script still targets it, e.g. `scripts/generate_reranker_training_set.py`'s retriever usage).

**Config additions:**
- `QDRANT_URL` (env var, required): Qdrant Cloud cluster REST endpoint.
- `QDRANT_API_KEY` (env var, required): Qdrant Cloud API key, sourced from SSM Parameter Store (SecureString) in the deployed environment.
- `QDRANT_COLLECTION` (env var, default e.g. `rag_documents`): collection name, replacing the role `persist_directory` played for Chroma.

**Provisioning (manual, this phase):** Qdrant Cloud free-tier cluster created via console in the region closest to `eu-central-1`; API key generated and stored in SSM Parameter Store. No Terraform for this yet, per CLAUDE.md.

## Testing Decisions

- **`create_vectorstore`/`load_vectorstore`** (`src/retrieval/vectorstore.py`): unit test against a fake/stub Qdrant client (monkeypatch the `langchain_qdrant` client construction), not a real network call — assert idempotent collection creation is attempted, and that `load_vectorstore` raises the expected error when the collection is missing/empty. No test should require live Qdrant Cloud credentials to pass in CI.
- **`create_retriever`/reranking wrapper** (`tests/test_retrievers.py`): update existing fixtures/monkeypatches to construct fake retrievers the same way regardless of backend — these tests already operate above the vectorstore seam and shouldn't need Qdrant-specific changes beyond fixture setup, confirming the seam boundary held.
- **Ingestion** (`tests/test_main_ingest.py`): update the `--clean` test to assert a "delete collection" call happens instead of asserting `rmtree` on a directory.
- **`validate_runtime_config` additions** (`src/config.py`/`tests/test_config.py`): add cases for missing `QDRANT_URL`/`QDRANT_API_KEY`.
- **End-to-end retrieval-quality check**: not a unit test — run `python -m src.main eval` once against the migrated, re-ingested Qdrant-backed corpus with the existing frozen `eval_set.jsonl`, and record the result in `docs/decisions.md`/`history.csv` per story #10. This requires live Qdrant Cloud credentials and is a manual verification step, not part of the automated CI suite.

## Out of Scope

- Document-upload-to-S3 (still admin-script-only ingestion, per CLAUDE.md — out of scope here).
- Terraform for Qdrant/AWS resources (Phase 5).
- Changing the embedding model or re-scoping the 20-paper corpus.
- Reranker serving changes (separate spec: `docs/specs/reranker-sagemaker-endpoint.md`).
- Postgres chat-memory migration (separate spec: `docs/specs/postgres-chat-memory-migration.md`).
- Any ECS/container/deploy work itself (separate spec: `docs/specs/backend-ecs-fargate-deploy.md`) — this spec only makes the backend code cloud-storage-ready, it doesn't deploy it.

## Further Notes

- Baseline numbers this migration must not silently regress below (Chroma, `RERANKER_MODE=finetuned`, from `docs/decisions.md`): `retrieval_direct` hit_rate 0.966 / MRR 0.966 / precision 0.885 / page_hit_rate 0.786; `retrieval_agent` hit_rate 0.931 / MRR 0.882 / precision 0.759 / page_hit_rate 0.778. A small delta from ANN-index/backend differences is expected and acceptable; a large regression should be investigated (e.g. distance-metric mismatch) before proceeding to the next Phase 2 track.
- Consider whether `RERANK_CANDIDATE_K` over-fetch behavior (`_base_retriever` in `src/retrieval/retrievers.py`) needs any Qdrant-specific `search_kwargs` translation — LangChain's Qdrant retriever wrapper should expose an equivalent `as_retriever(search_kwargs={"k": ...})` API, but confirm before assuming parity with the current Chroma `mmr`/`similarity` `search_type` handling.
