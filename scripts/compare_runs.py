# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Compare metrics across test runs.

Reads output/*/metrics.json and prints a summary table.

Usage:
    uv run scripts/compare_runs.py
    uv run scripts/compare_runs.py --output-dir ./output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_runs(output_dir: Path) -> list[dict]:
    runs = []
    for metrics_path in sorted(output_dir.glob("*/metrics.json")):
        try:
            data = json.loads(metrics_path.read_text())
            data["_dir"] = metrics_path.parent.name
            runs.append(data)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: skipping {metrics_path}: {e}", file=sys.stderr)
    return runs


def print_table(runs: list[dict]) -> None:
    if not runs:
        print("No runs found.")
        return

    headers = ["Run", "Model", "Duration", "Rounds", "Tools", "Errors", "Pass"]
    rows = []
    for r in runs:
        run_id = r.get("run_id", r["_dir"])
        model = r.get("agent_model", "?")
        if "/" in model:
            model = model.split("/")[-1]
        duration = f"{r.get('total_duration_s', 0):.0f}s"
        rounds = str(r.get("total_rounds", "?"))
        tools = str(r.get("total_tool_calls", "?"))
        errors = str(r.get("total_tool_errors", "?"))
        passed = "PASS" if r.get("verification_passed") else "FAIL"
        rows.append([run_id, model, duration, rounds, tools, errors, passed])

    widths = [max(len(h), max(len(row[i]) for row in rows)) for i, h in enumerate(headers)]

    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep_line = "  ".join("-" * w for w in widths)
    print(header_line)
    print(sep_line)
    for row in rows:
        print("  ".join(val.ljust(w) for val, w in zip(row, widths)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "output",
        help="Directory containing run output folders (default: ./output)",
    )
    args = parser.parse_args()

    runs = load_runs(args.output_dir)
    print_table(runs)


if __name__ == "__main__":
    main()
