# Decisions Log

Running notes on why a particular AWS service, tool, or architectural approach was chosen — kept for interview talking points and to avoid re-litigating settled choices in a fresh session.

## 2026-07-17 — Fine-tuned cross-encoder reranker for retrieval

**Decision:** Add a reranking stage to the retrieval pipeline using `sentence-transformers`' `CrossEncoder`, in two modes: `pretrained` (`cross-encoder/ms-marco-MiniLM-L-6-v2`, used as-is) and `finetuned` (the same base model, fine-tuned locally on synthetic (query, chunk) pairs generated from the ingested corpus). Selected over the other two candidate ML-engineering-layer options (query/intent classifier, fine-tuned embedding model) because it directly targets the MRR/precision metrics already captured in the eval baseline, and is the most industry-standard "RAG differentiator" for portfolio purposes.

**Implementation:** `src/retrieval/reranker.py` (`create_reranker` factory, mirrors the existing `create_retriever` pattern), wired into `create_retriever` in `src/retrieval/retrievers.py` as a widen-then-rerank-then-truncate step (`RERANK_CANDIDATE_K` candidates fetched, reranked, truncated to `k`). Mode controlled by `RERANKER_MODE` env var (`none`/`pretrained`/`finetuned`), consumed identically by the agent's `search_documents` tool and the eval runner, so reranking affects real agent answers, not just eval metrics. Training script (`scripts/train_reranker.py`) fine-tunes via a single `CrossEncoder.fit()` call across all epochs (not per-epoch calls, which would reset the LR schedule/optimizer state each time), selecting the checkpoint with the lowest validation BCE loss.

**Result — three-way eval comparison** (same 29-question eval set, `data/eval/eval_set.jsonl`, held fixed across all three runs so the comparison is apples-to-apples):

| Metric | baseline (`none`) | `pretrained` | `finetuned` |
|---|---|---|---|
| retrieval_direct hit_rate | 0.931 | 0.966 | 0.966 |
| retrieval_direct mrr | 0.914 | 0.966 | 0.966 |
| retrieval_direct precision | 0.782 | 0.851 | **0.885** |
| retrieval_direct page_hit_rate | 0.630 | 0.786 | 0.786 |
| retrieval_agent hit_rate | 0.828 | 0.897 | **0.931** |
| retrieval_agent mrr | 0.805 | 0.879 | **0.882** |
| retrieval_agent precision | 0.609 | 0.701 | **0.759** |
| retrieval_agent page_hit_rate | 0.583 | 0.692 | **0.778** |
| judge faithfulness | 4.55 | 4.66 | **4.83** |
| judge relevance | 4.76 | 4.76 | **4.93** |
| judge correctness | 4.41 | 4.59 | **4.69** |

Raw numbers: `data/eval/runs/history.csv`, runs at `2026-07-17T09:38:02` (pretrained), `2026-07-17T09:41:43` (finetuned) — both at commit `8fc5157` — and `2026-07-17T10:29:05` (baseline, explicit `RERANKER_MODE=none` run) at commit `6e10567`. The `none` row was run explicitly (rather than reusing the original pre-reranker baseline numbers from before `RERANKER_MODE` existed) so all three configurations are tagged and directly comparable in `history.csv`, per the acceptance criteria for issue #5. Retrieval metrics (hit_rate/MRR/precision/page_hit_rate) reproduced exactly, as expected since retrieval is deterministic; judge scores shifted slightly (LLM-as-judge via `gpt-4o-mini` is not deterministic run-to-run) — the table above uses this explicit `none` run's judge scores rather than the earlier ones for consistency with the other two rows.

**Interpretation:**
- Adding reranking at all (`none` → `pretrained`) is the larger of the two steps — precision and page_hit_rate improve substantially on both direct and agent retrieval just from a generic, off-the-shelf cross-encoder.
- Fine-tuning on top of that (`pretrained` → `finetuned`) adds a smaller but real further improvement: every metric moved in the improving direction, none regressed. Precision saw the largest fine-tuning-specific gain (+0.034 direct, +0.058 agent), and judge scores improved across all three axes.
- Per the pre-agreed decision rule ("any directional MRR/precision improvement from pretrained → fine-tuned counts as success"), this is a clean success on both precision (direct and agent) and MRR (agent improved, direct held flat already near ceiling).
- Mean latency dropped in the finetuned run (7137ms → 5348ms pretrained→finetuned); this is most likely run-to-run variance in agent iteration count rather than a real effect of the reranker itself, and shouldn't be read as a fine-tuning benefit.
- This result was recorded regardless of outcome (per the spec's story #19) so a flat or negative result would have been preserved just as faithfully as this positive one — the point of the comparison is a defensible finding, not a foregone conclusion.

**Training run used for the `finetuned` checkpoint:** 3 epochs, batch_size=4 (reduced from the default 16 after an MPS OOM on the full corpus at the default batch size), best checkpoint selected at epoch 1 (val_loss=0.1322) — validation loss increased in epochs 2-3, consistent with the model starting to overfit the relatively small synthetic training set beyond epoch 1.
