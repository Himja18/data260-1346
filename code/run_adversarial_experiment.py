"""
code/run_adversarial_experiment.py — DATA-260 HW2 Part 4.5

Runs one adversarial input (reports/hw02/cases/adversarial_input.json) 5
times and reports the observed rate of hitting the turn ceiling. The input
is designed to be hard to compress into a compliant schema (many distinct
sub-events crammed into one incident report), not to guarantee a
deterministic failure — so this script reports the observed rate honestly
rather than assuming it will always fail.

Writes raw results to reports/hw02/raw/adversarial_raw.json and a summary
to reports/hw02/raw/adversarial_summary.json.

Usage:
    python code/run_adversarial_experiment.py
    python code/run_adversarial_experiment.py --n 5 --turn-ceiling 6
"""

import argparse
import json
from pathlib import Path

import agents_graph as ag

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = REPO_ROOT / "reports" / "hw02" / "cases" / "adversarial_input.json"
RAW_DIR = REPO_ROOT / "reports" / "hw02" / "raw"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--turn-ceiling", type=int, default=6)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with open(INPUT_PATH) as f:
        case = json.load(f)

    print(f"Adversarial input: '{case['title']}'")
    print(f"Running {args.n} runs at turn_ceiling={args.turn_ceiling} ...")

    runs = []
    for i in range(1, args.n + 1):
        print(f"  [run {i}/{args.n}] ...")
        result = ag.run_once(case["title"], case["content"], turn_ceiling=args.turn_ceiling, verbose=False)
        runs.append({
            "run": i,
            "outcome": result["outcome"],
            "hit_ceiling": result["outcome"] == "abandoned_at_ceiling",
            "turn_count": result["turn_count"],
            "validation_retry_count": result["validation_retry_count"],
            "latency_ms": round(result["latency_ms"], 1),
            "final_tags": result["final"].get("tags", []),
            "final_summary": result["final"].get("summary", ""),
        })

    ceiling_hits = sum(1 for r in runs if r["hit_ceiling"])
    observed_rate = ceiling_hits / args.n

    summary = {
        "n_runs": args.n,
        "turn_ceiling": args.turn_ceiling,
        "ceiling_hits": ceiling_hits,
        "observed_ceiling_hit_rate": round(observed_rate, 3),
        "note": (
            "Rate reported as observed, not assumed deterministic. "
            "A hit rate below 4/5 does not mean the input failed to be "
            "adversarial -- it means the model's small size makes it "
            "inconsistent even on genuinely hard inputs; report the number "
            "as-is."
        ),
    }

    with open(RAW_DIR / "adversarial_raw.json", "w") as f:
        json.dump(runs, f, indent=2)
    with open(RAW_DIR / "adversarial_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved raw JSON to {RAW_DIR / 'adversarial_raw.json'}")
    print(f"Saved summary to {RAW_DIR / 'adversarial_summary.json'}")


if __name__ == "__main__":
    main()