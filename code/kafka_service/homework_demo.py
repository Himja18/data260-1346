"""HW8 Part 1 demonstration: CREATE_INCIDENT -> GET_INCIDENT over Kafka, with the full message flow.

    python code/kafka_service/homework_demo.py            # client talks to Kafka directly
    python code/kafka_service/homework_demo.py --via-api  # same flow through the FastAPI wrapper (port 8446)

Needs Kafka + the worker running (docker compose up). The worker writes its receive/process/reply
events to reports/hw08/raw/message_trace.jsonl, so step 9 can print the complete cross-process
sequence in time order. Results are saved to reports/hw08/raw/part1_demo.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1])]

import hw08_config as cfg  # noqa: E402
from incident_service import CREATE_OP, GET_OP  # noqa: E402
from kafka_client import IncidentKafkaClient  # noqa: E402
from kafka_common import new_correlation_id, now_iso, setup_logging  # noqa: E402

log = setup_logging("demo")

INCIDENT = {
    "route_title": "Line 22 - Fillmore",
    "location": "Fillmore St & Geary Blvd",
    "category": "Breakdown",
    "passengers_affected": 37,
    "description": "Trolley bus lost overhead power; passengers moved to the next bus.",
}

EVENT_LABEL = {"client_sent": "SEND", "worker_received": "RECEIVE", "worker_processed": "PROCESS",
               "worker_replied": "REPLY", "client_received": "CLIENT RESPONSE"}


def step(n: int, text: str) -> None:
    """Print a numbered step banner."""
    log.info("---- step %d: %s", n, text)


class ApiClient:
    """Same interface as IncidentKafkaClient.request, but over HTTP to the FastAPI wrapper."""

    def __init__(self) -> None:
        import requests
        self.s = requests.Session()
        self.base = f"http://127.0.0.1:{cfg.PORT_BASE}"

    def request(self, operation: str, data: dict, correlation_id: str) -> dict:
        """POST/GET through the API; the API sends to Kafka and waits for the reply."""
        headers = {"X-Correlation-ID": correlation_id}
        if operation == CREATE_OP:
            r = self.s.post(f"{self.base}/incidents", json=data, headers=headers, timeout=40)
        elif operation == GET_OP:
            r = self.s.get(f"{self.base}/incidents/{data.get('incident_id', '')}", headers=headers, timeout=40)
        else:
            r = self.s.post(f"{self.base}/kafka/request", json={"operation": operation, "data": data},
                            headers=headers, timeout=40)
        log.info("HTTP %s -> status %d, X-Correlation-ID=%s", operation, r.status_code, r.headers.get("X-Correlation-ID"))
        return r.json()

    def close(self) -> None:
        """Nothing to close."""


def sequence_for(correlation_ids: list[str], since: float) -> list[dict]:
    """Trace events of these correlation ids (all processes), oldest first."""
    if not cfg.TRACE_FILE.exists():
        return []
    rows = []
    for line in cfg.TRACE_FILE.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("correlation_id") in correlation_ids and rec.get("ts", 0) >= since:
            rows.append(rec)
    return sorted(rows, key=lambda r: r["ts"])


def main() -> None:
    """Run the 10 required steps plus three error cases."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--via-api", action="store_true", help="go through the FastAPI wrapper on PORT_BASE")
    args = ap.parse_args()
    started = time.time()
    log.info("HW8 Part 1 demo | %s | %s | requests=%s responses=%s | mode=%s", cfg.STUDENT_NAME, cfg.PREFIX,
             cfg.REQUEST_TOPIC, cfg.RESPONSE_TOPIC, "FastAPI" if args.via_api else "direct Kafka client")
    client = ApiClient() if args.via_api else IncidentKafkaClient(component="client", timeout_s=30)
    time.sleep(0.5)

    step(1, "create one correlation_id for CREATE_INCIDENT")
    create_corr = new_correlation_id()
    log.info("correlation_id = %s", create_corr)

    step(2, f"send CREATE_INCIDENT to {cfg.REQUEST_TOPIC}  (steps 3-6 are the SEND / worker / RESPONSE lines)")
    create_resp = client.request(CREATE_OP, INCIDENT, create_corr)
    time.sleep(0.3)
    for rec in sequence_for([create_corr], started):
        log.info("   step %s | %-15s | %-7s | corr=%s", {"client_sent": 3, "worker_received": 4,
                 "worker_processed": 4, "worker_replied": 5, "client_received": 6}.get(rec["event"], "?"),
                 EVENT_LABEL.get(rec["event"], rec["event"]), rec["component"], rec["correlation_id"])

    step(7, "extract the generated incident_id")
    if not create_resp.get("success"):
        log.error("CREATE failed: %s", create_resp)
        raise SystemExit(1)
    incident_id = create_resp["incident_id"]
    log.info("incident_id = %s | success=%s | correlation preserved=%s", incident_id, create_resp["success"],
             create_resp.get("correlation_id") == create_corr)

    step(8, "send GET_INCIDENT with that incident_id (new correlation_id)")
    get_corr = new_correlation_id()
    get_resp = client.request(GET_OP, {"incident_id": incident_id}, get_corr)
    time.sleep(0.3)

    step(9, "complete CREATE -> GET sequence across client and worker (from the shared trace)")
    seq = sequence_for([create_corr, get_corr], started)
    for rec in seq:
        op = rec.get("operation") or ""
        extra = ""
        if rec["event"] == "worker_processed":
            extra = f" success={rec.get('success')} store_size={rec.get('store_size')}"
        if rec["event"] == "client_received":
            extra = f" success={rec.get('success')} latency={rec.get('latency_ms')}ms"
        log.info("   %s | %-15s | %-6s | %-15s | topic=%s corr=%s%s", rec["at"][11:23],
                 EVENT_LABEL.get(rec["event"], rec["event"]), rec["component"], op,
                 rec.get("topic", "-"), rec["correlation_id"], extra)

    step(10, "retrieved incident + correlation_id check")
    log.info("GET response: %s", json.dumps(get_resp, indent=2))
    same_fields = all(get_resp.get("incident", {}).get(k) == v for k, v in INCIDENT.items())
    log.info("correlation preserved: CREATE %s, GET %s | fields round-trip: %s",
             create_resp.get("correlation_id") == create_corr, get_resp.get("correlation_id") == get_corr,
             same_fields)

    log.info("---- error handling (each error still echoes its correlation_id)")
    errors = {}
    for name, op, data in [
        ("unknown_incident_id", GET_OP, {"incident_id": "00000000-0000-4000-8000-000000000000"}),
        ("unknown_operation", "DELETE_INCIDENT", {"incident_id": incident_id}),
        ("missing_and_invalid_fields", CREATE_OP, {"route_title": "", "category": "Flood",
                                                   "passengers_affected": -3}),
    ]:
        corr = new_correlation_id()
        resp = client.request(op, data, corr)
        errors[name] = {"request_correlation_id": corr, "response": resp,
                        "correlation_preserved": resp.get("correlation_id") == corr}
        log.info("%-27s success=%s error=%r corr preserved=%s", name, resp.get("success"), resp.get("error"),
                 resp.get("correlation_id") == corr)

    client.close()
    cfg.ensure_dirs()
    out = {"at": now_iso(), "mode": "api" if args.via_api else "kafka", "incident_input": INCIDENT,
           "create": {"correlation_id": create_corr, "response": create_resp},
           "get": {"correlation_id": get_corr, "response": get_resp}, "fields_round_trip": same_fields,
           "errors": errors, "sequence": seq}
    (cfg.RAW_DIR / f"part1_demo{'_api' if args.via_api else ''}.json").write_text(json.dumps(out, indent=2))
    log.info("saved reports/hw08/raw/part1_demo%s.json", "_api" if args.via_api else "")


if __name__ == "__main__":
    main()
