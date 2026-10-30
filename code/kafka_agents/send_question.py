"""HW8 Part 2 - send a question to s1346_inbox and wait for the final answer on s1346_final.

    python code/kafka_agents/send_question.py
    python code/kafka_agents/send_question.py --question "..." --timeout 300

Prints the message journey (inbox -> tasks -> drafts -> final) from the shared trace and
the final JSON, and appends the journey to reports/hw08/raw/part2_journeys.json.
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1])]

from confluent_kafka import Consumer  # noqa: E402

import hw08_config as cfg  # noqa: E402
from kafka_common import (  # noqa: E402
    assign_at_end,
    decode,
    encode,
    make_producer,
    new_correlation_id,
    now_iso,
    setup_logging,
    short,
    trace,
)

DEFAULT_QUESTION = ("My Line 22 trolley bus broke down at Fillmore and Geary and we waited 25 minutes. "
                    "How do I report it and which incident category applies?")


def journey(corr: str) -> list[dict]:
    """All trace events for one correlation_id, oldest first."""
    rows = []
    if cfg.TRACE_FILE.exists():
        for line in cfg.TRACE_FILE.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("correlation_id") == corr:
                rows.append(rec)
    return sorted(rows, key=lambda r: r["ts"])


def main() -> None:
    """Send one question and wait for its final answer."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--no-wait", action="store_true")
    args = ap.parse_args()
    log = setup_logging("send_question")

    final_reader = Consumer({"bootstrap.servers": cfg.KAFKA_BOOTSTRAP, "enable.auto.commit": False,
                             "group.id": f"{cfg.PREFIX}_asker_{uuid.uuid4().hex[:8]}"})
    assign_at_end(final_reader, cfg.FINAL_TOPIC)          # only finals produced after this point

    corr = new_correlation_id()
    message = {"correlation_id": corr, "question": args.question, "asked_by": cfg.STUDENT_NAME,
               "sent_at": now_iso(), "trace": [{"stage": "you", "instance": "send_question", "at": now_iso()}]}
    producer = make_producer(f"{cfg.PREFIX}-send-question")
    started = time.time()
    producer.produce(cfg.INBOX_TOPIC, key=corr.encode(), value=encode(message))
    producer.flush(10)
    log.info("SENT -> %s corr=%s message=%s", cfg.INBOX_TOPIC, corr, short(message))
    trace("send_question", "agent_sent", corr, topic=cfg.INBOX_TOPIC)
    if args.no_wait:
        return

    final = None
    while time.time() - started < args.timeout and final is None:
        msg = final_reader.poll(1.0)
        if msg is None or msg.error():
            continue
        try:
            value = decode(msg.value())
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("correlation_id") == corr:
            final = value
            log.info("RECEIVED <- %s[%d]@%d corr=%s", msg.topic(), msg.partition(), msg.offset(), corr)
    final_reader.close()
    if final is None:
        log.error("no final message for corr=%s within %.0fs - are planner/writer/reviewer running?", corr, args.timeout)
        raise SystemExit(1)
    trace("send_question", "agent_received", corr, topic=cfg.FINAL_TOPIC)

    elapsed = time.time() - started
    log.info("---- message journey for corr=%s (%.1fs end to end)", corr, elapsed)
    events = journey(corr)
    for rec in events:
        verb = {"agent_sent": "SENT ->", "agent_received": "RECEIVED <-"}.get(rec["event"], rec["event"])
        where = rec.get("topic", "")
        if "partition" in rec:
            where += f"[{rec['partition']}]@{rec.get('offset')}"
        log.info("   %s | %-14s | %-11s %s", rec["at"][11:23], rec["component"], verb, where)
    log.info("---- final JSON from %s:\n%s", cfg.FINAL_TOPIC, json.dumps(final, indent=2, ensure_ascii=False))
    log.info("correlation_id preserved end to end: %s | status=%s", final.get("correlation_id") == corr,
             final.get("status"))

    cfg.ensure_dirs()
    path = cfg.RAW_DIR / "part2_journeys.json"
    try:
        saved = json.loads(path.read_text()) if path.exists() else []
    except json.JSONDecodeError:
        saved = []
    saved.append({"correlation_id": corr, "question": args.question, "seconds": round(elapsed, 2),
                  "final": final, "events": events})
    path.write_text(json.dumps(saved, indent=2, ensure_ascii=False))
    log.info("saved reports/hw08/raw/part2_journeys.json")


if __name__ == "__main__":
    main()
