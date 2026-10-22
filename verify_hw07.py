"""HW7 smoke test -> reports/hw07/verification.json   (make verify-hw07)

Run on the tagged commit with the backend up on PORT_BASE 8446, MySQL migrated, the three
role users created, and Ollama serving qwen2.5:3b:

    export JWT_SECRET=...  HW7_USER_PASSWORD=...  MYSQL_PASSWORD=...
    python verify_hw07.py              # live checks + the offline suite
    python verify_hw07.py --offline    # offline suite only (no server / MySQL / Ollama)

Checks are behavioural (status codes, fields, counts, stop reasons), never exact wording.
It creates one temporary incident through the API and deletes it again; it never modifies
application code (the offline suite works in a temporary directory).
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path[:0] = [str(REPO / "code"), str(REPO / "code" / "mcp"), str(REPO / "src")]
import hw07_config as cfg  # noqa: E402

BASE = f"http://127.0.0.1:{cfg.PORT_BASE}"
checks: list[dict] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    """Record + print one check."""
    checks.append({"name": name, "passed": bool(passed), "detail": str(detail)[:240]})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))


def safe(name: str, fn) -> None:
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


def live_checks() -> None:
    """Part 1 over HTTP + one real agent-loop verification task."""
    import requests
    pw = os.environ.get("HW7_USER_PASSWORD")
    if not pw:
        check("env_HW7_USER_PASSWORD_set", False, "export HW7_USER_PASSWORD (password of the 3 role users)")
        return
    s = requests.Session()

    def c_health():
        r = s.get(f"{BASE}/health", timeout=5)
        check("backend_on_port_base", r.status_code == 200 and r.json().get("port") == cfg.PORT_BASE,
              f"status={r.status_code}")
    safe("backend_on_port_base", c_health)

    tokens: dict[str, str] = {}

    def c_login():
        for u in ("reader1346", "writer1346", "moderator1346"):
            r = s.post(f"{BASE}/auth/login", json={"username": u, "password": pw}, timeout=10)
            if r.status_code == 200:
                tokens[u] = r.json()["access_token"]
        check("login_valid_returns_jwt", len(tokens) == 3 and all(t.count(".") == 2 for t in tokens.values()),
              f"{len(tokens)}/3 role users")
        r = s.post(f"{BASE}/auth/login", json={"username": "writer1346", "password": pw + "-wrong"}, timeout=10)
        check("login_invalid_401", r.status_code == 401, f"status={r.status_code}")
    safe("login", c_login)
    if len(tokens) < 3:
        return
    H = {u: {"Authorization": f"Bearer {t}"} for u, t in tokens.items()}

    def c_me():
        r = s.get(f"{BASE}/auth/me", headers=H["writer1346"], timeout=5)
        check("auth_me_identity_and_role", r.status_code == 200 and r.json().get("role") == "writer",
              f"{r.json()}")
        check("auth_me_no_token_401", s.get(f"{BASE}/auth/me", timeout=5).status_code == 401)
        bad = tokens["reader1346"][:-3] + "abc"
        check("auth_me_invalid_token_401",
              s.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {bad}"}, timeout=5).status_code == 401)
        if os.environ.get("JWT_SECRET"):
            out = subprocess.run([sys.executable, "make_token.py", "--username", "reader1346", "--minutes", "-5"],
                                 cwd=REPO / "code" / "backend", capture_output=True, text=True, timeout=60)
            exp = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""
            r = s.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {exp}"}, timeout=5)
            check("auth_me_expired_token_401", r.status_code == 401 and "expired" in r.text.lower(),
                  f"status={r.status_code}")
        else:
            check("auth_me_expired_token_401", False, "JWT_SECRET not exported - cannot mint an expired token")
    safe("auth_me", c_me)

    def c_rbac():
        body = {"route_title": "VERIFY hw07 temporary incident", "category": "Delay", "passengers_affected": 0}
        r = s.post(f"{BASE}/api/incidents", json=body, headers=H["reader1346"], timeout=10)
        check("create_as_reader_403", r.status_code == 403, f"status={r.status_code}")
        r = s.post(f"{BASE}/api/incidents", json=body, headers=H["writer1346"], timeout=10)
        check("create_as_writer_201", r.status_code == 201, f"status={r.status_code}")
        if r.status_code != 201:
            return
        iid = r.json()["id"]
        r = s.delete(f"{BASE}/api/incidents/{iid}", headers=H["writer1346"], timeout=10)
        check("delete_as_writer_403", r.status_code == 403, f"status={r.status_code}")
        r = s.delete(f"{BASE}/api/incidents/{iid}", headers=H["moderator1346"], timeout=10)
        check("delete_as_moderator_200", r.status_code in (200, 204), f"status={r.status_code}")
        r = s.get(f"{BASE}/api/incidents", params={"limit": 3}, headers=H["reader1346"], timeout=10)
        check("list_as_reader_200", r.status_code == 200 and isinstance(r.json(), list), f"items={len(r.json())}")
        check("list_without_token_401", s.get(f"{BASE}/api/incidents", timeout=5).status_code == 401)
    safe("rbac", c_rbac)

    def c_agent():
        from agent_loop.loop import run_agent
        from agent_loop.tasks import TASKS_BY_ID, verify
        from repository import SqlRepository
        repo, task = SqlRepository(), TASKS_BY_ID["A"]
        res, v = None, None
        for k in range(2):                                   # objective: pass within 2 seeded tries
            res = run_agent(task.prompt, required_tools=list(task.required_tools), seed=cfg.VERIFY_SEED + k,
                            log_path=None)
            v = verify(task, res, repo)
            if v.passed:
                break
        check("agent_loop_completes_task_A_live", v.passed and res.tool_calls >= 2,
              f"stop={res.stop_reason} tool_calls={res.tool_calls} {v.reason}")
    safe("agent_loop_completes_task_A_live", c_agent)


def offline_checks() -> None:
    """The offline suite (SQLite + scripted models) run in a subprocess, plus ruff + evidence files."""
    out = subprocess.run([sys.executable, str(REPO / "code" / "test_hw07.py")], capture_output=True, text=True,
                         timeout=600, cwd=REPO)
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("[PASS]") or line.startswith("[FAIL]"):
            name, _, detail = line[7:].partition(": ")
            check(f"offline_{name}", line.startswith("[PASS]"), detail)
    try:
        r = subprocess.run(["ruff", "check", "."], cwd=REPO, capture_output=True, text=True, timeout=120)
        check("ruff_clean", r.returncode == 0, (r.stdout.strip().splitlines() or ["ok"])[-1])
    except FileNotFoundError:
        check("ruff_clean", False, "ruff not installed")
    raw = REPO / "reports" / "hw07" / "raw"
    expected = ["part2_reliability_attempts.csv", "part3_comparison_runs.csv", "reflections.jsonl",
                "bike_scenario_summaries.json", "part5_attack_results.json", "part6_safety_gate_results.json"]
    missing = [f for f in expected if not (raw / f).exists()]
    check("raw_evidence_files_present", not missing, f"missing: {missing}" if missing else f"{len(expected)} files")
    snaps = list((raw / "pricing_snapshots").glob("*/pricing_snapshot.json"))
    check("pricing_snapshots_with_sha256", len(snaps) >= 2 and all(json.loads(p.read_text()).get("sha256") for p in snaps),
          f"{len(snaps)} snapshots")


def main() -> None:
    """Run the checks and write verification.json."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    print(f"HW7 smoke test - {cfg.STUDENT_NAME} ({cfg.PREFIX}), PORT_BASE {cfg.PORT_BASE}")
    if not a.offline:
        live_checks()
    offline_checks()
    result = {
        "homework": "HW7", "sid4": cfg.SID4, "student": cfg.STUDENT_NAME,
        "commit_hash": git("rev-parse", "HEAD"), "tag": git("describe", "--tags", "--exact-match") ,
        "model_configuration": f"{cfg.MODEL_DESCRIPTION}; agent temperature {cfg.AGENT_TEMPERATURE}, "
                               f"bike agent temperature {cfg.BIKE_TEMPERATURE}, seed {cfg.SEED}",
        "hardware": cfg.HARDWARE, "seed": cfg.SEED, "verify_seed": cfg.VERIFY_SEED, "port_base": cfg.PORT_BASE,
        "mode": "offline" if a.offline else "live+offline",
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "checks": checks,
        "summary": {"passed": sum(c["passed"] for c in checks), "total": len(checks)},
    }
    path = REPO / "reports" / "hw07" / "verification.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    print(f"{result['summary']['passed']}/{result['summary']['total']} checks passed -> {path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
