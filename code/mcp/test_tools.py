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

from domain_tools import execute_tool  # noqa: E402
from fixtures import AlwaysDown, FakeRepo  # noqa: E402
from resilience import ResilientRepository, RetryPolicy  # noqa: E402


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
    env = call("search_incidents", {"category": "Delay", "limit": 500})
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
    from test_agent import TESTS as AGENT_TESTS  # noqa: E402
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
