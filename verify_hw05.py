"""HW5 smoke test. Writes reports/hw05/verification.json.

  python verify_hw05.py          (backend running on 8446, MYSQL_PASSWORD set, Ollama up)

Behaviour checks only (status codes, envelope fields, counts) - never exact wording.
Reads the app and the report files; never modifies application code. Temporary
records it creates through the API (one transit line) are deleted again.
"""
import asyncio
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent
MCP_DIR = REPO / "code" / "mcp"
RAW = REPO / "reports" / "hw05" / "raw"
SID4, SEED, VERIFY_SEED = 1346, 1346, 261346
PORT = 8000 + SID4 % 900                     # 8446
BASE = f"http://127.0.0.1:{PORT}"
MODEL = "qwen2.5:3b via Ollama (temperature 0, seed 1346)"
LOGIN = {"email": "dispatcher1346@transit.test", "password": os.getenv("APP_PASSWORD", "TransitLine22!")}

sys.path.insert(0, str(MCP_DIR))
checks = []


def check(name, passed, detail=""):
    checks.append({"name": name, "passed": bool(passed), "detail": str(detail)[:200]})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))


def safe(name, fn):
    try:
        fn()
    except Exception as e:                                       # noqa: BLE001
        check(name, False, f"{e.__class__.__name__}: {e}")


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()
    except Exception:
        return "UNKNOWN"


print(f"Running HW5 smoke tests (PORT_BASE={PORT}) ...")
s = requests.Session()


# ---- Part 1: FastAPI + MySQL ---------------------------------------------------
def c_health():
    r = s.get(f"{BASE}/health", timeout=5)
    check("backend_responds_on_port_base", r.status_code == 200 and r.json().get("port") == PORT,
          f"status={r.status_code}")


def c_login():
    r = s.post(f"{BASE}/api/auth/login", json=LOGIN, timeout=5)
    check("login_returns_200", r.status_code == 200, f"status={r.status_code}")


def c_lines_crud_and_relationship():
    r = s.get(f"{BASE}/api/lines", params={"limit": 2, "offset": 0}, timeout=5)
    body = r.json()
    check("lines_list_paginated", r.status_code == 200 and {"total", "items"} <= set(body)
          and len(body["items"]) <= 2, f"total={body.get('total')}")
    first = body["items"][0]["id"]
    r = s.get(f"{BASE}/api/lines/{first}/incidents", params={"limit": 3}, timeout=5)
    check("relationship_query_returns_incidents",
          r.status_code == 200 and all("incident_code" in i for i in r.json()["items"]),
          f"line {first}: total={r.json().get('total')}")
    # temp line: create -> duplicate 409 -> bad format 422 -> delete
    code = f"L-{900 + int(time.time()) % 99:03d}"
    r = s.post(f"{BASE}/api/lines", json={"code": code, "name": "Verify temp line", "mode": "Bus"}, timeout=5)
    created = r.status_code == 201
    tmp_id = r.json().get("id") if created else None
    dup = s.post(f"{BASE}/api/lines", json={"code": code, "name": "Dup", "mode": "Bus"}, timeout=5).status_code
    bad = s.post(f"{BASE}/api/lines", json={"code": "201", "name": "Bad", "mode": "Bus"}, timeout=5).status_code
    gone = s.delete(f"{BASE}/api/lines/{tmp_id}", timeout=5).status_code if tmp_id else None
    check("line_create_201_dup_409_format_422_delete_200",
          created and dup == 409 and bad == 422 and gone == 200, f"dup={dup} bad={bad} delete={gone}")


def c_delete_protection():
    r = s.get(f"{BASE}/api/incidents", params={"limit": 50}, timeout=5)
    line_id = next(i["line_id"] for i in r.json() if i["line_id"])
    r = s.delete(f"{BASE}/api/lines/{line_id}", timeout=5)
    check("delete_line_with_incidents_blocked_409", r.status_code == 409, f"line {line_id}")


def c_missing_404():
    check("missing_line_404", s.get(f"{BASE}/api/lines/999999", timeout=5).status_code == 404)


for n, f in [("backend_responds_on_port_base", c_health), ("login_returns_200", c_login),
             ("lines_crud", c_lines_crud_and_relationship), ("delete_protection", c_delete_protection),
             ("missing_line_404", c_missing_404)]:
    safe(n, f)


# ---- Part 2: both MCP servers start and answer a tool call (over STDIO) --------
async def mcp_probe(script, call_name, call_args):
    from mcp.client.stdio import stdio_client

    from mcp import ClientSession, StdioServerParameters
    params = StdioServerParameters(command=sys.executable, args=[str(MCP_DIR / script)],
                                   env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()
            tools = [t.name for t in (await sess.list_tools()).tools]
            res = await sess.call_tool(call_name, call_args)
            return tools, res


def c_meals():
    tools, res = asyncio.run(asyncio.wait_for(
        mcp_probe("meals_server.py", "search_meals_by_name", {"query": "Arrabiata", "limit": 2}), 60))
    expected = {"search_meals_by_name", "meals_by_ingredient", "meal_details", "random_meal"}
    check("meals_server_lists_4_tools", set(tools) == expected, tools)
    text = res.content[0].text if res.content else ""
    if res.isError:   # no internet is still a clean, answered tool call
        check("meals_server_answers_tool_call", "TheMealDB" in text or "Network" in text, "clean error (offline?)")
    else:
        data = json.loads(text)
        check("meals_server_answers_tool_call",
              "results" in data and all({"id", "name", "area", "category", "thumb"} <= set(m) for m in data["results"]),
              f"{data.get('count')} result(s)")


def c_domain():
    tools, res = asyncio.run(asyncio.wait_for(
        mcp_probe("domain_server.py", "incident_stats", {"line_code": "L-005"}), 60))
    check("domain_server_lists_3_tools",
          set(tools) == {"search_incidents", "get_incident", "incident_stats"}, tools)
    env = json.loads(res.content[0].text)
    check("domain_server_tool_call_envelope_ok",
          set(env) == {"ok", "data", "error"} and env["ok"] is True and env["error"] is None,
          f"total_incidents={env['data']['total_incidents'] if env['ok'] else env['error']}")
    tools, res = asyncio.run(asyncio.wait_for(
        mcp_probe("domain_server.py", "get_incident", {"incident_code": "INC-12"}), 60))
    env = json.loads(res.content[0].text)
    check("domain_server_rejects_invalid_input", env["ok"] is False and env["data"] is None and env["error"])


safe("meals_server", c_meals)
safe("domain_server", c_domain)


# ---- Part 3: raw data + reproducibility ---------------------------------------
def c_fault_raw():
    rows = list(csv.DictReader(open(RAW / "fault_injection_calls.csv")))
    per_rate = {r: sum(1 for x in rows if float(x["failure_rate"]) == r) for r in (0.0, 0.2, 0.5)}
    check("fault_injection_150_records", len(rows) == 150 and set(per_rate.values()) == {50}, per_rate)


def c_reproducible():
    import random
    summary = json.load(open(RAW / "fault_injection_summary.json"))
    ok = summary["verify_seed"] == VERIFY_SEED
    for r in summary["rates"]:
        rate = float(r["failure_rate"].rstrip("%")) / 100
        rng = random.Random(VERIFY_SEED)
        seq = "".join("F" if rng.random() < rate else "." for _ in range(r["draws"]))
        import hashlib
        ok &= hashlib.sha256(seq.encode()).hexdigest()[:16] == r["sequence_sha256"]
    check("fault_sequence_reproducible_from_verify_seed", ok, "replayed all 3 rates")


def c_retry_policy():
    from domain_tools import run_tool
    from resilience import ResilientRepository, RetryPolicy, TransientError

    class Flaky:
        def __init__(self): self.n = 0
        def category_stats(self, line_code):
            self.n += 1
            if self.n == 1:
                raise TransientError("simulated")
            return []
        def line_exists(self, c): return True
    fast = RetryPolicy(base_delay_s=0.0, max_delay_s=0.0, attempt_timeout_s=2.0)
    repo = ResilientRepository(Flaky(), fast)
    env = run_tool("incident_stats", {}, repo=repo)
    check("retry_recovers_after_transient_failure", env["ok"] and repo.last_report.attempts == 2)


for n, f in [("fault_injection_150_records", c_fault_raw),
             ("fault_sequence_reproducible_from_verify_seed", c_reproducible),
             ("retry_recovers_after_transient_failure", c_retry_policy)]:
    safe(n, f)


# ---- Part 4/5: offline test suite, safety rule, agent log ---------------------
def c_suite():
    out = subprocess.run([sys.executable, str(MCP_DIR / "test_tools.py")], capture_output=True,
                         text=True, timeout=120, cwd=REPO).stdout
    last = out.strip().splitlines()[-1]
    x, y = last.split()[0].split("/")
    check("offline_test_suite_all_pass", x == y and int(y) >= 8, last)


def c_safety():
    from domain_tools import execute_tool
    env = json.loads(execute_tool("search_incidents", {"limit": 50}, repo=object()))
    check("safety_rule_blocks_unscoped_bulk_search", env["ok"] is False and env["data"] is None
          and "safety" in env["error"])


def c_agent_log():
    events = [json.loads(line) for line in open(RAW / "agent_runs.jsonl")]
    stops = {e["stop_reason"] for e in events if e["event"] == "stop"}
    runs = len({e["run_id"] for e in events if e["event"] == "stop" and e.get("model") != "mock"})
    check("agent_log_has_all_stop_reasons", {"completed", "safety_block", "max_steps"} <= stops,
          f"{runs} logged runs, stop reasons={sorted(stops)}")


def c_ollama():
    r = requests.get("http://localhost:11434/api/tags", timeout=5)
    names = [m["name"] for m in r.json().get("models", [])]
    check("ollama_model_available", "qwen2.5:3b" in names, names)


for n, f in [("offline_test_suite_all_pass", c_suite), ("safety_rule", c_safety),
             ("agent_log", c_agent_log), ("ollama_model_available", c_ollama)]:
    safe(n, f)

report = {
    "homework": "HW5",
    "sid4": SID4,
    "commit_hash": git_commit(),
    "model_configuration": MODEL,
    "seed": SEED,
    "verify_seed": VERIFY_SEED,
    "port_base": PORT,
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "checks": checks,
    "summary": f"{sum(c['passed'] for c in checks)}/{len(checks)} passed",
    "all_passed": all(c["passed"] for c in checks),
}
out = REPO / "reports" / "hw05" / "verification.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2))
print(f"\n{report['summary']}  ->  {out.relative_to(REPO)}")
