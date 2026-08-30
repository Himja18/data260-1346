"""
run_nondeterminism_experiment.py — DATA-260 HW1 Part 3

Runs agents_demo.py's pipeline 20 times at temperature=0.7 and 20 times
at temperature=0.0 on a single fixed input, then computes:
  - number of distinct tag sets produced
  - tags that appeared in all 20 runs
  - tags that appeared in exactly 1 run
  - latency p50 / p95 / p99

Saves raw per-run results (tags + latency) as JSON and CSV.

Usage (run from the code/ folder):
    python run_nondeterminism_experiment.py
"""

import csv
import json
import statistics
import sys
from pathlib import Path

from agents_demo import run_pipeline

N_RUNS = 20
INPUT_FILE = Path(__file__).parent.parent / "reports" / "hw01" / "cases" / "nondeterminism_input.json"
RAW_DIR = Path(__file__).parent.parent / "reports" / "hw01" / "raw"


def percentile(data, pct):
    """Simple linear-interpolation percentile, no external deps needed."""
    if not data:
        return None
    data = sorted(data)
    k = (len(data) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)


def run_batch(title: str, content: str, temperature: float, n: int) -> list:
    """Run the pipeline n times at a fixed temperature, return list of
    {tags, summary, latency_ms} dicts."""
    results = []
    for i in range(n):
        print(f"  [temp={temperature}] run {i + 1}/{n}...", flush=True)
        result = run_pipeline(title, content, temperature, verbose=False)
        results.append({
            "run_index": i + 1,
            "temperature": temperature,
            "tags": result["final"]["tags"],
            "summary": result["final"]["summary"],
            "latency_ms": result["latency_ms"],
        })
    return results


def analyze(results: list) -> dict:
    """Compute the required Part 3 statistics for one temperature's batch."""
    tag_sets = [tuple(sorted(r["tags"])) for r in results]
    distinct_tag_sets = len(set(tag_sets))

    # Count how many runs each individual tag appeared in
    tag_run_counts = {}
    for r in results:
        for tag in set(r["tags"]):  # set() in case of accidental dupes within one run
            tag_run_counts[tag] = tag_run_counts.get(tag, 0) + 1

    n_runs = len(results)
    tags_in_all_runs = sorted([t for t, c in tag_run_counts.items() if c == n_runs])
    tags_in_exactly_one_run = sorted([t for t, c in tag_run_counts.items() if c == 1])

    latencies = [r["latency_ms"] for r in results]

    return {
        "n_runs": n_runs,
        "distinct_tag_sets": distinct_tag_sets,
        "tags_in_all_runs": tags_in_all_runs,
        "tags_in_exactly_one_run": tags_in_exactly_one_run,
        "latency_p50_ms": round(percentile(latencies, 50), 1),
        "latency_p95_ms": round(percentile(latencies, 95), 1),
        "latency_p99_ms": round(percentile(latencies, 99), 1),
    }


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: fixed input file not found at {INPUT_FILE}")
        print("Create it first (see reports/hw01/cases/nondeterminism_input.json).")
        sys.exit(1)

    with open(INPUT_FILE, "r") as f:
        data = json.load(f)
    title, content = data["title"], data["content"]

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fixed input: {title!r}")
    print(f"Running {N_RUNS} runs at temperature=0.7 ...")
    results_07 = run_batch(title, content, 0.7, N_RUNS)

    print(f"Running {N_RUNS} runs at temperature=0.0 ...")
    results_00 = run_batch(title, content, 0.0, N_RUNS)

    all_results = results_07 + results_00

    # Save raw results as JSON
    json_path = RAW_DIR / "nondeterminism_raw.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved raw JSON to {json_path}")

    # Save raw results as CSV
    csv_path = RAW_DIR / "nondeterminism_raw.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run_index", "temperature", "tags", "summary", "latency_ms"])
        for r in all_results:
            writer.writerow([r["run_index"], r["temperature"], "|".join(r["tags"]), r["summary"], r["latency_ms"]])
    print(f"Saved raw CSV to {csv_path}")

    # Analyze and print summary for each temperature
    summary_07 = analyze(results_07)
    summary_00 = analyze(results_00)

    print("\n=== TEMPERATURE 0.7 SUMMARY ===")
    print(json.dumps(summary_07, indent=2))

    print("\n=== TEMPERATURE 0.0 SUMMARY ===")
    print(json.dumps(summary_00, indent=2))

    # Save summary stats too, for easy reference when filling METRICS.md
    summary_path = RAW_DIR / "nondeterminism_summary.json"
    with open(summary_path, "w") as f:
        json.dump({"temp_0.7": summary_07, "temp_0.0": summary_00}, f, indent=2)
    print(f"\nSaved summary to {summary_path}")


if __name__ == "__main__":
    main()