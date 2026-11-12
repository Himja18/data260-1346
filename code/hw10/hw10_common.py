"""HW10 helpers shared by the trace and latency runners: cache wiring, waiting for evaluation, span maths."""
import statistics
import time
from typing import Any, Optional

import hw10_config as cfg
from tracing import load_spans

QUEUE_STAGES = ("queue_inbox", "queue_tasks", "queue_drafts", "queue_final")
STAGE_ORDER = ["request", "cache_lookup", "queue_inbox", "planner", "queue_tasks", "writer", "queue_drafts",
               "reviewer", "queue_final", "evaluation"]


def build_cache(log: Any, fake_agent: bool = False):  # noqa: ANN201
    """The HW9 semantic cache (threshold 0.95 + entity guard, the HW9 shipping choice) over the HW8 pipeline."""
    from run_hw09_part2 import build_cache as b9
    return b9(log, 0.95, fake_agent)


def spans_for(trace_id: str) -> list[dict]:
    """Spans of one trace in stage order (then start time)."""
    sp = [s for s in load_spans() if s.get("trace_id") == trace_id]
    return sorted(sp, key=lambda s: (s["start_ms"], STAGE_ORDER.index(s["stage"]) if s["stage"] in STAGE_ORDER else 99))


def wait_for_evaluation(trace_id: str, timeout_s: float, log: Any) -> Optional[dict]:
    """Block until the evaluator wrote the `evaluation` span for this trace (bounded)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for s in reversed(load_spans()):
            if s.get("trace_id") == trace_id and s.get("stage") == "evaluation":
                return s
        time.sleep(1.0)
    log.warning("no evaluation span for %s within %.0fs - is evaluator.py running?", trace_id, timeout_s)
    return None


def stage_durations(spans: list[dict]) -> dict:
    """Per-trace durations (ms) for the required stages + end-to-end."""
    by = {}
    for s in spans:
        by.setdefault(s["stage"], []).append(s)
    d = {}
    for st in ("cache_lookup", "planner", "writer", "reviewer", "evaluation", *QUEUE_STAGES):
        if st in by:
            d[st] = sum(x["duration_ms"] for x in by[st])
    d["queue_total"] = sum(d.get(q, 0.0) for q in QUEUE_STAGES)
    start = min(s["start_ms"] for s in spans)
    end = max(s["end_ms"] for s in spans)
    d["end_to_end"] = end - start
    if "request" in by:
        d["user_facing"] = by["request"][0]["duration_ms"]
    return d


def pct(values: list[float], q: float) -> float:
    """Linear-interpolated percentile (same as numpy's default)."""
    v = sorted(values)
    if not v:
        return float("nan")
    k = (len(v) - 1) * q / 100
    f = int(k)
    c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def summarize(values: list[float]) -> dict:
    """p50 / p95 / mean."""
    return {"p50": round(pct(values, 50), 1), "p95": round(pct(values, 95), 1), "mean": round(statistics.mean(values), 1),
            "n": len(values)}


__all__ = ["cfg", "QUEUE_STAGES", "STAGE_ORDER", "build_cache", "spans_for", "wait_for_evaluation",
           "stage_durations", "pct", "summarize"]
