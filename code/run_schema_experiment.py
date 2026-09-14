"""
code/run_schema_experiment.py — DATA-260 HW2 Part 4.3

Runs the stateful graph (code/agents_graph.py) 30 times on one fixed,
frozen input (reports/hw02/cases/schema_input.json), classifying each run
as one of:
    - valid_first_attempt
    - valid_after_1_retry
    - valid_after_2plus_retries
    - abandoned_at_ceiling

Writes raw per-run results to reports/hw02/raw/schema_raw.json/.csv and a
counts+latency summary to reports/hw02/raw/schema_summary.json.

Usage:
    python code/run_schema_experiment.py
    python code/run_schema_experiment.py --n 30 --turn-ceiling 6
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--turn-ceiling", type=int, default=6)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with open(INPUT_PATH) as f:
        case = json.load(f)

    print(f"Fixed input: '{case['title']}'")
    print(f"Running {args.n} runs at turn_ceiling={args.turn_ceiling} ...")

    runs = []
    for i in range(1, args.n + 1):
        print(f"  [run {i}/{args.n}] ...")
        result = ag.run_once(
            case["title"], case["content"],
            turn_ceiling=args.turn_ceiling, verbose=False,
        )
        runs.append({
            "run": i,
            "outcome": result["outcome"],
            "turn_count": result["turn_count"],
            "validation_retry_count": result["validation_retry_count"],
            "latency_ms": round(result["latency_ms"], 1),
            "final_tags": result["final"].get("tags", []),
            "final_summary": result["final"].get("summary", ""),
        })

    # Save raw results
    raw_json_path = RAW_DIR / "schema_raw.json"
    with open(raw_json_path, "w") as f:
        json.dump(runs, f, indent=2)

    raw_csv_path = RAW_DIR / "schema_raw.csv"
    with open(raw_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(runs[0].keys()))
        writer.writeheader()
        for row in runs:
            writer.writerow({**row, "final_tags": "|".join(row["final_tags"])})

    # Compute summary
    outcomes = ["valid_first_attempt", "valid_after_1_retry", "valid_after_2plus_retries", "abandoned_at_ceiling"]
    counts = {o: sum(1 for r in runs if r["outcome"] == o) for o in outcomes}
    latencies_by_outcome = {
        o: [r["latency_ms"] for r in runs if r["outcome"] == o] for o in outcomes
    }
    mean_latency_by_outcome = {
        o: (round(statistics.mean(lat), 1) if lat else None)
        for o, lat in latencies_by_outcome.items()
    }

    summary = {
        "n_runs": args.n,
        "turn_ceiling": args.turn_ceiling,
        "counts": counts,
        "mean_latency_ms_by_outcome": mean_latency_by_outcome,
        "overall_mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in runs), 1),
    }

    summary_path = RAW_DIR / "schema_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved raw JSON to {raw_json_path}")
    print(f"Saved raw CSV to {raw_csv_path}")
    print(f"Saved summary to {summary_path}")


if __name__ == "__main__":
    main()