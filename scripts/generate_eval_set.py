#!/usr/bin/env python3
"""Generate an LLM-authored eval set from documents already ingested into the vectorstore.

Usage example:
python scripts/generate_eval_set.py \
    --persist-directory ./chroma_db \
    --output data/eval/eval_set.jsonl \
    --questions-per-doc 2
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an eval set (question/reference-answer pairs) from ingested docs."
    )
    parser.add_argument(
        "--persist-directory", default="./chroma_db", help="Vectorstore persistence directory."
    )
    parser.add_argument(
        "--output", default="data/eval/eval_set.jsonl", help="Output JSONL eval set path."
    )
    parser.add_argument(
        "--questions-per-doc",
        type=int,
        default=2,
        help="Max number of questions to generate per source document.",
    )
    parser.add_argument(
        "--min-chunk-chars",
        type=int,
        default=300,
        help="Skip chunks shorter than this many characters.",
    )
    parser.add_argument(
        "--model", default="gpt-4o-mini", help="OpenAI chat model used for question generation."
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for chunk sampling.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from src.config import validate_runtime_config
    from src.eval.generation import generate_eval_set

    ok, message = validate_runtime_config()
    if not ok:
        print(f"ERROR: {message}")
        return 1

    try:
        examples = generate_eval_set(
            persist_directory=args.persist_directory,
            output_path=args.output,
            questions_per_doc=args.questions_per_doc,
            min_chunk_chars=args.min_chunk_chars,
            model=args.model,
            seed=args.seed,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    return 0 if examples else 1


if __name__ == "__main__":
    raise SystemExit(main())
