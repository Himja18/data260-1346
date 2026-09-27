"""HW4 smoke-test verification script. Writes reports/hw04/verification.json."""
import json, subprocess, sys, time
from datetime import datetime
from pathlib import Path
import requests

REPO = Path(__file__).resolve().parent
PORT = 8446
BASE = f"http://127.0.0.1:{PORT}"
SID4 = 1346
SEED = 1346
VERIFY_SEED = 261346

def git_commit():
    try:
        return subprocess.check_output(
            ["git","rev-parse","HEAD"], cwd=REPO).decode().strip()
    except Exception:
        return "UNKNOWN"

checks = []

def check(name, passed, detail=""):
    checks.append({"name": name, "passed": passed, "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))

print("Running HW4 smoke tests...")

# 1. Backend responds
try:
    r = requests.get(f"{BASE}/health", timeout=5)
    check("fastapi_backend_responds", r.status_code == 200)
except Exception as e:
    check("fastapi_backend_responds", False, str(e))

# 2. Login works
cookie = None
try:
    r = requests.post(f"{BASE}/api/auth/login",
        json={"email":"dispatcher1346@transit.test","password":"TransitLine22!"},
        timeout=5)
    check("login_returns_200", r.status_code == 200)
    cookie = r.cookies
except Exception as e:
    check("login_returns_200", False, str(e))

# 3. Incidents list returns data
try:
    r = requests.get(f"{BASE}/api/incidents", cookies=cookie, timeout=5)
    data = r.json()
    check("incidents_list_returns_data",
          r.status_code == 200 and isinstance(data, list) and len(data) > 0,
          f"{len(data)} incidents")
except Exception as e:
    check("incidents_list_returns_data", False, str(e))

# 4. Naive endpoint returns N+1 SQL count
try:
    r = requests.get(f"{BASE}/api/incidents/naive",
        params={"limit":10}, cookies=cookie, timeout=10)
    body = r.json()
    sql = body.get("sql_statements", 0)
    check("naive_endpoint_n_plus_1",
          r.status_code == 200 and sql == 11,
          f"sql_statements={sql}")
except Exception as e:
    check("naive_endpoint_n_plus_1", False, str(e))

# 5. Fixed endpoint returns 1 SQL statement
try:
    r = requests.get(f"{BASE}/api/incidents/fixed",
        params={"limit":10}, cookies=cookie, timeout=10)
    body = r.json()
    sql = body.get("sql_statements", 0)
    check("fixed_endpoint_one_query",
          r.status_code == 200 and sql == 1,
          f"sql_statements={sql}")
except Exception as e:
    check("fixed_endpoint_one_query", False, str(e))

# 6. Raw measurement file exists with 180 rows
try:
    import csv
    raw = REPO / "reports/hw04/raw/n1_raw.csv"
    rows = list(csv.DictReader(open(raw)))
    check("raw_180_requests_saved",
          len(rows) == 180, f"{len(rows)} rows")
except Exception as e:
    check("raw_180_requests_saved", False, str(e))

# 7. RAG results file exists
try:
    rag = REPO / "reports/hw04/raw/rag_results.json"
    data = json.load(open(rag))
    check("rag_results_saved", len(data) >= 6, f"{len(data)} results")
except Exception as e:
    check("rag_results_saved", False, str(e))

# 8. Transit lines seeded
try:
    r = requests.get(f"{BASE}/api/incidents/fixed",
        params={"limit":1}, cookies=cookie, timeout=10)
    item = r.json()["items"][0]
    check("transit_lines_seeded",
          item.get("line") is not None,
          f"line={item.get('line',{}).get('code','?')}")
except Exception as e:
    check("transit_lines_seeded", False, str(e))

all_passed = all(c["passed"] for c in checks)
report = {
    "homework": "HW4",
    "sid4": SID4,
    "commit_hash": git_commit(),
    "seed": SEED,
    "verify_seed": VERIFY_SEED,
    "model_configuration": "qwen2.5:3b via Ollama",
    "timestamp": datetime.now().isoformat(),
    "checks": checks,
    "all_passed": all_passed,
}
out = REPO / "reports/hw04/verification.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2))
print(f"\nOverall: {'PASS' if all_passed else 'FAIL'}")
print(f"Saved to {out}")
