"""HW8 smoke test -> reports/hw08/verification.json   (make verify-hw08)

Run on the tagged commit with the stack up (docker compose up -d, make hw08-topics) and,
for the pipeline checks, planner.py / writer.py / reviewer.py running:

    python verify_hw08.py                  # all checks
    python verify_hw08.py --skip-agents    # Part 1 + FastAPI + offline suite only
    python verify_hw08.py --offline        # offline suite only (no Kafka)

Checks are behavioural (success flags, ids, correlation ids, counts, topics), never exact wording.
The script only sends messages and writes verification.json; it never modifies application code.
"""
import argparse
import json
import random
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path[:0] = [str(REPO / "code"), str(REPO / "code" / "kafka_service")]

import hw08_config as cfg  # noqa: E402

checks: list[dict] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    """Record + print one check."""
    checks.append({"name": name, "passed": bool(passed), "detail": str(detail)[:300]})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))


def safe(name: str, fn) -> None:  # noqa: ANN001
    """Run a check function; an exception is a FAIL, not a crash."""
    try:
        fn()
    except Exception as exc:                                         # noqa: BLE001
        check(name, False, f"{exc.__class__.__name__}: {exc}")


def git(*args: str) -> str:
    """git output or UNKNOWN."""
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, stderr=subprocess.DEVNULL).decode().strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def offline_checks() -> None:
    """Section 0 values + the offline test suite."""
    check("section0_config", (cfg.PORT_BASE, cfg.PREFIX, cfg.SEED, cfg.VERIFY_SEED, cfg.DOMAIN_ID)
          == (8000 + 1346 % 900, "s1346", 1346, 261346, 1346 % 8), f"port={cfg.PORT_BASE} prefix={cfg.PREFIX}")
    proc = subprocess.run([sys.executable, str(REPO / "code" / "test_hw08.py")], capture_output=True, text=True,
                          cwd=REPO, timeout=120)
    last = (proc.stdout.strip().splitlines() or ["no output"])[-1]
    check("offline_test_suite", proc.returncode == 0, last if proc.returncode == 0 else proc.stdout[-300:])


def part1_checks() -> None:
    """Kafka request/response round trips through the worker."""
    from incident_service import CREATE_OP, GET_OP
    from kafka_client import IncidentKafkaClient
    from kafka_common import topic_partitions, wait_for_broker

    def c_broker():
        wait_for_broker(timeout_s=20)
        check("kafka_broker_reachable", True, cfg.KAFKA_BOOTSTRAP)
    safe("kafka_broker_reachable", c_broker)
    if not checks[-1]["passed"]:
        return

    def c_topics():
        have = topic_partitions()
        bad = {t: have.get(t) for t, p in cfg.TOPICS.items() if have.get(t) != p}
        check("topics_exist_with_partitions", not bad, "all 7 OK (tasks=2)" if not bad else f"wrong/missing: {bad}")
    safe("topics_exist_with_partitions", c_topics)

    client = IncidentKafkaClient(component="verify", timeout_s=20)
    rng = random.Random(cfg.VERIFY_SEED)
    data = {"route_title": f"Verify Line {rng.randint(1, 99)}", "location": "Civic Center Station",
            "category": rng.choice(cfg.CATEGORIES), "passengers_affected": rng.randint(0, 500)}
    state: dict = {}

    def c_create():
        corr = str(uuid.uuid4())
        r = client.request(CREATE_OP, data, corr)
        uuid.UUID(str(r.get("incident_id")))
        state["id"] = r["incident_id"]
        check("create_incident_over_kafka", r.get("success") is True and r.get("correlation_id") == corr,
              f"incident_id={r['incident_id']} correlation preserved={r.get('correlation_id') == corr}")
    safe("create_incident_over_kafka", c_create)

    def c_get():
        corr = str(uuid.uuid4())
        r = client.request(GET_OP, {"incident_id": state["id"]}, corr)
        inc = r.get("incident") or {}
        same = all(inc.get(k) == v for k, v in data.items()) and inc.get("incident_id") == state["id"]
        check("get_incident_round_trip", r.get("success") is True and same and r.get("correlation_id") == corr,
              f"fields equal={same}")
    safe("get_incident_round_trip", c_get)

    def c_errors():
        cases = [("get_unknown_id", GET_OP, {"incident_id": str(uuid.uuid4())}),
                 ("unknown_operation", "PATCH_INCIDENT", {}),
                 ("invalid_fields", CREATE_OP, {**data, "category": "Flood", "location": ""})]
        for name, op, d in cases:
            corr = str(uuid.uuid4())
            r = client.request(op, d, corr)
            check(f"error_{name}", r.get("success") is False and bool(r.get("error")) and r.get("correlation_id") == corr,
                  f"error={r.get('error')!r}")
    safe("error_cases", c_errors)

    def c_duplicate():
        corr = str(uuid.uuid4())
        msg = {"correlation_id": corr, "reply_to": cfg.RESPONSE_TOPIC, "operation": CREATE_OP, "data": data}
        client.expect(corr)
        client.send_raw(msg, key=corr)
        client.send_raw(msg, key=corr)                              # replay, same correlation_id
        got = client.collect(corr, 2, timeout_s=20)
        ids = {r.get("incident_id") for r in got}
        check("duplicate_replay_idempotent", len(got) == 2 and len(ids) == 1 and all(r.get("success") for r in got),
              f"{len(got)} responses, distinct incident ids={len(ids)}")
    safe("duplicate_replay_idempotent", c_duplicate)
    client.close()

    def c_api():
        import requests
        base = f"http://127.0.0.1:{cfg.PORT_BASE}"
        h = requests.get(f"{base}/health", timeout=5).json()
        check("fastapi_on_port_base", h.get("port") == cfg.PORT_BASE, f"{base}/health -> {h.get('status')}")
        corr = str(uuid.uuid4())
        r = requests.post(f"{base}/incidents", json=data, headers={"X-Correlation-ID": corr}, timeout=30)
        g = requests.get(f"{base}/incidents/{r.json().get('incident_id')}", timeout=30)
        check("fastapi_create_get_via_kafka", r.status_code == 200 and r.json().get("correlation_id") == corr
              and g.status_code == 200 and g.json()["incident"]["route_title"] == data["route_title"],
              f"POST {r.status_code}, GET {g.status_code}")
        n = requests.get(f"{base}/incidents/{uuid.uuid4()}", timeout=30)
        check("fastapi_unknown_id_404", n.status_code == 404 and n.json().get("success") is False, f"{n.status_code}")
    safe("fastapi", c_api)


def agent_checks() -> None:
    """Part 2 end-to-end journey and Part 3 dead-letter behaviour (agents must be running)."""
    from confluent_kafka import Consumer

    from kafka_common import assign_at_end, encode, end_offsets, make_producer, read_topic

    def c_pipeline():
        reader = Consumer({"bootstrap.servers": cfg.KAFKA_BOOTSTRAP, "group.id": f"verify_{uuid.uuid4().hex[:6]}",
                           "enable.auto.commit": False})
        assign_at_end(reader, cfg.FINAL_TOPIC)
        corr = str(uuid.uuid4())
        p = make_producer(f"{cfg.PREFIX}-verify")
        p.produce(cfg.INBOX_TOPIC, key=corr.encode(), value=encode(
            {"correlation_id": corr, "question": "Which incident category is a route detour?", "asked_by": "verify"}))
        p.flush(10)
        final, deadline = None, time.time() + 300
        while time.time() < deadline and final is None:
            msg = reader.poll(1.0)
            if msg is not None and not msg.error():
                v = json.loads(msg.value())
                if v.get("correlation_id") == corr:
                    final = v
        reader.close()
        stages = [t.get("stage") for t in (final or {}).get("trace", [])]
        check("pipeline_inbox_to_final", bool(final) and final.get("status") in ("approved", "rejected")
              and bool(final.get("answer")) and all(s in stages for s in ("planner", "writer", "reviewer")),
              f"status={final and final.get('status')} stages={stages}" if final else
              "no final message in 300 s - start planner.py, writer.py, reviewer.py")
    safe("pipeline_inbox_to_final", c_pipeline)

    def c_dlq():
        start = end_offsets(cfg.DEAD_LETTER_TOPIC)
        p = make_producer(f"{cfg.PREFIX}-verify")
        marker = f"verify-poison-{uuid.uuid4().hex[:8]}"
        p.produce(cfg.TASKS_TOPIC, key=marker.encode(), value=f'{{"broken": "{marker}'.encode())
        p.flush(10)
        deadline, found = time.time() + 60, None
        while time.time() < deadline and not found:
            for r in read_topic(cfg.DEAD_LETTER_TOPIC, start=start, idle_s=2, max_s=10):
                if isinstance(r["value"], dict) and marker in str(r["value"].get("raw_value", "")):
                    found = r["value"]
        check("poison_to_dead_letter", bool(found) and found.get("attempts") == cfg.MAX_ATTEMPTS,
              f"attempts={found.get('attempts')} source={found.get('source_agent')}" if found else
              "not dead-lettered within 60 s (is writer.py running?)")
    safe("poison_to_dead_letter", c_dlq)


def main() -> None:
    """Run the checks and write reports/hw08/verification.json."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--skip-agents", action="store_true")
    args = ap.parse_args()
    started = time.time()
    commit = git("rev-parse", "HEAD")
    print(f"HW8 verification | {cfg.STUDENT_NAME} | {cfg.PREFIX} | commit {commit[:12]}")
    offline_checks()
    if not args.offline:
        part1_checks()
        if not args.skip_agents:
            agent_checks()
    cfg.ensure_dirs()
    passed = sum(c["passed"] for c in checks)
    out = {
        "homework": 8, "sid4": cfg.SID4, "prefix": cfg.PREFIX, "port_base": cfg.PORT_BASE,
        "domain_id": cfg.DOMAIN_ID, "commit": commit, "tag_hw8": git("rev-list", "-n", "1", "hw8"),
        "model": cfg.MODEL_DESCRIPTION, "hardware": cfg.HARDWARE, "seed": cfg.SEED, "verify_seed": cfg.VERIFY_SEED,
        "kafka": cfg.KAFKA_BOOTSTRAP, "mode": "offline" if args.offline else ("no-agents" if args.skip_agents else "full"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "duration_s": round(time.time() - started, 1),
        "checks": checks, "passed": passed, "total": len(checks), "all_passed": passed == len(checks),
    }
    (cfg.REPORT_DIR / "verification.json").write_text(json.dumps(out, indent=2))
    print(f"{passed}/{len(checks)} checks passed -> reports/hw08/verification.json")
    raise SystemExit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
