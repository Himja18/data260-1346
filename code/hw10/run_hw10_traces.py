"""HW10 Part 4.2 - capture the three required traces: cache miss (success), cache hit, failed.

    python code/hw10/run_hw10_traces.py

Needs: Redis, MySQL, Kafka + planner/writer/reviewer (HW8), and evaluator.py running.
  1. cache MISS  - a new question goes cache_lookup -> Kafka agents -> final -> evaluation (success)
  2. cache HIT   - the same question again, answered from Redis (no Kafka spans)
  3. FAILED      - a new question sent with inject_fault="writer": the Writer raises on every attempt, the
                   message is dead-lettered after 3 attempts, the client times out and the evaluator records
                   an error that names the failing stage.
The three trace_ids are saved to reports/hw10/trace_examples.json for the dashboard and the report.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw10_config as cfg  # noqa: E402
from hw10_common import build_cache, spans_for, wait_for_evaluation  # noqa: E402

MISS_Q = "What is the route title for incident INC-000512?"
FAIL_Q = "How many passengers were affected by incident INC-000513?"


def show(log, title: str, trace_id: str) -> list[dict]:  # noqa: ANN001
    """Log the trace in stage order."""
    sp = spans_for(trace_id)
    log.info("---- %s trace %s (%d spans) ----", title, trace_id, len(sp))
    for s in sp:
        log.info("   %-13s %-8s %s -> %s  %8.1f ms %s", s["stage"], s["status"], s["start"][11:23], s["end"][11:23],
                 s["duration_ms"], f"ERROR: {s['error']}" if s.get("error") else "")
    return sp


def main() -> None:
    """Capture and save the three traces."""
    log = cfg.setup_logging("hw10-traces")
    log.info("HW10 Part 4.2 trace examples | %s | %s", cfg.STUDENT_NAME, cfg.PREFIX)
    cache = build_cache(log)
    examples = {}

    miss = cache.ask(MISS_Q)
    if miss.is_cached:
        raise SystemExit("the miss question was already cached - change MISS_Q to a new incident code")
    wait_for_evaluation(miss.trace_id, 300, log)
    examples["cache_miss"] = {"trace_id": miss.trace_id, "question": MISS_Q, "latency_ms": miss.latency_ms}
    show(log, "CACHE MISS (success)", miss.trace_id)

    hit = cache.ask(MISS_Q)
    examples["cache_hit"] = {"trace_id": hit.trace_id, "question": MISS_Q, "latency_ms": hit.latency_ms,
                             "is_cached": hit.is_cached, "similarity": hit.similarity}
    show(log, "CACHE HIT", hit.trace_id)

    t0 = time.time()
    try:
        cache.ask(FAIL_Q, inject_fault="writer", agent_timeout_s=90)
        raise SystemExit("expected the failed trace to fail")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - AgentTimeout from the client
        log.info("client error after %.1f s: %s", time.time() - t0, exc)
    failed_id = None
    for s in reversed(spans_for_all()):
        if s["stage"] == "request" and s["status"] == "error" and s.get("query") == FAIL_Q:
            failed_id = s["trace_id"]
            break
    wait_for_evaluation(failed_id, 120, log)
    sp = show(log, "FAILED", failed_id)
    failing = next((s for s in sp if s["status"] == "error" and s["stage"] not in ("request", "evaluation")), None)
    examples["failed"] = {"trace_id": failed_id, "question": FAIL_Q, "inject_fault": "writer",
                          "failing_stage": failing["stage"] if failing else None,
                          "error": failing.get("error") if failing else None}
    log.info("failing stage: %s | error: %s", examples["failed"]["failing_stage"], examples["failed"]["error"])

    cfg.TRACE_EXAMPLES.write_text(json.dumps(examples, indent=2), encoding="utf-8")
    log.info("saved %s: %s", cfg.TRACE_EXAMPLES.relative_to(cfg.REPO_ROOT),
             {k: v["trace_id"] for k, v in examples.items()})
    cache.agent.close()


def spans_for_all() -> list[dict]:
    """All spans."""
    from tracing import load_spans
    return load_spans()


if __name__ == "__main__":
    main()
