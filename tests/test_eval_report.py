import csv
import json

from src.eval.report import write_run_report


def test_write_run_report_creates_expected_files(tmp_path):
    results = [{"id": "eval_0001", "hit": True}]
    summary = {"num_examples": 1, "retrieval_direct": {"hit_rate": 1.0}}

    run_dir = write_run_report(str(tmp_path), results, summary)

    assert run_dir.parent == tmp_path
    assert (run_dir / "results.jsonl").exists()
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "summary.csv").exists()

    lines = (run_dir / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0]) == results[0]

    loaded_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert loaded_summary == summary


def test_write_run_report_appends_history(tmp_path):
    summary_a = {"num_examples": 1, "retrieval_direct": {"hit_rate": 1.0}}
    summary_b = {"num_examples": 2, "retrieval_direct": {"hit_rate": 0.5}}

    write_run_report(str(tmp_path), [], summary_a)
    write_run_report(str(tmp_path), [], summary_b)

    history_path = tmp_path / "history.csv"
    with history_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["num_examples"] == "1"
    assert rows[1]["num_examples"] == "2"
    assert rows[0]["retrieval_direct.hit_rate"] == "1.0"
