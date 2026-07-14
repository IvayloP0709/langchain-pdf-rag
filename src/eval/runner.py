import os
import subprocess
import time
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Optional

from src.eval.costs import CostTracker
from src.eval.metrics import aggregate_retrieval_metrics, compute_retrieval_metrics
from src.eval.report import write_run_report
from src.eval.schema import load_eval_set


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[idx]


def _get_git_sha() -> Optional[str]:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        return None


def _aggregate_judge_scores(
    judge_scores: List[Dict[str, Any]], num_failures: int
) -> Dict[str, Any]:
    if not judge_scores:
        return {
            "faithfulness_mean": None,
            "relevance_mean": None,
            "correctness_mean": None,
            "num_judge_failures": num_failures,
        }
    return {
        "faithfulness_mean": round(mean(s["faithfulness"] for s in judge_scores), 2),
        "relevance_mean": round(mean(s["relevance"] for s in judge_scores), 2),
        "correctness_mean": round(mean(s["correctness"] for s in judge_scores), 2),
        "num_judge_failures": num_failures,
    }


def run_evaluation(
    eval_set_path: str = "data/eval/eval_set.jsonl",
    persist_directory: str = "./chroma_db",
    k: Optional[int] = None,
    judge_model: str = "gpt-4o-mini",
    agent_model: str = "gpt-4o-mini",
    output_dir: str = "data/eval/runs",
    limit: Optional[int] = None,
    skip_judge: bool = False,
    search_type: str = "similarity",
    reranker_mode: Optional[str] = None,
    candidate_k: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the eval set through both a direct retriever and the full agent graph,
    score answer quality with an LLM judge, and write a timestamped run report.

    `agent_model` is only used as a cost-estimation fallback (the agent's own LLM
    model is configured in src.agent.nodes, not here).
    """
    from src.agent.graph import create_agent_graph
    from src.agent.sources import extract_sources_from_messages
    from src.eval.judge import judge_answer
    from src.main import build_initial_state, initialize_vectorstore
    from src.retrieval.retrievers import create_retriever

    examples = load_eval_set(eval_set_path)
    if limit is not None:
        examples = examples[:limit]
    if not examples:
        raise ValueError(f"Eval set at {eval_set_path} has no examples to run.")

    k = k or int(os.getenv("RETRIEVAL_K", "3"))
    reranker_mode = reranker_mode or os.getenv("RERANKER_MODE", "none")
    candidate_k = candidate_k or int(os.getenv("RERANK_CANDIDATE_K", "15"))

    vectorstore = initialize_vectorstore(persist_directory)
    retriever = create_retriever(
        vectorstore,
        search_type=search_type,
        k=k,
        reranker_mode=reranker_mode,
        candidate_k=candidate_k,
    )
    graph = create_agent_graph()

    results: List[Dict[str, Any]] = []
    direct_metrics: List[Dict[str, Any]] = []
    agent_metrics: List[Dict[str, Any]] = []
    latencies: List[float] = []
    judge_scores: List[Dict[str, Any]] = []
    num_judge_failures = 0
    num_errors = 0

    for idx, example in enumerate(examples, start=1):
        print(f"[{idx}/{len(examples)}] {example.id}: {example.question[:80]}")

        result: Dict[str, Any] = {
            "id": example.id,
            "question": example.question,
            "expected_source": example.expected_source,
            "expected_page": example.expected_page,
            "reference_answer": example.reference_answer,
        }

        try:
            direct_docs = retriever.invoke(example.question)
        except Exception as exc:
            direct_docs = []
            result["direct_retrieval_error"] = str(exc)

        direct_result = compute_retrieval_metrics(
            direct_docs, example.expected_source, example.expected_page
        )
        direct_metrics.append(direct_result)
        result["retrieval_direct"] = direct_result

        generated_answer = ""
        agent_sources: List[Dict[str, Any]] = []
        error = None

        start = time.perf_counter()
        with CostTracker(model=agent_model) as cost:
            try:
                state = graph.invoke(build_initial_state(example.question))
                messages = state.get("messages", [])
                generated_answer = messages[-1].content if messages else ""
                agent_sources = extract_sources_from_messages(messages)
            except Exception as exc:
                error = str(exc)
                num_errors += 1
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

        agent_result = compute_retrieval_metrics(
            agent_sources, example.expected_source, example.expected_page
        )
        agent_metrics.append(agent_result)

        result.update(
            {
                "generated_answer": generated_answer,
                "error": error,
                "retrieval_agent": agent_result,
                "latency_ms": round(latency_ms, 1),
                "agent_tokens": {
                    "prompt": cost.prompt_tokens,
                    "completion": cost.completion_tokens,
                    "total": cost.total_tokens,
                },
                "agent_cost_usd": round(cost.cost_usd, 6),
            }
        )

        if skip_judge:
            result["judge"] = None
            result["judge_tokens"] = {"prompt": 0, "completion": 0, "total": 0}
            result["judge_cost_usd"] = 0.0
        else:
            context = "\n\n".join(s.get("snippet") or "" for s in agent_sources)
            with CostTracker(model=judge_model) as judge_cost:
                judge_result = judge_answer(
                    question=example.question,
                    reference_answer=example.reference_answer,
                    generated_answer=generated_answer,
                    retrieved_context=context,
                    model=judge_model,
                )

            result["judge"] = judge_result
            result["judge_tokens"] = {
                "prompt": judge_cost.prompt_tokens,
                "completion": judge_cost.completion_tokens,
                "total": judge_cost.total_tokens,
            }
            result["judge_cost_usd"] = round(judge_cost.cost_usd, 6)

            if judge_result is None:
                num_judge_failures += 1
            else:
                judge_scores.append(judge_result)

        results.append(result)

    agent_total_cost = sum(r["agent_cost_usd"] for r in results)
    judge_total_cost = sum(r["judge_cost_usd"] for r in results)
    agent_total_tokens = sum(r["agent_tokens"]["total"] for r in results)
    num_examples = len(examples)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _get_git_sha(),
        "eval_set_path": eval_set_path,
        "num_examples": num_examples,
        "num_errors": num_errors,
        "persist_directory": persist_directory,
        "k": k,
        "search_type": search_type,
        "reranker_mode": reranker_mode,
        "judge_model": None if skip_judge else judge_model,
        "skip_judge": skip_judge,
        "retrieval_direct": aggregate_retrieval_metrics(direct_metrics),
        "retrieval_agent": aggregate_retrieval_metrics(agent_metrics),
        "judge": _aggregate_judge_scores(judge_scores, num_judge_failures),
        "latency_ms": {
            "mean": round(mean(latencies), 1) if latencies else 0.0,
            "p50": round(_percentile(latencies, 50), 1),
            "p95": round(_percentile(latencies, 95), 1),
        },
        "agent_cost_usd_total": round(agent_total_cost, 6),
        "agent_cost_usd_mean": (round(agent_total_cost / num_examples, 6) if num_examples else 0.0),
        "agent_tokens_total": agent_total_tokens,
        "judge_cost_usd_total": round(judge_total_cost, 6),
    }

    write_run_report(output_dir, results, summary)
    return summary
