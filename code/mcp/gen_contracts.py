"""HW5 Part 3.1 - write the tool-contract table for the Part 2B rejected calls.
Runs the real validation (no DB needed: invalid input is rejected before storage).
  python code/mcp/gen_contracts.py  ->  reports/hw05/PART3_CONTRACTS.md
                                        reports/hw05/raw/inspector_rejected_calls.json
"""
import json
import os

from domain_tools import SCHEMAS, run_tool

CASES = [
    ("search_incidents", {"category": "Flood", "limit": 10},
     "`category` is an enum. 'Flood' is not one of Delay / Breakdown / Accident / Service Change, "
     "so validation rejects it before any query runs."),
    ("get_incident", {"incident_code": "INC-12"},
     "`incident_code` must match ^INC-\\d{6}$ (six digits). 'INC-12' has two, so it fails the "
     "format check; the database is never queried."),
    ("incident_stats", {"line_code": "Line5"},
     "`line_code` must match ^L-\\d{3}$. 'Line5' is a free-text name, not a line code, so the "
     "pattern check rejects it."),
]


class NoDB:                       # proves rejection happens before storage
    def __getattr__(self, name):
        raise AssertionError("storage must not be reached for invalid input")


root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
out_md = os.path.join(root, "reports", "hw05", "PART3_CONTRACTS.md")
out_json = os.path.join(root, "reports", "hw05", "raw", "inspector_rejected_calls.json")
os.makedirs(os.path.dirname(out_json), exist_ok=True)

lines = ["# Part 3.1 - Tool contracts and the Part 2B rejected calls", "",
         "All three tools return the same envelope `{ok, data, error}`. A rejected call is still a",
         "successful MCP call (the Inspector shows *Tool Result: Success*); the rejection is",
         "carried inside the envelope as `ok: false` with a message naming the broken rule.", ""]
records = []
for name, bad, why in CASES:
    env = run_tool(name, bad, repo=NoDB())
    assert env["ok"] is False and env["data"] is None
    records.append({"tool": name, "schema": SCHEMAS[name], "rejected_input": bad, "output": env, "why": why})
    lines += [f"## {name}", "", "**Expected input schema**", "```json",
              json.dumps(SCHEMAS[name], indent=2), "```", "",
              "**Rejected input**", "```json", json.dumps(bad), "```", "",
              "**Returned output**", "```json", json.dumps(env, indent=2), "```", "",
              f"**Why it was rejected:** {why}", ""]
open(out_md, "w").write("\n".join(lines))
json.dump(records, open(out_json, "w"), indent=2)
print(f"wrote {out_md}\nwrote {out_json}")
