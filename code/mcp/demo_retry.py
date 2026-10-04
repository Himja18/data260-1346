"""HW5 Part 3 - retry policy demo (three required cases), runs offline.

  python code/mcp/demo_retry.py

Case A: success on the first attempt
Case B: first attempt fails (timeout), retry succeeds
Case C: every attempt fails -> clean {ok:false} envelope, no crash
"""
import getpass
import json
import time
from datetime import datetime

from domain_tools import run_tool
from resilience import INTERACTIVE, ResilientRepository, TransientError

ROW = {"id": 5005, "incident_code": "INC-005005", "route_title": "Route 5 - 15 min delay at Main St",
       "category": "Delay", "passengers_affected": 35, "line_code": "L-005", "line_name": "Route 5",
       "line_mode": "Bus", "created_at": "2026-10-04T20:53:00", "updated_at": "2026-10-04T20:53:00"}


class ScriptedRepo:
    """Fake storage that follows a script per attempt: 'ok', 'slow' (exceeds the
    per-attempt timeout), or 'fail' (transient error)."""
    def __init__(self, script):
        self.script, self.i = list(script), 0

    def get_incident(self, code):
        step = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        if step == "slow":
            time.sleep(INTERACTIVE.attempt_timeout_s + 0.5)
        if step == "fail":
            raise TransientError("connection reset by peer (simulated)")
        return dict(ROW, incident_code=code)


def run(label, script):
    repo = ResilientRepository(ScriptedRepo(script), INTERACTIVE)
    env = run_tool("get_incident", {"incident_code": "INC-005005"}, repo=repo)
    r = repo.last_report
    print(f"\n=== {label} ===")
    print(f"attempt outcomes : {r.attempt_outcomes}")
    print(f"attempts used    : {r.attempts}/{INTERACTIVE.max_attempts}")
    print(f"total latency    : {r.latency_ms:.0f} ms")
    shown = dict(env, data={"incident_code": env["data"]["incident_code"]} if env["data"] else None)
    print(f"envelope         : {json.dumps(shown)}")
    return {"case": label, "outcomes": r.attempt_outcomes, "attempts": r.attempts,
            "latency_ms": round(r.latency_ms, 1), "ok": env["ok"], "error": env["error"]}


if __name__ == "__main__":
    p = INTERACTIVE
    print(f"Run by {getpass.getuser()} at {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Policy: max_attempts={p.max_attempts}, timeout/attempt={p.attempt_timeout_s}s, "
          f"backoff={p.base_delay_s}s x{p.multiplier} (cap {p.max_delay_s}s)")
    results = [
        run("A: success on first attempt", ["ok"]),
        run("B: timeout on attempt 1, success on retry", ["slow", "ok"]),
        run("C: fails every attempt -> clean error", ["fail", "fail", "fail"]),
    ]
    import os
    out = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "hw05", "raw", "retry_demo.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(results, open(out, "w"), indent=2)
    print(f"\nsaved {os.path.normpath(out)}")
