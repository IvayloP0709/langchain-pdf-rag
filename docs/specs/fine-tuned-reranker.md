---
title: Fine-tuned cross-encoder reranker for retrieval quality
status: ready-for-agent
---

## Problem Statement

The RAG assistant's retrieval quality has a measured, documented gap: on the 20-paper arXiv baseline (29-question eval set), `retrieval_direct` scores hit_rate 0.931 / MRR 0.914 / precision 0.782, while the ranking produced by plain cosine-similarity search over the embedding vectorstore is the ceiling the rest of the pipeline works with. There is currently no mechanism to re-rank retrieved candidates by finer-grained relevance — the top-k returned by the vectorstore is final. This also means the project has no trained/fine-tuned ML component of its own; every capability so far is orchestration around a general-purpose LLM API, which undercuts the project's stated purpose of demonstrating ML engineering (not just API-wrapping) for AI/ML engineering job applications.

## Solution

Add a second retrieval stage: over-fetch a wider candidate pool from the existing vectorstore, then re-score and reorder those candidates with a cross-encoder reranker before truncating to the final `RETRIEVAL_K`. The reranker is fine-tuned locally on a synthetic, domain-specific training set generated from the project's own ingested corpus, starting from a pretrained MiniLM cross-encoder rather than training from scratch. Both the interactive agent and the eval harness are wired through the same retrieval seam so the improvement (or lack of it) is real for actual agent answers, not just an eval-only number. The result is evaluated with a three-way comparison (no reranker / pretrained reranker / fine-tuned reranker) against the existing frozen eval set, so the fine-tuning's specific marginal contribution is isolated and documented either way.

## User Stories

1. As the developer, I want retrieval to over-fetch a wide candidate pool and rerank it down to the final k, so that a cross-encoder gets enough candidates to meaningfully reorder rather than just re-sorting an already-truncated top-3.
2. As the developer, I want the candidate pool size to be independently configurable from the final retrieval k, so that I can tune reranking recall/precision tradeoffs without touching the agent-facing `RETRIEVAL_K`.
3. As the developer, I want a single retrieval seam (`create_retriever`) used by both the agent's `search_documents` tool and the eval runner's `retrieval_direct` measurement, so that reranking improvements (or regressions) are real for actual agent answers and not an eval-only artifact.
4. As the developer, I want to fine-tune a pretrained MiniLM cross-encoder rather than train one from scratch, so that the training is feasible on local hardware within a solo weekend-project timeframe.
5. As the developer, I want a script that generates synthetic (query, positive chunk) pairs by prompting an LLM with each ingested chunk, so that I have training data without hand-labeling.
6. As the developer, I want hard negatives mined from the current (un-fine-tuned) retriever's top results for each synthetic question, so that the reranker learns to distinguish genuinely relevant chunks from merely topically-similar ones.
7. As the developer, I want hard-negative mining to exclude chunks from the same source document as the positive, so that I don't mislabel a chunk that's actually relevant (same-paper subtopic overlap) as a negative.
8. As the developer, I want the synthetic training set generated strictly disjoint from the existing 29-question eval set, so that the before/after eval comparison isn't contaminated by training-on-the-test-set.
9. As the developer, I want an 85/15 train/validation split of the synthetic pairs, so that I can monitor for overfitting during fine-tuning.
10. As the developer, I want the cross-encoder fine-tuned via `sentence-transformers`' `CrossEncoder.fit()` with binary relevance labels, so that I use the standard, well-supported training path for this model family instead of a hand-rolled training loop.
11. As the developer, I want the fine-tuned model checkpoint selected by lowest validation loss across a small number of epochs, so that training doesn't overfit the small synthetic set.
12. As the developer, I want the trained model artifact saved to a gitignored local directory rather than committed to git, so that the repository doesn't carry binary model weights while the training pipeline stays fully reproducible from the training script.
13. As the developer, I want a `Reranker` interface with a single `rerank(query, docs)` method, backed locally by the fine-tuned cross-encoder today, so that the same call sites can later point at a remote SageMaker/Lambda inference endpoint (Cloud Deploy phase) without changing retrieval call sites.
14. As the developer, I want a `RERANKER_MODE` setting (`none` / `pretrained` / `finetuned`) read the same way existing settings like `RETRIEVAL_K` and `EMBEDDING_PROVIDER` are, so that switching reranking behavior doesn't require code changes, just config.
15. As the developer, I want `RERANKER_MODE` validated in `validate_runtime_config()`, so that an invalid value fails fast with a clear error instead of silently falling back.
16. As the developer, I want to run the eval harness three times (baseline, pretrained reranker, fine-tuned reranker) against the unchanged `eval_set.jsonl`, so that all three data points land in `history.csv` for direct comparison.
17. As the developer, I want the three-way comparison to isolate "adding any reranker" from "fine-tuning the reranker," so that I can truthfully describe the fine-tuning's specific contribution rather than conflating it with the effect of reranking in general.
18. As the developer, I want a documented decision rule (any directional MRR/precision improvement from pretrained → fine-tuned counts as success) fixed before seeing results, so that I don't rationalize a threshold after the fact.
19. As the developer, I want the three-way comparison result documented in `docs/decisions.md` regardless of outcome, so that a flat or negative result is preserved as a legitimate, defensible evaluation finding rather than something to quietly drop.
20. As the developer, I want the LLM used for synthetic question generation to be `gpt-4o-mini`, consistent with the existing eval-set generator and judge, so that I don't introduce a second model/provider purely for this step.
21. As a future maintainer (including future-me in a new session), I want the reranker's training and integration to follow existing repo conventions (`scripts/` for one-off generation/training scripts, env-var-driven config, `create_retriever` as the retrieval seam), so that the addition reads as consistent with the rest of the codebase rather than a bolted-on side project.

## Implementation Decisions

**New modules:**
- `src/retrieval/reranker.py` — defines a `Reranker` interface/protocol with `rerank(query: str, docs: List[Document]) -> List[Document]` (returns docs reordered by descending relevance, same length/content as input, no truncation inside `rerank` itself). Includes a local implementation backed by `sentence_transformers.CrossEncoder`, loading either the pretrained checkpoint (`cross-encoder/ms-marco-MiniLM-L-6-v2`, downloaded from HuggingFace) or the fine-tuned local checkpoint depending on mode. Exposes a `create_reranker(mode: str, model_path: Optional[str] = None) -> Optional[Reranker]` factory (returns `None` for `mode="none"`), mirroring the existing `create_retriever` factory pattern in `src/retrieval/retrievers.py`.
- `scripts/generate_reranker_training_set.py` — generates synthetic (query, positive chunk) pairs via `gpt-4o-mini` (one question per ingested chunk), mines hard negatives from the current (un-fine-tuned) retriever's top results excluding same-source-document chunks, excludes any overlap with `data/eval/eval_set.jsonl` questions, writes an 85/15 train/val split to disk (format: JSONL, one `{query, doc_text, label}` per line, mirroring the existing `EvalExample`/`write_eval_set` pattern in `src/eval/schema.py`).
- `scripts/train_reranker.py` — loads the generated training/val JSONL, fine-tunes `cross-encoder/ms-marco-MiniLM-L-6-v2` via `CrossEncoder.fit()` with binary labels, 2-4 epochs, selects the checkpoint with lowest validation loss, saves to `models/reranker/finetuned/`.

**Modified modules:**
- `src/retrieval/retrievers.py` — `create_retriever` gains a `reranker_mode` parameter (default `"none"`, sourced from `RERANKER_MODE` env var by callers) and a `candidate_k` parameter (default sourced from `RERANK_CANDIDATE_K` env var, defaulting to 15). When `reranker_mode != "none"`, internally builds the base vectorstore retriever with `k=candidate_k`, and returns a wrapping retriever whose `.invoke(query)` fetches the wide candidate set, calls `create_reranker(reranker_mode).rerank(query, candidates)`, and truncates to the requested final `k`. When `reranker_mode == "none"`, behavior is unchanged from today (direct `k`-sized retrieval, no wrapping).
- `src/agent/tools.py` — `search_documents` no longer calls `_vectorstore.similarity_search(query, k=k)` directly. Instead it calls `create_retriever(_vectorstore, k=k, reranker_mode=os.getenv("RERANKER_MODE", "none"))` and invokes that retriever. This unifies the agent's real retrieval path with the eval runner's, so reranking affects actual agent answers, not just the `retrieval_direct` eval metric.
- `src/eval/runner.py` — `run_evaluation` reads `RERANKER_MODE` (or accepts a `reranker_mode` parameter, mirroring how `k`/`search_type` are already parameters) and passes it to `create_retriever`. `summary` dict gains a `reranker_mode` field so `history.csv` rows record which configuration produced each run.
- `src/config.py` — `validate_runtime_config()` gains validation for `RERANKER_MODE` (must be one of `none`/`pretrained`/`finetuned`) and `RERANK_CANDIDATE_K` (must be a positive integer, same pattern as the existing `RETRIEVAL_K`/`DOC_PREVIEW_CHARS` checks).
- `.gitignore` — add `models/` so the trained reranker artifact isn't committed.
- `docs/decisions.md` — new file (doesn't exist yet) if not already created by the time this is implemented; add an entry recording the reranker approach and the three-way eval comparison result.

**Config additions:**
- `RERANKER_MODE` (env var): `none` (default) / `pretrained` / `finetuned`.
- `RERANK_CANDIDATE_K` (env var): integer, default `15` — wide candidate pool size fetched before reranking, independent of `RETRIEVAL_K`.
- `RERANKER_MODEL_PATH` (env var): path to the fine-tuned checkpoint, default `models/reranker/finetuned`. Only consulted when `RERANKER_MODE=finetuned`; `pretrained` mode always loads `cross-encoder/ms-marco-MiniLM-L-6-v2` from HuggingFace regardless of this variable.

**Dependency note:** `sentence-transformers` is already present as an optional `local` extra in `pyproject.toml` — no new dependency needed, but it should move from optional to a hard dependency (or the `local` extra should be documented as required) if reranking is meant to work by default, since it's not currently installed in the base dependency set.

## Testing Decisions

Tests should exercise behavior through the same seams the codebase already tests through, not reach into cross-encoder internals:

- **`create_retriever` reranking behavior** (`src/retrieval/retrievers.py`): extend the existing seam already used in `tests/test_eval_runner_smoke.py` (which monkeypatches `retrievers.create_retriever`). Add a direct unit test for `create_retriever` itself: given a fake base retriever returning a known-order candidate list and a fake `Reranker` (injected via monkeypatching `create_reranker`) that reorders deterministically, assert the final output is reordered and truncated to `k`. Also assert `reranker_mode="none"` preserves today's exact behavior (regression coverage) — this is the one existing test that will need its monkeypatch signature updated to match the new `create_retriever` parameters.
- **`Reranker.rerank` logic** (`src/retrieval/reranker.py`): unit test with a stub scoring model (not a real loaded cross-encoder) that returns fixed scores for known (query, doc) pairs, asserting the output ordering matches descending score. No test should load real model weights or hit HuggingFace — that's slow and not what's under test.
- **`search_documents` tool** (`src/agent/tools.py`): extend/adjust existing tool tests (or add one alongside the pattern in `tests/test_agent_sources.py`/`tests/test_nodes.py`) to monkeypatch `create_retriever` and confirm the tool calls it instead of `_vectorstore.similarity_search` directly.
- **`run_evaluation` reranker plumbing** (`src/eval/runner.py`): extend `tests/test_eval_runner_smoke.py`'s existing fixture-based smoke test to assert `reranker_mode` is threaded into the `create_retriever` call and recorded in the returned summary.
- **`validate_runtime_config` additions** (`src/config.py`): no existing `test_config.py` — add one, following the assertion style already implied by `validate_runtime_config`'s existing checks (valid values pass, invalid `RERANKER_MODE`/`RERANK_CANDIDATE_K` values return `(False, message)`).
- **Hard-negative mining logic** (`scripts/generate_reranker_training_set.py`): unit test the mining function in isolation with a small fixture set of chunks spanning 2+ documents, asserting negatives are only drawn from documents other than the positive's source.
- **Training script** (`scripts/train_reranker.py`): not unit tested against real training (too slow, not deterministic); a lightweight smoke test with a tiny fixture dataset (a handful of pairs) and 1 epoch, asserting it runs end-to-end and writes a model directory to a `tmp_path`, following the smoke-test convention already used in `tests/test_eval_runner_smoke.py` and `tests/test_main_ingest.py`.

## Out of Scope

- Cloud-hosted serving of the reranker (SageMaker endpoint / ONNX-behind-Lambda) — the `Reranker` interface is designed to make this swap possible later, but the served-endpoint work itself belongs to the Cloud Deploy phase per CLAUDE.md's phased plan.
- Expanding or re-ingesting the corpus beyond the existing 20 papers.
- Regenerating or modifying the existing 29-question `eval_set.jsonl` — it stays frozen so before/after comparisons remain valid.
- Query/intent classifier and fine-tuned embedding model — the two alternative ML-engineering-layer options CLAUDE.md already ruled out in favor of the reranker.
- Iterating on training hyperparameters/data volume to force a win if the fine-tuned model doesn't beat the pretrained baseline — a flat or negative result is an acceptable, documented outcome for this scope.
- Postgres-backed memory, Qdrant/Pinecone migration, or any other later-phase infra work unrelated to reranking.

## Further Notes

- The existing baseline numbers this work is compared against (commit `529f36f`): `retrieval_direct` hit_rate 0.931 / MRR 0.914 / precision 0.782 / page_hit_rate 0.630; `retrieval_agent` hit_rate 0.828 / MRR 0.805 / precision 0.609 / page_hit_rate 0.583. Note the agent path already underperforms direct retrieval before any reranking is introduced — the reranker targets ranking quality given a candidate set, not this separate agent-vs-direct gap, so it's plausible reranking improves both paths proportionally without closing that gap.
- `RETRIEVAL_K` currently defaults to `3` (not `5` as an earlier draft of this plan assumed) — `RERANK_CANDIDATE_K` default of `15` is calibrated as 5x that actual default.
- Corpus size caveat: ~20 papers is a small base for synthetic training-pair generation; if chunk count turns out too low for a meaningful training set (implementer should check actual chunk count from the existing Chroma store before committing to the 1-question-per-chunk/3-hard-negatives sizing), revisit sizing before training rather than proceeding with too little data.
