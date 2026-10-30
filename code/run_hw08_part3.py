"""HW8 Part 3 - failure behaviour runner: each scenario "before fix" and "after fix", with raw evidence.

    python code/run_hw08_part3.py --scenario all          # duplicate, consumer-death, poison, ordering
    python code/run_hw08_part3.py --scenario ordering
    python code/run_hw08_part3.py --scenario all --llm    # writers call qwen2.5:3b instead of the template

Needs Kafka + the seven topics (docker compose up, make hw08-topics). The runner starts its own Writer
processes (code/kafka_agents/writer.py) with a fresh consumer group per experiment, so stop any Writer you
started by hand first (planner/reviewer may keep running). The Writers use the template draft by default
(--fake-llm): these tests are about Kafka delivery, not answer quality, and the template keeps the timing
of every run the same. Evidence:
  reports/hw08/raw/part3_<scenario>.json, part3_ordering_{unkeyed,keyed}.csv, part3_events_*.jsonl
  reports/hw08/RUN_LOG.txt (runner + every writer process)
"""
import argparse
import csv
import json
import os
import random
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw08_config as cfg  # noqa: E402
from kafka_common import (  # noqa: E402
    committed_offsets,
    encode,
    end_offsets,
    make_producer,
    now_iso,
    read_topic,
    set_group_to_end,
    setup_logging,
    wait_for_broker,
)

WRITER = Path(__file__).resolve().parent / "kafka_agents" / "writer.py"
RUN_ID = time.strftime("%m%d%H%M%S")
NS = uuid.UUID("6f1f2b8e-1346-4a0b-9c2d-261346000000")
log = setup_logging("part3-runner")


# ---- helpers -------------------------------------------------------------------------------
class WriterProc:
    """A writer.py subprocess whose output is echoed live and whose events go to a JSONL file."""

    def __init__(self, instance: str, group: str, events: Path, state: Path, extra: list[str], llm: bool) -> None:
        self.instance, self.events = instance, events
        cmd = [sys.executable, str(WRITER), "--instance-id", instance, "--group", group,
               "--events-file", str(events), "--state-file", str(state), *extra]
        if not llm:
            cmd.append("--fake-llm")
        log.info("start writer %s: %s", instance, " ".join(cmd[1:]))
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        self.lines: list[str] = []
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.p.stdout:                      # type: ignore[union-attr]
            self.lines.append(line.rstrip())
            sys.stdout.write("      " + line)
            sys.stdout.flush()

    def alive(self) -> bool:
        return self.p.poll() is None

    def kill(self) -> None:
        """SIGKILL: the process dies mid-work, no cleanup, no commit."""
        self.p.kill()
        self.p.wait(10)

    def stop(self) -> None:
        """Graceful stop (SIGTERM)."""
        if self.alive():
            self.p.terminate()
            try:
                self.p.wait(15)
            except subprocess.TimeoutExpired:
                self.p.kill()


def events(path: Path) -> list[dict]:
    """Read a writer events file."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def wait_until(pred: Callable[[], bool], timeout: float, what: str) -> bool:
    """Poll a condition."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.25)
    log.warning("timed out after %.0fs waiting for: %s", timeout, what)
    return False


def has_event(path: Path, event: str, corr: Optional[str] = None, instance: Optional[str] = None) -> bool:
    """True if the events file holds a matching record."""
    return any(e.get("event") == event and (corr is None or e.get("correlation_id") == corr)
               and (instance is None or e.get("instance") == instance) for e in events(path))


def assigned(path: Path, instance: str) -> bool:
    """True once the writer has been assigned at least one partition."""
    return any(e.get("event") == "assigned" and e.get("instance") == instance and e.get("partitions")
               for e in events(path))


def task(corr: str, question: str) -> dict:
    """A normal Writer input message (what the Planner would send)."""
    return {"correlation_id": corr, "question": question, "kind": "task",
            "plan": ["Name the incident category", "Say how to report it", "Say what happens next"],
            "trace": [{"stage": "part3-runner", "instance": "runner", "at": now_iso()}]}


def drafts_for(corr: str, start: dict[int, int], instance_prefix: str) -> list[dict]:
    """Drafts on s1346_drafts for one correlation_id written by this experiment's writers."""
    out = []
    for rec in read_topic(cfg.DRAFTS_TOPIC, start=start, idle_s=2.5):
        v = rec["value"]
        if isinstance(v, dict) and v.get("correlation_id") == corr and any(
                str(t.get("instance", "")).startswith(f"writer-{instance_prefix}") for t in v.get("trace", [])):
            out.append({"partition": rec["partition"], "offset": rec["offset"], "trace": v.get("trace")})
    return out


def banner(text: str) -> None:
    """Section banner in the console and RUN_LOG."""
    log.info("=" * 20 + f" {text} " + "=" * 20)


def save(name: str, obj: Any) -> None:
    """Write a raw JSON file."""
    path = cfg.RAW_DIR / name
    path.write_text(json.dumps(obj, indent=2, default=str))
    log.info("saved reports/hw08/raw/%s", name)


def group_for(name: str) -> str:
    """Fresh consumer group positioned at the current end of s1346_tasks."""
    group = f"{cfg.PREFIX}_writers_{name}_{RUN_ID}"
    ends = set_group_to_end(group, cfg.TASKS_TOPIC)
    log.info("consumer group %s starts at end offsets %s", group, ends)
    return group


# ---- I. duplicate delivery -------------------------------------------------------------------
def duplicate(llm: bool) -> dict:
    """Send a task, then replay the exact same message (same correlation_id)."""
    banner("Part 3 I - duplicate delivery")
    producer = make_producer(f"{cfg.PREFIX}-part3-runner")
    result: dict[str, Any] = {"scenario": "duplicate", "at": now_iso()}
    for phase, extra in (("before", ["--no-idempotency"]), ("after", [])):
        inst = f"dup-{phase}"
        ev = cfg.RAW_DIR / f"part3_events_duplicate_{phase}.jsonl"
        ev.unlink(missing_ok=True)
        group = group_for(f"dup_{phase}")
        w = WriterProc(inst, group, ev, cfg.STATE_DIR / f"part3_dup_{phase}_{RUN_ID}.json", extra, llm)
        wait_until(lambda ev=ev, inst=inst: assigned(ev, f"writer-{inst}"), 60, "partition assignment")
        drafts_start = end_offsets(cfg.DRAFTS_TOPIC)
        corr = str(uuid.uuid4())
        payload = encode(task(corr, "How do I report a Delay on Line 14?"))
        log.info("[%s] send task corr=%s", phase, corr)
        producer.produce(cfg.TASKS_TOPIC, key=corr.encode(), value=payload)
        producer.flush(10)
        wait_until(lambda ev=ev, corr=corr: has_event(ev, "processed", corr), 90, "first processing")
        log.info("[%s] REPLAY the identical message (same correlation_id %s)", phase, corr)
        producer.produce(cfg.TASKS_TOPIC, key=corr.encode(), value=payload)
        producer.flush(10)
        wait_until(lambda ev=ev, corr=corr: sum(1 for e in events(ev) if e.get("correlation_id") == corr and
                                               e.get("event") in ("processed", "duplicate_skipped")) >= 2,
                   90, "replay handled")
        time.sleep(1)
        w.stop()
        drafts = drafts_for(corr, drafts_start, inst)
        evs = [e for e in events(ev) if e.get("correlation_id") == corr]
        result[phase] = {"writer_flags": extra, "correlation_id": corr, "deliveries": 2,
                         "times_processed": sum(1 for e in evs if e["event"] == "processed"),
                         "duplicates_skipped": sum(1 for e in evs if e["event"] == "duplicate_skipped"),
                         "drafts_produced": len(drafts), "drafts": drafts}
        log.info("[%s] RESULT: 2 deliveries -> processed %d time(s), skipped %d, drafts on %s = %d", phase,
                 result[phase]["times_processed"], result[phase]["duplicates_skipped"], cfg.DRAFTS_TOPIC, len(drafts))
    save("part3_duplicate.json", result)
    return result


# ---- II. consumer death ----------------------------------------------------------------------
def consumer_death(llm: bool) -> dict:
    """Kill the Writer with SIGKILL in the middle of processing, restart it, see what happened to the message."""
    banner("Part 3 II - consumer killed mid-processing")
    producer = make_producer(f"{cfg.PREFIX}-part3-runner")
    result: dict[str, Any] = {"scenario": "consumer_death", "at": now_iso()}
    for phase, extra in (("before", ["--auto-commit"]), ("after", [])):
        ev = cfg.RAW_DIR / f"part3_events_consumer_death_{phase}.jsonl"
        ev.unlink(missing_ok=True)
        group = group_for(f"death_{phase}")
        state = cfg.STATE_DIR / f"part3_death_{phase}_{RUN_ID}.json"
        a = WriterProc(f"death-{phase}-a", group, ev, state, [*extra, "--work-delay", "8"], llm)
        wait_until(lambda ev=ev, phase=phase: assigned(ev, f"writer-death-{phase}-a"), 60, "partition assignment")
        drafts_start = end_offsets(cfg.DRAFTS_TOPIC)
        corr = str(uuid.uuid4())
        producer.produce(cfg.TASKS_TOPIC, key=corr.encode(), value=encode(task(corr, "Bus 38 had an Accident, "
                                                                                      "what should riders do?")))
        producer.flush(10)
        wait_until(lambda ev=ev, corr=corr: has_event(ev, "received", corr), 60, "message received")
        rec = next(e for e in events(ev) if e.get("event") == "received" and e.get("correlation_id") == corr)
        part, off = rec["partition"], rec["offset"]
        time.sleep(2.5)                                           # writer is now inside its 8 s of work
        before_kill = committed_offsets(group, cfg.TASKS_TOPIC).get(part)
        log.info("[%s] writer is mid-processing %s[%d]@%d -> SIGKILL (committed offset now %s)",
                 phase, cfg.TASKS_TOPIC, part, off, before_kill)
        a.kill()
        after_kill = committed_offsets(group, cfg.TASKS_TOPIC).get(part)
        log.info("[%s] writer killed; committed offset for partition %d = %s (message offset %d) -> %s", phase,
                 part, after_kill, off, "message would be LOST (offset already past it)"
                 if (after_kill if after_kill is not None else -1) > off else "message will be redelivered")
        b = WriterProc(f"death-{phase}-b", group, ev, state, [*extra, "--work-delay", "1"], llm)
        wait_until(lambda ev=ev, phase=phase: assigned(ev, f"writer-death-{phase}-b"), 60, "restart assignment")
        redelivered = wait_until(lambda ev=ev, corr=corr, phase=phase:
                                 has_event(ev, "processed", corr, f"writer-death-{phase}-b"), 30,
                                 "redelivery to the restarted writer")
        time.sleep(1)
        final_commit = committed_offsets(group, cfg.TASKS_TOPIC).get(part)
        b.stop()
        drafts = drafts_for(corr, drafts_start, f"death-{phase}")
        result[phase] = {"writer_flags": extra, "correlation_id": corr, "partition": part, "message_offset": off,
                         "committed_before_kill": before_kill, "committed_after_kill": after_kill,
                         "redelivered_after_restart": redelivered, "committed_after_restart": final_commit,
                         "drafts_produced": len(drafts), "outcome": "completed after restart" if drafts else "LOST"}
        log.info("[%s] RESULT: committed after kill=%s, redelivered=%s, committed after restart=%s, drafts=%d -> %s",
                 phase, after_kill, redelivered, final_commit, len(drafts), result[phase]["outcome"])
    save("part3_consumer_death.json", result)
    return result


# ---- III. poison message -----------------------------------------------------------------------
def poison(llm: bool) -> dict:
    """A bad message followed by a good one in the same partition."""
    banner("Part 3 III - poison message")
    producer = make_producer(f"{cfg.PREFIX}-part3-runner")
    result: dict[str, Any] = {"scenario": "poison", "at": now_iso(), "max_attempts": cfg.MAX_ATTEMPTS}
    key = b"poison-demo"                       # same key -> same partition, so the good message queues behind
    group = group_for("poison")                # shared by both phases: "after" starts where "before" got stuck
    state = cfg.STATE_DIR / f"part3_poison_{RUN_ID}.json"
    dlq_start = end_offsets(cfg.DEAD_LETTER_TOPIC)
    drafts_start = end_offsets(cfg.DRAFTS_TOPIC)

    # before: no retries, no dead-letter topic -> crash, crash again on restart, good message blocked
    ev = cfg.RAW_DIR / "part3_events_poison_before.jsonl"
    ev.unlink(missing_ok=True)
    good1 = str(uuid.uuid4())
    producer.produce(cfg.TASKS_TOPIC, key=key, value=b'{"correlation_id": "poison-1", "question": "broken...')
    producer.produce(cfg.TASKS_TOPIC, key=key, value=encode(task(good1, "Is the Red line delayed?")))
    producer.flush(10)
    log.info("[before] sent poison (invalid JSON) then good message corr=%s, same partition", good1)
    crashes = 0
    for attempt in (1, 2):
        w = WriterProc(f"poison-before-{attempt}", group, ev, state, ["--no-dlq"], llm)
        wait_until(lambda w=w: not w.alive(), 60, "writer crash")
        crashes += 0 if w.alive() else 1
        log.info("[before] writer run %d exited with code %s", attempt, w.p.returncode)
        w.stop()
        time.sleep(1)
    blocked = not has_event(ev, "processed", good1)
    result["before"] = {"writer_flags": ["--no-dlq"], "crashes": crashes, "good_message_corr": good1,
                        "good_message_processed": not blocked,
                        "dead_letter_records": 0, "committed": committed_offsets(group, cfg.TASKS_TOPIC)}
    log.info("[before] RESULT: %d crashes on the same offset, good message processed=%s -> partition BLOCKED",
             crashes, not blocked)

    # after: bounded retries -> dead letter -> commit -> later messages flow
    ev = cfg.RAW_DIR / "part3_events_poison_after.jsonl"
    ev.unlink(missing_ok=True)
    good2 = str(uuid.uuid4())
    producer.produce(cfg.TASKS_TOPIC, key=key, value=encode({"correlation_id": "poison-2",
                                                             "question": "missing plan field"}))
    producer.produce(cfg.TASKS_TOPIC, key=key, value=encode(task(good2, "Which category is a detour?")))
    producer.flush(10)
    log.info("[after] same stuck group; also sent a 2nd poison (JSON without 'plan') and good corr=%s", good2)
    w = WriterProc("poison-after", group, ev, state, [], llm)
    wait_until(lambda: has_event(ev, "processed", good1) and has_event(ev, "processed", good2), 120,
               "both good messages")
    time.sleep(1)
    w.stop()
    dlq = [r for r in read_topic(cfg.DEAD_LETTER_TOPIC, start=dlq_start)
           if isinstance(r["value"], dict) and str(r["value"].get("source_agent", "")).startswith("writer-poison")]
    result["after"] = {
        "writer_flags": [], "dead_letter_records": len(dlq),
        "dead_letters": [{k: r["value"].get(k) for k in ("correlation_id", "error", "attempts", "partition", "offset")}
                         for r in dlq],
        "retry_lines": [ln for ln in w.lines if "RETRY attempt" in ln],
        "good_messages_processed": {good1: has_event(ev, "processed", good1), good2: has_event(ev, "processed", good2)},
        "drafts_for_good_messages": len(drafts_for(good1, drafts_start, "poison"))
        + len(drafts_for(good2, drafts_start, "poison")),
        "committed": committed_offsets(group, cfg.TASKS_TOPIC)}
    log.info("[after] RESULT: %d message(s) -> %s after %d attempts each; good messages processed: %s",
             len(dlq), cfg.DEAD_LETTER_TOPIC, cfg.MAX_ATTEMPTS, result["after"]["good_messages_processed"])
    save("part3_poison.json", result)
    return result


# ---- IV. ordering ------------------------------------------------------------------------------
def ordering_messages() -> list[dict]:
    """20 related messages from VERIFY_SEED: 4 incidents x 5 status updates, interleaved."""
    rng = random.Random(cfg.VERIFY_SEED)
    entities = [f"INC-{rng.randint(100000, 999999)}" for _ in range(4)]
    stages = ["reported", "dispatched", "on_scene", "service_restored", "closed"]
    order = [e for e in entities for _ in range(5)]
    rng.shuffle(order)
    seq = dict.fromkeys(entities, 0)
    msgs = []
    for i, ent in enumerate(order):
        seq[ent] += 1
        msgs.append({"kind": "ordering_probe", "msg_index": i, "entity_id": ent, "seq": seq[ent],
                     "status": stages[seq[ent] - 1], "work_ms": rng.randint(50, 400),
                     "unkeyed_partition": rng.randint(0, 1)})
    return msgs


def analyse(processed: list[dict]) -> dict:
    """Per-entity order check over the processing order."""
    per_entity: dict[str, list[int]] = {}
    partitions: dict[str, set] = {}
    for e in processed:
        per_entity.setdefault(e["entity_id"], []).append(e["seq"])
        partitions.setdefault(e["entity_id"], set()).add(e["partition"])
    inversions = {ent: sum(1 for i in range(len(s)) for j in range(i + 1, len(s)) if s[i] > s[j])
                  for ent, s in per_entity.items()}
    return {"entities": {ent: {"processed_seq": s, "in_order": s == sorted(s), "inversions": inversions[ent],
                               "partitions": sorted(partitions[ent])} for ent, s in per_entity.items()},
            "entities_in_order": sum(1 for s in per_entity.values() if s == sorted(s)),
            "entities_total": len(per_entity), "total_inversions": sum(inversions.values()),
            "messages_processed": len(processed)}


def ordering(llm: bool) -> dict:
    """Two partitions, two writers in one group: no key vs entity key."""
    banner("Part 3 IV - ordering (2 partitions, 2 writers, same group)")
    msgs = ordering_messages()
    save("part3_ordering_messages.json", msgs)
    summary: dict[str, Any] = {"scenario": "ordering", "at": now_iso(), "verify_seed": cfg.VERIFY_SEED}
    for run in ("unkeyed", "keyed"):
        ev = cfg.RAW_DIR / f"part3_events_ordering_{run}.jsonl"
        ev.unlink(missing_ok=True)
        group = group_for(f"order_{run}")
        writers = [WriterProc(f"order-{run}-{n}", group, ev, cfg.STATE_DIR / f"part3_order_{run}_{n}_{RUN_ID}.json",
                              [], llm) for n in (1, 2)]

        def balanced(ev: Path = ev, run: str = run) -> bool:
            last: dict[str, list] = {}
            for e in events(ev):
                if e.get("event") == "assigned":
                    last[e["instance"]] = e.get("partitions", [])
            return all(len(last.get(f"writer-order-{run}-{n}", [])) == 1 for n in (1, 2))

        wait_until(balanced, 90, "one partition per writer")
        time.sleep(1)
        producer = make_producer(f"{cfg.PREFIX}-part3-ordering", partitioner="murmur2_random")
        corrs = {}
        for m in msgs:
            corr = str(uuid.uuid5(NS, f"{RUN_ID}-{run}-{m['msg_index']}"))
            corrs[corr] = m
            value = encode({**{k: v for k, v in m.items() if k != "unkeyed_partition"}, "correlation_id": corr})
            if run == "keyed":
                producer.produce(cfg.TASKS_TOPIC, key=m["entity_id"].encode(), value=value)
            else:   # no key: spread over both partitions (seeded, so the run is reproducible)
                producer.produce(cfg.TASKS_TOPIC, value=value, partition=m["unkeyed_partition"])
        producer.flush(10)
        log.info("[%s] sent 20 messages (%s)", run, "key = entity_id" if run == "keyed" else "no key")
        wait_until(lambda ev=ev, corrs=corrs: sum(1 for e in events(ev) if e.get("event") == "processed"
                                                  and e.get("correlation_id") in corrs) >= 20, 120, "20 processed")
        for w in writers:
            w.stop()
        processed = sorted((e for e in events(ev) if e.get("event") == "processed" and e.get("correlation_id") in corrs),
                           key=lambda e: e["ts"])
        rows = []
        for pos, e in enumerate(processed, 1):
            m = corrs[e["correlation_id"]]
            rows.append({"processed_position": pos, "processed_at": e["at"], "writer": e["instance"],
                         "partition": e["partition"], "offset": e["offset"], "msg_index_sent": m["msg_index"],
                         "entity_id": m["entity_id"], "seq": m["seq"], "status": m["status"],
                         "work_ms": m["work_ms"]})
        with open(cfg.RAW_DIR / f"part3_ordering_{run}.csv", "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["processed_position"])
            wr.writeheader()
            wr.writerows(rows)
        res = analyse(rows)
        summary[run] = res
        log.info("[%s] processing order (entity:seq@partition/writer):", run)
        for r in rows:
            log.info("   %2d. %s:%d@p%d/%s", r["processed_position"], r["entity_id"], r["seq"], r["partition"],
                     r["writer"].rsplit("-", 1)[-1])
        for ent, info in res["entities"].items():
            log.info("[%s] %s partitions=%s processed seq=%s -> %s", run, ent, info["partitions"],
                     info["processed_seq"], "IN ORDER" if info["in_order"] else f"OUT OF ORDER ({info['inversions']} inversions)")
        log.info("[%s] RESULT: %d/%d entities in order, %d inversions", run, res["entities_in_order"],
                 res["entities_total"], res["total_inversions"])
    save("part3_ordering_summary.json", summary)
    return summary


def main() -> None:
    """Run the selected scenarios."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="all", choices=["all", "duplicate", "consumer-death", "poison", "ordering"])
    ap.add_argument("--llm", action="store_true", help="writers call the local model instead of the template")
    args = ap.parse_args()
    cfg.ensure_dirs()
    wait_for_broker(log)
    log.info("HW8 Part 3 runner | %s | %s | run %s | VERIFY_SEED %d | writers use %s", cfg.STUDENT_NAME, cfg.PREFIX,
             RUN_ID, cfg.VERIFY_SEED, cfg.MODEL_DESCRIPTION if args.llm else "template drafts (--fake-llm)")
    todo = ["duplicate", "consumer-death", "poison", "ordering"] if args.scenario == "all" else [args.scenario]
    fns = {"duplicate": duplicate, "consumer-death": consumer_death, "poison": poison, "ordering": ordering}
    for name in todo:
        fns[name](args.llm)
    log.info("done - rebuild the tables with: make hw08-metrics")


if __name__ == "__main__":
    main()
