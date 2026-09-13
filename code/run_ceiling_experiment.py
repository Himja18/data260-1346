"""
code/run_ceiling_experiment.py — DATA-260 HW2 Part 4.4

Compares turn ceilings of 2 and 10 over 20 runs each, using the same frozen
input and model settings. Reports completion rate and mean latency for each
ceiling, then prints a recommendation for deployment based on the data.

Writes raw results to reports/hw02/raw/ceiling_raw.json/.csv and a summary
to reports/hw02/raw/ceiling_summary.json.

Usage:
    python code/run_ceiling_experiment.py
    python code/run_ceiling_experiment.py --n 20
"""

import argparse
import csv
import json
import statistics
from pathlib import Path

import agents_graph as ag

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = REPO_ROOT / "reports" / "hw02" / "cases" / "schema_input.json"
RAW_DIR = REPO_ROOT / "reports" / "hw02" / "raw"


def run_batch(case: dict, ceiling: int, n: int) -> list[dict]:
    runs = []
    for i in range(1, n + 1):
        print(f"  [ceiling={ceiling}] run {i}/{n} ...")
        result = ag.run_once(case["title"], case["content"], turn_ceiling=ceiling, verbose=False)
        runs.append({
            "ceiling": ceiling,
            "run": i,
            "outcome": result["outcome"],
            "completed": result["outcome"] != "abandoned_at_ceiling",
            "turn_count": result["turn_count"],
            "latency_ms": round(result["latency_ms"], 1),
        })
    return runs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with open(INPUT_PATH) as f:
        case = json.load(f)

    print(f"Fixed input: '{case['title']}'")

    all_runs = []
    for ceiling in (2, 10):
        all_runs.extend(run_batch(case, ceiling, args.n))

    raw_json_path = RAW_DIR / "ceiling_raw.json"
    with open(raw_json_path, "w") as f:
        json.dump(all_runs, f, indent=2)

    raw_csv_path = RAW_DIR / "ceiling_raw.csv"
    with open(raw_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_runs[0].keys()))
        writer.writeheader()
        writer.writerows(all_runs)

    summary = {}
    for ceiling in (2, 10):
        subset = [r for r in all_runs if r["ceiling"] == ceiling]
        completed = [r for r in subset if r["completed"]]
        summary[f"ceiling_{ceiling}"] = {
            "n_runs": len(subset),
            "completion_rate": round(len(completed) / len(subset), 3),
            "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in subset), 1),
            "mean_latency_ms_completed_only": (
                round(statistics.mean(r["latency_ms"] for r in completed), 1) if completed else None
            ),
        }

    summary_path = RAW_DIR / "ceiling_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved raw JSON to {raw_json_path}")
    print(f"Saved raw CSV to {raw_csv_path}")
    print(f"Saved summary to {summary_path}")


if __name__ == "__main__":
    main()