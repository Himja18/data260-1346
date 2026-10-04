"""HW5 Part 5.III - the two extra offline tests (picked up by test_tools.py).
No API key, live model, external API or database: FakeRepo + MockModel."""
import json
import os
import tempfile

from agent import MockModel, run_agent
from domain_tools import execute_tool
from fixtures import FakeRepo


def test_execute_tool_blocks_safety_violation():
    repo = FakeRepo()
    allowed = json.loads(execute_tool("search_incidents", {"category": "Delay", "limit": 50}, repo))
    assert allowed["ok"] is True, "scoped search with a large limit is allowed"
    calls_before = repo.calls
    blocked = json.loads(execute_tool("search_incidents", {"limit": 50}, repo))
    assert blocked == {"ok": False, "data": None, "error": blocked["error"]}
    assert blocked["error"].startswith("blocked by safety rule")
    assert repo.calls == calls_before, "blocked call must never reach storage"


def test_run_agent_stops_at_max_steps():
    model = MockModel([{"tool": "incident_stats", "arguments": {"line_code": "L-005"}}])  # never answers
    with tempfile.TemporaryDirectory() as d:
        log_path = os.path.join(d, "agent_runs.jsonl")
        result = run_agent("loop forever", model=model, max_steps=3, repo=FakeRepo(), log_path=log_path)
        events = [json.loads(line) for line in open(log_path)]
    assert result["stop_reason"] == "max_steps"
    assert result["steps"] == 3 and result["tool_calls"] == 3
    assert events[-1]["event"] == "stop" and events[-1]["stop_reason"] == "max_steps"
    assert sum(e["event"] == "tool_call" for e in events) == 3


TESTS = [test_execute_tool_blocks_safety_violation, test_run_agent_stops_at_max_steps]
