"""
code/verify_hw02.py — DATA-260 HW2 smoke test

Runs a small set of objective, behavior-based checks (not exact-text
checks, since the local model is non-deterministic) against the tagged
commit, and writes reports/hw02/verification.json.

Checks:
  1. FastAPI backend responds on PORT_BASE (8446) with a 200 on GET /
  2. FastAPI /api/incidents returns a JSON list
  3. The LangGraph pipeline (code/agents_graph.py) finishes within a
     bounded time instead of hanging, for a fixed low turn ceiling
  4. The Planner's finalized output always has exactly 3 tags (schema
     safety net enforced regardless of what the model returns)

Usage:
    python code/verify_hw02.py --commit <full-git-commit-hash>

If --commit is omitted, the script tries `git rev-parse HEAD`.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "code" / "backend"
REPORTS_DIR = REPO_ROOT / "reports" / "hw02"

PORT_BASE = 8446
SID4 = 1346
SEED = 1346
VERIFY_SEED = 261346
MODEL_NAME = "qwen2.5:3b"


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT
        ).decode().strip()
    except Exception:
        return "UNKNOWN"


def check_backend() -> dict:
    """Start the FastAPI backend as a subprocess, hit two endpoints, then
    stop it. Returns a dict with pass/fail per sub-check."""
    result = {
        "name": "fastapi_backend_responds",
        "checks": {},
        "passed": False,
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", "0.0.0.0", "--port", str(PORT_BASE)],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Give the server a few seconds to come up.
        started = False
        for _ in range(20):
            time.sleep(0.5)
            try:
                r = requests.get(f"http://127.0.0.1:{PORT_BASE}/", timeout=1)
                if r.status_code == 200:
                    started = True
                    break
            except requests.exceptions.ConnectionError:
                continue

        result["checks"]["home_page_200"] = started

        try:
            r = requests.get(f"http://127.0.0.1:{PORT_BASE}/api/incidents", timeout=2)
            result["checks"]["incidents_endpoint_returns_list"] = (
                r.status_code == 200 and isinstance(r.json(), list)
            )
        except Exception:
            result["checks"]["incidents_endpoint_returns_list"] = False

        result["passed"] = all(result["checks"].values())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    return result

def check_graph_finishes() -> dict:
    """Confirm the LangGraph pipeline terminates within a bounded number
    of turns instead of hanging, using a real (small) turn ceiling."""
    sys.path.insert(0, str(REPO_ROOT / "code"))
    import agents_graph as ag

    result = {"name": "langgraph_finishes_not_hanging", "checks": {}, "passed": False}

    start = time.time()
    try:
        out = ag.run_once(
            "Line 22 - Bus stalled on Main St",
            "The 8:15 AM bus on Route 22 broke down near Main St and 5th Ave.",
            turn_ceiling=4,
            verbose=False,
        )
        elapsed = time.time() - start
        result["checks"]["returned_within_120s"] = elapsed < 120
        result["checks"]["turn_count_within_ceiling"] = out["turn_count"] <= 4
        result["checks"]["has_outcome_field"] = "outcome" in out
        result["elapsed_seconds"] = round(elapsed, 1)
        result["passed"] = all(result["checks"].values())
    except Exception as e:
        result["checks"]["error"] = str(e)
        result["passed"] = False

    return result

def check_schema_exactly_three_tags() -> dict:
    """Confirm the finalize() safety net always yields exactly 3 tags,
    regardless of what the (non-deterministic) model returns -- this is a
    behavior check, not an exact-text check."""
    sys.path.insert(0, str(REPO_ROOT / "code"))
    import agents_graph as ag

    result = {"name": "finalized_output_has_exactly_3_tags", "checks": {}, "passed": False}

    # Under-filled Reviewer output (2 tags) should be backfilled from the
    # Planner's proposal to reach exactly 3.
    reviewer_output = {"tags": ["OnlyOne", "OnlyTwo"], "summary": "short summary"}
    planner_output = {"tags": ["OnlyOne", "OnlyTwo", "Backfilled", "Extra"], "summary": "short summary"}
    final = ag.finalize(reviewer_output, planner_output)

    result["checks"]["exactly_3_tags"] = len(final["tags"]) == 3
    result["checks"]["backfilled_from_planner"] = "Backfilled" in final["tags"]
    result["passed"] = all(result["checks"].values())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", type=str, default=None)
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    commit = args.commit or get_git_commit()

    print("Running HW2 smoke tests...")
    checks = [
        check_backend(),
        check_graph_finishes(),
        check_schema_exactly_three_tags(),
    ]

    for c in checks:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['name']}")

    report = {
        "homework": "HW2",
        "sid4": SID4,
        "commit_hash": commit,
        "model_configuration": MODEL_NAME,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "checks": checks,
        "all_passed": all(c["passed"] for c in checks),
    }

    out_path = REPORTS_DIR / "verification.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nSaved verification report to {out_path}")
    print(f"Overall: {'PASS' if report['all_passed'] else 'FAIL'}")


if __name__ == "__main__":
    main()