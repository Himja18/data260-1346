"""HW10 Part 4.3 - stage latency over 50 confirmed cache misses (+ cache-hit latency kept separate).

    python code/hw10/run_hw10_latency.py              # 50 misses, then 10 hits
    python code/hw10/run_hw10_latency.py --n 50 --hits 10

Questions: 5 templates x 10 incident codes INC-000601..INC-000650, none of which was ever asked before, so
the entity guard alone makes a cached answer impossible; every request is still CHECKED - its cache_lookup
span must say "miss", otherwise it is reported and excluded. Requests run one at a time and the next one starts
only after the evaluator finished the previous trace, so stages never compete for the one local Ollama.

End-to-end (cache-miss) = first span start (cache_lookup) -> last span end (evaluation).
Each stage's % = mean stage duration / mean end-to-end. Queue wait (total) = inbox + tasks + drafts + final hops.
Outputs: reports/hw10/latency_experiment.json, reports/hw10/raw/latency_per_trace.csv
"""
import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw10_config as cfg  # noqa: E402
from hw10_common import (  # noqa: E402
    QUEUE_STAGES,
    build_cache,
    spans_for,
    stage_durations,
    summarize,
    wait_for_evaluation,
)

TEMPLATES = ["What category is incident INC-{n:06d}?",
             "How many passengers were affected by incident INC-{n:06d}?",
             "Which transit line is incident INC-{n:06d} on?",
             "When was incident INC-{n:06d} reported?",
             "What is the route title for incident INC-{n:06d}?"]
ROWS = [("cache_lookup", "Cache lookup"), ("planner", "Planner"), ("writer", "Writer"), ("reviewer", "Reviewer"),
        ("queue_total", "Queue wait (total)"), ("evaluation", "Evaluation")]


def main() -> None:  # noqa: PLR0915
    """Run the experiment."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--hits", type=int, default=10)
    ap.add_argument("--first-code", type=int, default=601)
    ap.add_argument("--fake-agent", action="store_true", help="offline test only")
    args = ap.parse_args()
    log = cfg.setup_logging("hw10-latency")
    log.info("HW10 Part 4.3 latency experiment | %s | %s | n=%d", cfg.STUDENT_NAME, cfg.PREFIX, args.n)
    cache = build_cache(log, args.fake_agent)
    questions = [TEMPLATES[i % len(TEMPLATES)].format(n=args.first_code + i) for i in range(args.n)]

    traces, not_miss = [], []
    t_start = time.time()
    for i, q in enumerate(questions, 1):
        res = cache.ask(q)
        lookup = next((s for s in spans_for(res.trace_id) if s["stage"] == "cache_lookup"), None)
        if res.is_cached or not lookup or lookup["status"] != "miss":
            not_miss.append({"question": q, "trace_id": res.trace_id})
            log.warning("request %d was NOT a cache miss - excluded: %s", i, q)
            continue
        ev = wait_for_evaluation(res.trace_id, 300, log) if not args.fake_agent else None
        traces.append(res.trace_id)
        log.info("request %2d/%d MISS trace=%s user-facing %.0f ms | evaluation %s", i, args.n, res.trace_id,
                 res.latency_ms, f"{ev['duration_ms']:.0f} ms ({ev['status']})" if ev else "-")

    per_trace = []
    for tid in traces:
        d = stage_durations(spans_for(tid))
        d["trace_id"] = tid
        per_trace.append(d)
    complete = [d for d in per_trace if all(k in d for k in ("planner", "writer", "reviewer", "evaluation"))]
    e2e = [d["end_to_end"] for d in complete]
    mean_e2e = statistics.mean(e2e)
    table = []
    for key, label in ROWS:
        vals = [d[key] for d in complete]
        s = summarize(vals)
        s.update(stage=label, key=key, pct_of_e2e=round(100 * s["mean"] / mean_e2e, 1))
        table.append(s)
    queues = {q: summarize([d.get(q, 0.0) for d in complete]) for q in QUEUE_STAGES}
    accounted = sum(t["mean"] for t in table)
    result = {
        "n_requested": args.n, "n_confirmed_miss": len(traces), "n_complete": len(complete), "not_miss": not_miss,
        "end_to_end_ms": summarize(e2e), "user_facing_ms": summarize([d["user_facing"] for d in complete if "user_facing" in d]),
        "stages": table, "queue_hops": queues,
        "other_ms_mean": round(mean_e2e - accounted, 1),
        "other_pct": round(100 * (mean_e2e - accounted) / mean_e2e, 1),
        "dominant_stage": max(table, key=lambda t: t["mean"])["stage"], "trace_ids": traces,
        "duration_s": round(time.time() - t_start, 1),
    }

    hit_lat = []
    for q in questions[: args.hits]:
        res = cache.ask(q)
        if res.is_cached:
            hit_lat.append(res.latency_ms)
    result["cache_hit_ms"] = summarize(hit_lat) if hit_lat else None

    cfg.LATENCY_RESULTS.write_text(json.dumps(result, indent=2), encoding="utf-8")
    with open(cfg.RAW_DIR / "latency_per_trace.csv", "w", newline="", encoding="utf-8") as fh:
        keys = ["trace_id", "cache_lookup", *QUEUE_STAGES, "planner", "writer", "reviewer", "evaluation",
                "queue_total", "user_facing", "end_to_end"]
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(per_trace)
    log.info("==== stage latency over %d confirmed cache misses (end-to-end p50 %.0f ms, p95 %.0f ms) ====",
             len(complete), result["end_to_end_ms"]["p50"], result["end_to_end_ms"]["p95"])
    log.info("%-20s | %10s | %10s | %s", "Stage", "p50 (ms)", "p95 (ms)", "% of cache-miss end-to-end")
    for t in table:
        log.info("%-20s | %10.1f | %10.1f | %5.1f%%", t["stage"], t["p50"], t["p95"], t["pct_of_e2e"])
    log.info("%-20s | %10s | %10s | %5.1f%%  (client, DB facts, cache store, gaps)", "Other", "", "", result["other_pct"])
    for q, s in queues.items():
        log.info("   %-13s p50 %8.1f  p95 %8.1f", q, s["p50"], s["p95"])
    log.info("user-facing (to the final answer) p50 %.0f ms, p95 %.0f ms | cache-HIT latency (n=%d) p50 %s ms, p95 %s ms",
             result["user_facing_ms"]["p50"], result["user_facing_ms"]["p95"], len(hit_lat),
             result["cache_hit_ms"]["p50"] if hit_lat else "-", result["cache_hit_ms"]["p95"] if hit_lat else "-")
    log.info("dominant stage: %s | excluded (not a miss): %d | saved %s", result["dominant_stage"], len(not_miss),
             cfg.LATENCY_RESULTS.relative_to(cfg.REPO_ROOT))
    cache.agent.close()


if __name__ == "__main__":
    main()
