import pytest

from src.eval.schema import EvalExample, load_eval_set, write_eval_set


def _example(i=1):
    return EvalExample(
        id=f"eval_{i:04d}",
        question="What is RAG?",
        reference_answer="Retrieval-augmented generation combines retrieval with generation.",
        expected_source="data/papers/sample.pdf",
        expected_page=2,
        source_chunk_id="abc123",
        generation_model="gpt-4o-mini",
        created_at="2026-07-07T12:00:00+00:00",
    )


def test_round_trip(tmp_path):
    path = tmp_path / "eval_set.jsonl"
    examples = [_example(1), _example(2)]

    write_eval_set(str(path), examples)
    loaded = load_eval_set(str(path))

    assert loaded == examples


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_eval_set(str(tmp_path / "missing.jsonl"))


def test_load_skips_blank_lines(tmp_path):
    path = tmp_path / "eval_set.jsonl"
    example = _example(1)
    path.write_text(f"\n{example.model_dump_json()}\n\n", encoding="utf-8")

    loaded = load_eval_set(str(path))

    assert loaded == [example]


def test_load_malformed_line_raises(tmp_path):
    path = tmp_path / "eval_set.jsonl"
    path.write_text("{not valid json\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_eval_set(str(path))


def test_write_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "eval_set.jsonl"
    write_eval_set(str(path), [_example(1)])

    assert path.exists()
