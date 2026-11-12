"""HW10 Part 2 - pipeline evaluator: joins Planner plan, Writer draft and Reviewer final by correlation_id.

    python code/hw10/evaluator.py                     # service: consume s1346_tasks/_drafts/_final/_dead_letter
    python code/hw10/evaluator.py --trace-id <id>     # one trace, loaded from the topics (replay)

For every trace it scores, on 1-5 with GEval (judge.py):
    plan_quality        Planner plan      (score + reason)
    writer_helpfulness  Writer draft      (score + trace_id)
    final_helpfulness   Reviewer final    (score + final answer)
    improvement         final_helpfulness of the final vs of the draft (both scores, difference, interpretation)
and writes one line to reports/hw10/eval_results.jsonl plus an `evaluation` span (trace_id = correlation_id).

Bounds - nothing can hang the run:
    malformed message (bad JSON, no correlation_id)  -> logged and skipped
    judge unavailable / slow                          -> each call times out after JUDGE_TIMEOUT_S (status error)
    trace never completes                             -> error span after EVAL_WAIT_S
    stage dead-lettered (s1346_dead_letter)           -> error span immediately, naming the failing stage
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw10_config as cfg  # noqa: E402
from judge import judge_settings, score  # noqa: E402
from kafka_common import decode, make_consumer, now_iso, read_topic, short  # noqa: E402
from tracing import write_span  # noqa: E402

cfg8 = cfg.cfg8


def _meta(msg: Any) -> dict:
    """Kafka metadata kept with the content so the evaluation can be reproduced."""
    if isinstance(msg, dict) and "kafka" in msg:
        return msg["kafka"]
    ts = msg.timestamp()[1] if msg.timestamp() else None
    return {"topic": msg.topic(), "partition": msg.partition(), "offset": msg.offset(), "timestamp_ms": ts}


def interpret(draft: str, final: str, reviewer_status: Optional[str], d: Optional[int], f: Optional[int]) -> str:
    """Plain-language reading of the draft -> final comparison (no forced positive conclusion)."""
    same = draft.strip() == final.strip()
    if d is None or f is None:
        return "Not comparable: at least one judge call failed."
    if same:
        base = (f"The Reviewer returned the draft unchanged (status={reviewer_status}); it approves or rejects but "
                f"does not rewrite, so the final cannot improve on the draft.")
        return base + (" Both judge scores are equal, as expected." if d == f else
                       f" The scores still differ by {f - d:+d}: that is judge noise on identical text, not an "
                       f"improvement or a regression.")
    if f > d:
        return f"The final answer scored {f - d:+d} higher than the draft: the Reviewer stage improved it."
    if f < d:
        return f"The final answer scored {f - d:+d} lower than the draft: the Reviewer stage made it worse."
    return "The final answer differs from the draft but scored the same: no measurable improvement."


def evaluate_trace(corr: str, plan_msg: Optional[dict], draft_msg: dict, final_msg: dict, log: Any,
                   meta: dict, started: Optional[float] = None) -> dict:
    """Score one trace, write the result line and the evaluation span."""
    t0 = started or time.time()
    question = str(draft_msg.get("question") or (plan_msg or {}).get("question") or "")
    steps = (plan_msg or {}).get("plan") or draft_msg.get("plan") or []
    plan_text = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    draft = str(draft_msg.get("draft") or "")
    final = str(final_msg.get("answer") or "")
    status = final_msg.get("status")
    log.info("EVALUATE trace=%s (reviewer=%s) question=%s", corr, status, short(question.split("\n")[0], 90))
    plan_s = score("plan_quality", question, plan_text)
    writer_s = score("writer_helpfulness", question, draft)
    final_s = score("final_helpfulness", question, final)
    draft_as_final = score("final_helpfulness", question, draft)      # same metric on the draft, for 2.2 #4
    d, f = draft_as_final["score"], final_s["score"]
    improvement = {"draft_score": d, "final_score": f, "difference": None if d is None or f is None else f - d,
                   "identical_text": draft.strip() == final.strip(), "interpretation": interpret(draft, final, status, d, f)}
    errors = [f"{s['metric']}: {s['error']}" for s in (plan_s, writer_s, final_s, draft_as_final) if s["status"] != "ok"]
    end = time.time()
    result = {
        "trace_id": corr, "evaluated_at": now_iso(), "status": "ok" if not errors else "error",
        "error": "; ".join(errors) or None, "duration_ms": round((end - t0) * 1000, 1),
        "judge": judge_settings(),
        "inputs": {"question": question, "plan": steps, "draft": draft, "final_answer": final,
                   "reviewer_status": status, "planned_by": (plan_msg or {}).get("planned_by"),
                   "written_by": draft_msg.get("written_by"), "kafka": meta},
        "plan_quality": {"score": plan_s["score"], "score_raw": plan_s["score_raw"], "reason": plan_s["reason"],
                         "status": plan_s["status"], "error": plan_s["error"]},
        "writer_helpfulness": {"score": writer_s["score"], "score_raw": writer_s["score_raw"], "trace_id": corr,
                               "reason": writer_s["reason"], "status": writer_s["status"], "error": writer_s["error"]},
        "final_helpfulness": {"score": final_s["score"], "score_raw": final_s["score_raw"], "final_answer": final,
                              "reason": final_s["reason"], "status": final_s["status"], "error": final_s["error"]},
        "draft_scored_as_final": {"score": d, "score_raw": draft_as_final["score_raw"],
                                  "reason": draft_as_final["reason"]},
        "improvement": improvement,
    }
    cfg.ensure_dirs()
    with open(cfg.EVAL_RESULTS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    write_span(corr, "evaluation", t0, end, result["status"], "evaluator", error=result["error"],
               plan_quality=plan_s["score"], writer_helpfulness=writer_s["score"],
               final_helpfulness=final_s["score"], improvement=improvement["difference"])
    log.info("SCORES trace=%s plan=%s writer=%s final=%s draft-as-final=%s diff=%s (%.1f s)%s", corr,
             plan_s["score"], writer_s["score"], f, d, improvement["difference"], (end - t0),
             f" ERRORS: {result['error']}" if errors else "")
    return result


def evaluation_failed(corr: str, error: str, log: Any, started: float, failing_stage: Optional[str] = None) -> None:
    """Upstream failure or incomplete trace: an error span and a result line, never a hang."""
    end = time.time()
    write_span(corr, "evaluation", started, end, "error", "evaluator", error=error, failing_stage=failing_stage)
    with open(cfg.EVAL_RESULTS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"trace_id": corr, "evaluated_at": now_iso(), "status": "error", "error": error,
                             "failing_stage": failing_stage, "duration_ms": round((end - started) * 1000, 1)}) + "\n")
    log.warning("EVALUATION ERROR trace=%s stage=%s: %s", corr, failing_stage, error)


def run_service(log: Any) -> None:
    """Consume tasks/drafts/final/dead_letter, join by correlation_id, evaluate when final arrives."""
    consumer = make_consumer(cfg.EVAL_GROUP, f"{cfg.PREFIX}-evaluator", auto_commit=True, offset_reset="latest")
    consumer.subscribe(cfg.EVAL_TOPICS)
    log.info("evaluator ready: %s | group=%s | judge=%s | wait=%ss", cfg.EVAL_TOPICS, cfg.EVAL_GROUP,
             judge_settings()["judge_model"], cfg.EVAL_WAIT_S)
    pending: dict[str, dict] = {}
    try:
        while True:
            msg = consumer.poll(1.0)
            now = time.time()
            for corr in [c for c, p in pending.items() if now - p["first_seen"] > cfg.EVAL_WAIT_S]:
                p = pending.pop(corr)
                missing = [k for k in ("plan", "draft", "final") if k not in p]
                evaluation_failed(corr, f"incomplete trace after {cfg.EVAL_WAIT_S:.0f}s: missing {', '.join(missing)}",
                                  log, p["first_seen"], failing_stage={"plan": "planner", "draft": "writer",
                                                                       "final": "reviewer"}[missing[0]])
            if msg is None or msg.error():
                continue
            try:
                value = decode(msg.value())
                corr = value.get("correlation_id") if isinstance(value, dict) else None
            except ValueError:
                value, corr = None, None
            if not corr:
                log.warning("MALFORMED message on %s@%s skipped (no JSON object with correlation_id)",
                            msg.topic(), msg.offset())
                continue
            p = pending.setdefault(corr, {"first_seen": now, "meta": {}})
            if msg.topic() == cfg8.DEAD_LETTER_TOPIC:
                pending.pop(corr, None)
                stage = str(value.get("source_agent", "?")).split("-")[0]
                evaluation_failed(corr, f"{stage} dead-lettered after {value.get('attempts')} attempts: "
                                        f"{value.get('error')}", log, now, failing_stage=stage)
                continue
            kind = {cfg8.TASKS_TOPIC: "plan", cfg8.DRAFTS_TOPIC: "draft", cfg8.FINAL_TOPIC: "final"}[msg.topic()]
            p[kind] = value
            p["meta"][kind] = _meta(msg)
            if kind == "final":
                p["final_received"] = now
            if "final" in p and "draft" in p:
                pending.pop(corr)
                evaluate_trace(corr, p.get("plan"), p["draft"], p["final"], log, p["meta"], p["final_received"])
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        log.info("evaluator stopping")


def replay(trace_id: str, log: Any) -> Optional[dict]:
    """Load the three messages for one trace from the topics and evaluate them (no service needed)."""
    found: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    for kind, topic in (("plan", cfg8.TASKS_TOPIC), ("draft", cfg8.DRAFTS_TOPIC), ("final", cfg8.FINAL_TOPIC)):
        for rec in read_topic(topic, idle_s=3.0, max_s=60.0):
            v = rec["value"]
            if isinstance(v, dict) and v.get("correlation_id") == trace_id:
                found[kind] = v
                meta[kind] = {"topic": topic, "partition": rec["partition"], "offset": rec["offset"]}
    if "draft" not in found or "final" not in found:
        evaluation_failed(trace_id, f"replay: missing {[k for k in ('plan', 'draft', 'final') if k not in found]}",
                          log, time.time())
        return None
    return evaluate_trace(trace_id, found.get("plan"), found["draft"], found["final"], log, meta)


def main() -> None:
    """CLI."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace-id")
    args = ap.parse_args()
    log = cfg.setup_logging("evaluator")
    if args.trace_id:
        replay(args.trace_id, log)
    else:
        run_service(log)


if __name__ == "__main__":
    main()
