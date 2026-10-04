"""HW5 Part 4 - offline test runner for the s1346_rel tool layer.

  python code/mcp/test_tools.py

No MySQL, no network, no LLM, no API key: every test injects an in-memory
FakeRepo into execute_tool (dependency injection), so the suite is fast,
offline, and gives the same result every run.
"""
import getpass
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from domain_tools import execute_tool                               # noqa: E402
from resilience import RetryPolicy, ResilientRepository, TransientError  # noqa: E402

# ---- fixtures ---------------------------------------------------------------
INCIDENTS = [
    {"id": 1, "incident_code": "INC-000001", "route_title": "Route 5 - 15 min delay at Main St",
     "category": "Delay", "passengers_affected": 35, "line_code": "L-005"},
    {"id": 2, "incident_code": "INC-000002", "route_title": "Route 5 - Breakdown at Oak St",
     "category": "Breakdown", "passengers_affected": 20, "line_code": "L-005"},
    {"id": 3, "incident_code": "INC-000003", "route_title": "Route 6 - Detour on Pine St",
     "category": "Service Change", "passengers_affected": 0, "line_code": "L-006"},
]
LINES = {"L-005": ("Route 5 - Harbor", "Bus"), "L-006": ("Route 6 - Uptown", "Bus")}


class FakeRepo:
    """Same interface as SqlRepository, backed by the lists above."""
    def __init__(self):
        self.calls = 0

    def search_incidents(self, category, line_code, text_query, limit):
        self.calls += 1
        rows = [r for r in INCIDENTS
                if (category is None or r["category"] == category)
                and (line_code is None or r["line_code"] == line_code)
                and (text_query is None or text_query.lower() in r["route_title"].lower())]
        return sorted(rows, key=lambda r: -r["id"])[:limit]

    def get_incident(self, code):
        self.calls += 1
        for r in INCIDENTS:
            if r["incident_code"] == code:
                name, mode = LINES[r["line_code"]]
                return dict(r, line_name=name, line_mode=mode)
        return None

    def line_exists(self, code):
        self.calls += 1
        return code in LINES

    def category_stats(self, line_code):
        self.calls += 1
        out = {}
        for r in INCIDENTS:
            if line_code is None or r["line_code"] == line_code:
                c = out.setdefault(r["category"], {"category": r["category"], "incidents": 0,
                                                   "passengers_affected": 0})
                c["incidents"] += 1
                c["passengers_affected"] += r["passengers_affected"]
        return sorted(out.values(), key=lambda c: -c["incidents"])


class AlwaysDown:
    """Every storage call fails with a transient error."""
    def __getattr__(self, name):
        def boom(*a, **k):
            raise TransientError("database unreachable (simulated)")
        return boom


def call(name, inputs, repo=None):
    """execute_tool returns a JSON string; decode it so tests can check fields."""
    raw = execute_tool(name, inputs, repo=repo if repo is not None else FakeRepo())
    assert isinstance(raw, str), "execute_tool must return a JSON string"
    env = json.loads(raw)
    assert set(env) == {"ok", "data", "error"}, f"bad envelope keys {set(env)}"
    return env


# ---- tests -------------------------------------------------------------------
def test_search_valid():
    env = call("search_incidents", {"category": "Delay", "line_code": "L-005", "limit": 5})
    assert env["ok"] is True and env["error"] is None
    assert env["data"]["count"] == 1
    assert env["data"]["results"][0]["incident_code"] == "INC-000001"


def test_search_invalid_category():                       # Part 2B/3 rejected call
    repo = FakeRepo()
    env = call("search_incidents", {"category": "Flood", "limit": 10}, repo)
    assert env["ok"] is False and env["data"] is None
    assert "category must be one of" in env["error"]
    assert repo.calls == 0, "invalid input must be rejected before storage"


def test_search_invalid_limit():
    env = call("search_incidents", {"limit": 500})
    assert env["ok"] is False and "limit must be an integer from 1 to 50" in env["error"]


def test_get_incident_valid():
    env = call("get_incident", {"incident_code": "INC-000002"})
    assert env["ok"] is True
    assert env["data"]["category"] == "Breakdown" and env["data"]["line_name"] == "Route 5 - Harbor"


def test_get_incident_invalid_format():                   # Part 2B/3 rejected call
    repo = FakeRepo()
    env = call("get_incident", {"incident_code": "INC-12"}, repo)
    assert env["ok"] is False and "must look like 'INC-000123'" in env["error"]
    assert repo.calls == 0


def test_get_incident_not_found():
    env = call("get_incident", {"incident_code": "INC-999999"})
    assert env["ok"] is False and env["error"] == "incident INC-999999 not found"


def test_stats_valid():
    env = call("incident_stats", {"line_code": "L-005"})
    assert env["ok"] is True
    assert env["data"]["total_incidents"] == 2
    assert env["data"]["total_passengers_affected"] == 55


def test_stats_invalid_line_code():                       # Part 2B/3 rejected call
    repo = FakeRepo()
    env = call("incident_stats", {"line_code": "Line5"}, repo)
    assert env["ok"] is False and "must look like 'L-005'" in env["error"]
    assert repo.calls == 0


def test_unknown_tool_and_bad_json_do_not_crash():
    assert call("drop_tables", {})["ok"] is False
    assert call("search_incidents", "{not json")["ok"] is False


def test_retries_exhausted_returns_clean_error():
    fast = RetryPolicy(max_attempts=3, attempt_timeout_s=1.0, base_delay_s=0.0, max_delay_s=0.0)
    env = call("get_incident", {"incident_code": "INC-000001"},
               ResilientRepository(AlwaysDown(), fast))
    assert env["ok"] is False and "failed after 3 attempt(s)" in env["error"]


TESTS = [test_search_valid, test_search_invalid_category, test_search_invalid_limit,
         test_get_incident_valid, test_get_incident_invalid_format, test_get_incident_not_found,
         test_stats_valid, test_stats_invalid_line_code,
         test_unknown_tool_and_bad_json_do_not_crash, test_retries_exhausted_returns_clean_error]

# Part 5 adds its tests here (safety rule + agent max_steps).
try:
    from test_agent import TESTS as AGENT_TESTS              # noqa: E402
    TESTS += AGENT_TESTS
except ImportError:
    pass


def main():
    import logging
    logging.disable(logging.CRITICAL)                       # keep output to PASS/FAIL lines
    print(f"s1346 tool tests - run by {getpass.getuser()} (offline: FakeRepo, no DB/LLM/network)\n")
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"PASS  {t.__name__}")
        except Exception as e:                              # noqa: BLE001
            print(f"FAIL  {t.__name__}: {e.__class__.__name__}: {e}")
            if os.getenv("VERBOSE"):
                traceback.print_exc()
    print(f"\n{passed}/{len(TESTS)} tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
