"""The one response envelope used by every domain tool (Part 2B), execute_tool
(Part 4) and the agent loop (Part 5):  {"ok": bool, "data": ..., "error": str | None}."""
import json
from typing import Any


def ok(data: Any) -> dict:
    return {"ok": True, "data": data, "error": None}


def fail(error: str) -> dict:
    return {"ok": False, "data": None, "error": error}


def to_json(envelope: dict) -> str:
    return json.dumps(envelope, default=str)
