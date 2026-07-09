import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel


class EvalExample(BaseModel):
    id: str
    question: str
    reference_answer: str
    expected_source: str
    expected_page: Optional[int] = None
    source_chunk_id: Optional[str] = None
    generation_model: Optional[str] = None
    created_at: Optional[str] = None


def load_eval_set(path: str) -> List[EvalExample]:
    """Load eval examples from a JSONL file, skipping blank lines."""
    eval_path = Path(path)
    if not eval_path.exists():
        raise FileNotFoundError(f"Eval set not found: {path}")

    examples: List[EvalExample] = []
    with eval_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no} of {path}: {exc}") from exc
            examples.append(EvalExample(**data))

    return examples


def write_eval_set(path: str, examples: List[EvalExample]) -> None:
    """Write eval examples to a JSONL file, one JSON object per line."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for example in examples:
            f.write(example.model_dump_json())
            f.write("\n")
