#!/usr/bin/env python3
"""Run the eval set through the agent and write a scored run report.

Usage example:
python scripts/evaluate.py --eval-set data/eval/eval_set.jsonl --limit 5
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the eval set through the agent, score it, and write a run report."
    )
    parser.add_argument(
        "--eval-set", default="data/eval/eval_set.jsonl", help="Path to the eval set JSONL."
    )
    parser.add_argument(
        "--persist-directory", default="./chroma_db", help="Vectorstore persistence directory."
    )
    parser.add_argument(
        "--k", type=int, default=None, help="Retrieval k (defaults to RETRIEVAL_K)."
    )
    parser.add_argument(
        "--judge-model", default="gpt-4o-mini", help="OpenAI chat model used for LLM-as-judge."
    )
    parser.add_argument(
        "--output-dir", default="data/eval/runs", help="Directory to write the run report under."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Only evaluate the first N examples."
    )
    parser.add_argument(
        "--skip-judge", action="store_true", help="Skip LLM-as-judge answer quality scoring."
    )
    parser.add_argument(
        "--search-type",
        choices=["similarity", "mmr"],
        default="similarity",
        help="Retrieval search type for the direct-retrieval metric.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from src.config import validate_runtime_config
    from src.eval.runner import run_evaluation

    ok, message = validate_runtime_config()
    if not ok:
        print(f"ERROR: {message}")
        return 1

    try:
        run_evaluation(
            eval_set_path=args.eval_set,
            persist_directory=args.persist_directory,
            k=args.k,
            judge_model=args.judge_model,
            output_dir=args.output_dir,
            limit=args.limit,
            skip_judge=args.skip_judge,
            search_type=args.search_type,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
