"""DATA-260 HW6 - append real Part 1 / Part 2 console output to reports/hw06/RUN_LOG.txt.

    python code/log_parts_1_2.py          (backend on 8446, MongoDB up)

Part 1: CRUD round trip on a temporary incident document (deleted again) plus the
validation / error cases. Part 2: GET /api/memory/himja and GET /api/aggregate/himja.
"""
import json
from datetime import datetime
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8446"
RUN_LOG = Path(__file__).resolve().parents[1] / "reports" / "hw06" / "RUN_LOG.txt"
URL = f"{BASE}/api/doc/incidents"


def log(line: str) -> None:
    """Print and append one timestamped line."""
    text = f"[{datetime.now().isoformat(timespec='seconds')}] {line}"
    print(text)
    with open(RUN_LOG, "a") as fh:
        fh.write(text + "\n")


def call(label: str, method: str, url: str, **kw) -> requests.Response:
    """Send one request and log status + body."""
    r = requests.request(method, url, timeout=30, **kw)
    body = r.text if len(r.text) < 600 else r.text[:600] + " ..."
    log(f"{label}: {method} {url.replace(BASE, '')} -> HTTP {r.status_code} {body}")
    return r


def main() -> None:
    """Run the Part 1 and Part 2 checks."""
    log("=== Part 1 / Part 2 console log (code/log_parts_1_2.py) ===")
    call("health", "GET", f"{BASE}/health")
    created = call("create", "POST", URL, json={
        "title": "RUN_LOG demo - bus 5512 door fault", "description": "Rear door will not close",
        "location": "Diridon Station", "category": "Breakdown", "occurred_at": "2026-10-18T20:30:00Z"})
    doc_id = created.json()["id"]
    call("list", "GET", URL, params={"limit": 3})
    call("get one", "GET", f"{URL}/{doc_id}")
    call("update", "PUT", f"{URL}/{doc_id}", json={"status": "Investigating"})
    call("delete", "DELETE", f"{URL}/{doc_id}")
    call("get deleted", "GET", f"{URL}/{doc_id}")
    good = {"title": "t", "category": "Delay", "occurred_at": "2026-10-18T08:00:00Z"}
    call("missing required", "POST", URL, json={"description": "no title"})
    call("invalid enum", "POST", URL, json={**good, "category": "Flood", "status": "Done"})
    call("wrong type", "POST", URL, json={**good, "title": 123, "occurred_at": "yesterday"})
    call("too long", "POST", URL, json={**good, "title": "x" * 101})
    call("malformed id", "GET", f"{URL}/not-an-id")
    call("not json", "POST", URL, data="title=x", headers={"Content-Type": "text/plain"})
    mem = requests.get(f"{BASE}/api/memory/himja", timeout=30).json()
    log("memory himja: " + json.dumps({"recent_messages": len(mem["recent_messages"]),
                                        "latest_session_summary": bool(mem["latest_session_summary"]),
                                        "latest_lifetime_summary": bool(mem["latest_lifetime_summary"]),
                                        "recent_episodes": [e["fact"] for e in mem["recent_episodes"]]}))
    call("aggregate himja", "GET", f"{BASE}/api/aggregate/himja")


if __name__ == "__main__":
    main()
