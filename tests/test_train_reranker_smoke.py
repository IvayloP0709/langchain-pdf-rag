import json

import pytest

from scripts.train_reranker import load_examples, train_reranker


def _write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record))
            f.write("\n")


_TRAIN_RECORDS = [
    {"query": "what is a cat", "doc_text": "a cat is a small domesticated feline", "label": 1},
    {"query": "what is a cat", "doc_text": "the stock market fell today", "label": 0},
    {"query": "what is python", "doc_text": "python is a programming language", "label": 1},
    {"query": "what is python", "doc_text": "bananas are yellow fruits", "label": 0},
]
_VAL_RECORDS = [
    {"query": "what is a dog", "doc_text": "a dog is a domesticated canine", "label": 1},
    {"query": "what is a dog", "doc_text": "quantum mechanics is a physics theory", "label": 0},
]


def test_load_examples_parses_jsonl(tmp_path):
    path = tmp_path / "train.jsonl"
    _write_jsonl(path, _TRAIN_RECORDS)

    examples = load_examples(str(path))

    assert examples == [
        ("what is a cat", "a cat is a small domesticated feline", 1.0),
        ("what is a cat", "the stock market fell today", 0.0),
        ("what is python", "python is a programming language", 1.0),
        ("what is python", "bananas are yellow fruits", 0.0),
    ]


def test_load_examples_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_examples("does/not/exist.jsonl")


@pytest.mark.slow
def test_train_reranker_runs_end_to_end_on_tiny_fixture(tmp_path):
    train_path = tmp_path / "train.jsonl"
    val_path = tmp_path / "val.jsonl"
    output_dir = tmp_path / "finetuned"
    _write_jsonl(train_path, _TRAIN_RECORDS)
    _write_jsonl(val_path, _VAL_RECORDS)

    result = train_reranker(
        train_path=str(train_path),
        val_path=str(val_path),
        output_dir=str(output_dir),
        epochs=1,
        batch_size=2,
    )

    assert result["epochs_trained"] == 1
    assert result["best_epoch"] == 1
    assert result["num_train_examples"] == len(_TRAIN_RECORDS)
    assert result["num_val_examples"] == len(_VAL_RECORDS)
    assert output_dir.is_dir()
    assert (output_dir / "config.json").exists()
    assert any(output_dir.glob("model.safetensors")) or any(output_dir.glob("pytorch_model.bin"))
