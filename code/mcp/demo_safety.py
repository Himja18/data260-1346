"""HW5 Part 5.I - safety rule demo: one allowed call, one blocked call (offline).
  python code/mcp/demo_safety.py"""
import getpass
import json
import logging

from domain_tools import execute_tool
from fixtures import FakeRepo

logging.disable(logging.CRITICAL)
print(f"Safety rule demo - run by {getpass.getuser()}")
print("Rule: a search with no category/line_code/text filter may return at most 10 rows.\n")
repo = FakeRepo()
for label, inputs in [("ALLOWED (scoped by category)", {"category": "Delay", "limit": 50}),
                      ("BLOCKED (unscoped bulk export)", {"limit": 50})]:
    out = json.loads(execute_tool("search_incidents", inputs, repo))
    if out["ok"]:
        out = dict(out, data={"count": out["data"]["count"], "...": "results omitted"})
    print(f"{label}\n  execute_tool('search_incidents', {json.dumps(inputs)})\n  -> {json.dumps(out)}\n")
print(f"storage calls made: {repo.calls} (the blocked call never reached the database)")
