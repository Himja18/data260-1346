"""HW10 Part 4 - structured JSON spans, one line per stage, keyed by trace_id (= the HW8 correlation_id).

Every process (cache ingress, Planner, Writer, Reviewer, evaluator) appends to the same file:
    reports/hw10/spans.jsonl          (override with HW10_SPANS_FILE)

A span:
    {"trace_id", "stage", "component", "start", "end" (ISO, local tz), "start_ms", "end_ms",
     "duration_ms", "status" (ok | hit | miss | error), "error" (only when status == error), ...attrs}

Stages on the request path:
    request (root, at the ingress) -> cache_lookup (status hit|miss)
    -> queue_inbox -> planner -> queue_tasks -> writer -> queue_drafts -> reviewer -> queue_final
    -> evaluation
queue_* spans run from the producer's Kafka CreateTime to the moment the consumer received the record.
No second identifier is created: the correlation_id generated at the ingress is the trace_id everywhere.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SPANS_FILE = Path(os.getenv("HW10_SPANS_FILE", str(REPO_ROOT / "reports" / "hw10" / "spans.jsonl")))


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="milliseconds")


def write_span(trace_id: Optional[str], stage: str, start: float, end: float, status: str = "ok",
               component: str = "", error: Optional[str] = None, **attrs: Any) -> Optional[dict]:
    """Append one span (start/end are epoch seconds). Spans without a trace_id are not written."""
    if not trace_id:
        return None
    span = {"trace_id": trace_id, "stage": stage, "component": component,
            "start": _iso(start), "end": _iso(end), "start_ms": round(start * 1000, 1),
            "end_ms": round(end * 1000, 1), "duration_ms": round((end - start) * 1000, 1), "status": status}
    if error:
        span["error"] = str(error)[:500]
    span.update({k: v for k, v in attrs.items() if v is not None})
    SPANS_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(span, default=str, ensure_ascii=False) + "\n"
    with open(SPANS_FILE, "a", encoding="utf-8") as fh:     # O_APPEND: one write per line
        fh.write(line)
    return span


def queue_span(trace_id: Optional[str], topic: str, kafka_timestamp: Any, received: float, component: str,
               **attrs: Any) -> Optional[dict]:
    """Queue wait for one Kafka hop: producer CreateTime -> consumer receive. topic s1346_tasks -> queue_tasks."""
    try:
        ts_type, ts_ms = kafka_timestamp
    except (TypeError, ValueError):
        return None
    if not ts_ms or ts_ms <= 0:
        return None
    stage = "queue_" + topic.split("_", 1)[-1]
    return write_span(trace_id, stage, ts_ms / 1000.0, max(received, ts_ms / 1000.0), "ok", component,
                      topic=topic, timestamp_type=ts_type, **attrs)


def load_spans(path: Optional[Path] = None) -> list[dict]:
    """All spans (bad lines skipped)."""
    p = Path(path or SPANS_FILE)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def now() -> float:
    """Epoch seconds."""
    return time.time()
