import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _flatten(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    items: Dict[str, Any] = {}
    for key, value in d.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.update(_flatten(value, new_key, sep))
        else:
            items[new_key] = value
    return items


def _append_history(history_path: Path, flat_summary: Dict[str, Any]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)

    if not history_path.exists():
        with history_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(flat_summary.keys()))
            writer.writeheader()
            writer.writerow(flat_summary)
        return

    with history_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_fieldnames = list(reader.fieldnames or [])
        existing_rows = list(reader)

    merged_fieldnames = list(existing_fieldnames)
    for key in flat_summary:
        if key not in merged_fieldnames:
            merged_fieldnames.append(key)

    if merged_fieldnames == existing_fieldnames:
        with history_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=merged_fieldnames)
            writer.writerow(flat_summary)
        return

    tmp_path = history_path.with_suffix(history_path.suffix + ".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=merged_fieldnames)
        writer.writeheader()
        for row in existing_rows:
            writer.writerow(row)
        writer.writerow(flat_summary)
    os.replace(tmp_path, history_path)


def _print_summary(summary: Dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("EVAL RUN SUMMARY")
    print("=" * 60)
    for key, value in summary.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for sub_key, sub_value in value.items():
                print(f"  {sub_key}: {sub_value}")
        else:
            print(f"{key}: {value}")
    print("=" * 60)


def write_run_report(
    output_dir: str, results: List[Dict[str, Any]], summary: Dict[str, Any]
) -> Path:
    """
    Write a full eval run report: results.jsonl + summary.json + summary.csv under a
    timestamped run directory, and append a flattened summary row to a shared
    history.csv so runs can be diffed over time.

    Returns the path to the created run directory.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(output_dir) / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    results_path = run_dir / "results.jsonl"
    with results_path.open("w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result))
            f.write("\n")

    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    flat_summary = _flatten(summary)

    csv_path = run_dir / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(flat_summary.keys()))
        writer.writeheader()
        writer.writerow(flat_summary)

    _append_history(Path(output_dir) / "history.csv", flat_summary)
    _print_summary(summary)

    return run_dir
