"""HW8 offline tests - no Kafka broker, no Ollama, no network (make hw08-test).

Covers the logic that the Kafka processes wrap: incident validation and storage, correlation-id
idempotency, the retry/dead-letter decision, the agents' handlers in template mode, and the
ordering-run message generator and order analysis.
"""
import os
import sys
import uuid
from pathlib import Path

os.environ["HW08_RUN_LOG"] = "0"          # tests must not write to the real RUN_LOG
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "kafka_service"), str(HERE / "kafka_agents")]

import hw08_config as cfg
import planner
import reviewer
import run_hw08_part3 as part3
import writer
from agent_base import PoisonMessageError, ProcessedStore, process_with_retries, require_fields
from incident_service import CREATE_OP, GET_OP, IncidentService

GOOD = {"route_title": "Line 22 - Fillmore", "location": "Fillmore & Geary", "category": "Breakdown",
        "passengers_affected": 37}
RESULTS: list[tuple[str, bool, str]] = []


def req(op: str, data: dict, corr: str | None = None) -> dict:
    """Build a request envelope."""
    return {"correlation_id": corr or str(uuid.uuid4()), "reply_to": cfg.RESPONSE_TOPIC, "operation": op, "data": data}


def case(name: str):  # noqa: ANN201
    """Register a test function."""
    def wrap(fn):  # noqa: ANN001, ANN202
        try:
            fn()
            RESULTS.append((name, True, ""))
        except Exception as exc:                                     # noqa: BLE001
            RESULTS.append((name, False, f"{exc.__class__.__name__}: {exc}"))
        return fn
    return wrap


class _Log:
    """Minimal logger stand-in."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def warning(self, msg: str, *args: object) -> None:
        self.lines.append(msg % args)


@case("config_section0_values")
def _():
    assert (cfg.PORT_BASE, cfg.PREFIX, cfg.SEED, cfg.VERIFY_SEED, cfg.DOMAIN_ID) == (8446, "s1346", 1346, 261346, 2)
    assert cfg.TOPICS[cfg.TASKS_TOPIC] == 2 and all(t.startswith("s1346_") for t in cfg.TOPICS)
    assert cfg.REQUEST_TOPIC == "s1346_incident_requests" and cfg.RESPONSE_TOPIC == "s1346_incident_responses"


@case("create_then_get_round_trip")
def _():
    s = IncidentService()
    r = s.handle(req(CREATE_OP, GOOD, "c-1"))[0]
    assert r["success"] and r["correlation_id"] == "c-1" and uuid.UUID(r["incident_id"])
    g = s.handle(req(GET_OP, {"incident_id": r["incident_id"]}, "c-2"))[0]
    assert g["success"] and g["correlation_id"] == "c-2"
    assert all(g["incident"][k] == v for k, v in GOOD.items()) and g["incident"]["incident_id"] == r["incident_id"]


@case("create_rejects_missing_empty_invalid")
def _():
    s = IncidentService()
    for bad in ({**GOOD, "route_title": ""}, {k: v for k, v in GOOD.items() if k != "location"},
                {**GOOD, "category": "Flood"}, {**GOOD, "passengers_affected": -1},
                {**GOOD, "passengers_affected": "12"}, {**GOOD, "passengers_affected": True},
                {**GOOD, "route_title": "   "}, {**GOOD, "reporter_email": "a@b.c"}):
        r = s.handle(req(CREATE_OP, bad, "bad"))[0]
        assert r["success"] is False and r["correlation_id"] == "bad" and r["error"].startswith("Validation failed")
    assert s.incidents == {}


@case("get_unknown_and_malformed_ids")
def _():
    s = IncidentService()
    assert s.handle(req(GET_OP, {"incident_id": str(uuid.uuid4())}, "x"))[0]["error"] == "Incident not found"
    assert "valid UUID" in s.handle(req(GET_OP, {"incident_id": "abc"}))[0]["error"]
    assert "required" in s.handle(req(GET_OP, {}))[0]["error"]


@case("unknown_operation_and_bad_envelope_keep_correlation_id")
def _():
    s = IncidentService()
    r = s.handle(req("DELETE_INCIDENT", {}, "u-1"))[0]
    assert r == {"correlation_id": "u-1", "operation": "DELETE_INCIDENT", "success": False, "error": "Unknown operation"}
    r = s.handle({"correlation_id": "e-1", "operation": CREATE_OP, "data": GOOD})[0]      # no reply_to
    assert r["success"] is False and r["correlation_id"] == "e-1" and "reply_to" in r["error"]
    assert s.safe_reply_topic({"reply_to": "someone_elses_topic"}) == cfg.RESPONSE_TOPIC


@case("duplicate_create_has_no_side_effect")
def _():
    s = IncidentService()
    first, dup1 = s.handle(req(CREATE_OP, GOOD, "same"))
    second, dup2 = s.handle(req(CREATE_OP, GOOD, "same"))
    assert not dup1 and dup2 and first == second and len(s.incidents) == 1
    off = IncidentService(idempotent=False)
    a, _ = off.handle(req(CREATE_OP, GOOD, "same"))
    b, _ = off.handle(req(CREATE_OP, GOOD, "same"))
    assert a["incident_id"] != b["incident_id"] and len(off.incidents) == 2      # the "before fix" behaviour


@case("retries_are_bounded_then_dead_letter")
def _():
    log, sleeps = _Log(), []
    out, err, attempts, _ = process_with_retries(b"{not json", lambda v: v, ("correlation_id",), 3, log, sleeps.append)
    assert out is None and "invalid JSON" in err and attempts == 3 and len(log.lines) == 3 and len(sleeps) == 2
    calls = {"n": 0}

    def flaky(v: dict) -> dict:
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("model timeout")
        return {"ok": True}
    out, err, attempts, _ = process_with_retries(b'{"correlation_id": "c"}', flaky, ("correlation_id",), 3,
                                                 _Log(), lambda s: None)
    assert out == {"ok": True} and err is None and attempts == 2


@case("require_fields_detects_poison")
def _():
    try:
        require_fields({"correlation_id": "c", "question": "q", "plan": []}, writer.TASK_FIELDS)
        raise AssertionError("empty plan accepted")
    except PoisonMessageError as exc:
        assert "plan" in str(exc)
    assert writer.required_for({"kind": "ordering_probe"}) == writer.PROBE_FIELDS


@case("processed_store_persists")
def _():
    path = cfg.STATE_DIR / f"test_store_{uuid.uuid4().hex}.json"
    try:
        ProcessedStore(path).add("c-1")
        assert "c-1" in ProcessedStore(path)
    finally:
        path.unlink(missing_ok=True)


@case("agents_template_mode_preserve_correlation_id")
def _():
    msg = {"correlation_id": "j-1", "question": "How do I report a Breakdown?", "trace": []}
    task = planner.build_handler(None)(msg)
    draft = writer.build_handler(None)(task)
    final = reviewer.build_handler(None)(draft)
    assert task["correlation_id"] == draft["correlation_id"] == final["correlation_id"] == "j-1"
    assert len(task["plan"]) >= 2 and draft["draft"] and final["status"] == "approved" and final["answer"]
    assert writer.build_handler(None)({"kind": "ordering_probe", "correlation_id": "p", "entity_id": "E", "seq": 1}) is None
    assert reviewer.deterministic_issues("word " * 250)


@case("ordering_messages_seeded_and_analysis")
def _():
    a, b = part3.ordering_messages(), part3.ordering_messages()
    assert a == b and len(a) == 20 and len({m["entity_id"] for m in a}) == 4
    for ent in {m["entity_id"] for m in a}:
        assert [m["seq"] for m in a if m["entity_id"] == ent] == [1, 2, 3, 4, 5]     # sent in order
    rows = [{"entity_id": "E", "seq": 2, "partition": 1}, {"entity_id": "E", "seq": 1, "partition": 0},
            {"entity_id": "F", "seq": 1, "partition": 0}, {"entity_id": "F", "seq": 2, "partition": 0}]
    res = part3.analyse(rows)
    assert res["entities"]["E"]["in_order"] is False and res["entities"]["F"]["in_order"] is True
    assert res["total_inversions"] == 1


def main() -> int:
    """Print results; exit 1 on any failure."""
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} offline HW8 tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
