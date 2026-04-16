#!/usr/bin/env python3
import json
from pathlib import Path


def main() -> int:
    eval_path = Path("data/eval/eval_set.jsonl")
    if not eval_path.exists():
        print("ERROR: Missing data/eval/eval_set.jsonl.")
        print("Please create the eval set first.")
        return 1

    total = 0
    with eval_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            json.loads(line)
            total += 1

    print(f"Loaded {total} eval examples.")


if __name__ == "__main__":
    raise SystemExit(main())
