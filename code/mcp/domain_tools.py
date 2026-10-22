"""s1346_rel domain tools: one search, one detail lookup, one aggregate.

Every tool takes plain inputs, validates them, and returns the shared
envelope {ok, data, error}. Invalid input never raises; it returns ok=False
with a message saying exactly what was wrong.

execute_tool(name, inputs) is the single entry point (Part 4/5).
"""
import json
import logging
import re
import sys
from collections.abc import Callable
from typing import Any

from envelope import fail, ok, to_json
from resilience import RetriesExhausted

log = logging.getLogger("s1346_rel")
if not log.handlers:                      # stderr only (STDIO-safe)
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s s1346_rel: %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

CATEGORIES = ("Delay", "Breakdown", "Accident", "Service Change")
LINE_CODE_RE = re.compile(r"^L-\d{3}$")
INCIDENT_CODE_RE = re.compile(r"^INC-\d{6}$")
MAX_LIMIT = 50

# Input schemas (documented in the report for Part 3).
SCHEMAS: dict[str, dict] = {
    "search_incidents": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": list(CATEGORIES)},
            "line_code": {"type": "string", "pattern": LINE_CODE_RE.pattern},
            "text": {"type": "string", "minLength": 2, "maxLength": 100},
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": 10},
        },
        "additionalProperties": False,
    },
    "get_incident": {
        "type": "object",
        "properties": {"incident_code": {"type": "string", "pattern": INCIDENT_CODE_RE.pattern}},
        "required": ["incident_code"],
        "additionalProperties": False,
    },
    "incident_stats": {
        "type": "object",
        "properties": {"line_code": {"type": "string", "pattern": LINE_CODE_RE.pattern}},
        "additionalProperties": False,
    },
}


class InvalidInput(ValueError):
    pass


def _opt_str(inputs: dict, key: str) -> str | None:
    v = inputs.get(key)
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        raise InvalidInput(f"'{key}' must be a string, got {type(v).__name__}")
    return v.strip()


def _check_keys(name: str, inputs: dict):
    if not isinstance(inputs, dict):
        raise InvalidInput("inputs must be a JSON object")
    allowed = set(SCHEMAS[name]["properties"])
    extra = set(inputs) - allowed
    if extra:
        raise InvalidInput(f"unknown field(s) {sorted(extra)}; allowed: {sorted(allowed)}")


def _line_code(inputs: dict) -> str | None:
    code = _opt_str(inputs, "line_code")
    if code is not None and not LINE_CODE_RE.match(code):
        raise InvalidInput(f"line_code must look like 'L-005' (pattern ^L-\\d{{3}}$), got '{code}'")
    return code


# ---- tools (repo is injected) ---------------------------------------------
def search_incidents(repo, inputs: dict) -> dict:
    _check_keys("search_incidents", inputs)
    category = _opt_str(inputs, "category")
    if category is not None and category not in CATEGORIES:
        raise InvalidInput(f"category must be one of {list(CATEGORIES)}, got '{category}'")
    line_code = _line_code(inputs)
    text_q = _opt_str(inputs, "text")
    if text_q is not None and not 2 <= len(text_q) <= 100:
        raise InvalidInput("text must be 2-100 characters")
    limit = inputs.get("limit", 10)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise InvalidInput(f"limit must be an integer from 1 to {MAX_LIMIT}, got {limit!r}")
    rows = repo.search_incidents(category, line_code, text_q, limit)
    return ok({"count": len(rows), "results": rows})


def get_incident(repo, inputs: dict) -> dict:
    _check_keys("get_incident", inputs)
    code = _opt_str(inputs, "incident_code")
    if code is None:
        raise InvalidInput("incident_code is required")
    if not INCIDENT_CODE_RE.match(code):
        raise InvalidInput(f"incident_code must look like 'INC-000123' (pattern ^INC-\\d{{6}}$), got '{code}'")
    row = repo.get_incident(code)
    if row is None:
        return fail(f"incident {code} not found")
    return ok(row)


def incident_stats(repo, inputs: dict) -> dict:
    _check_keys("incident_stats", inputs)
    line_code = _line_code(inputs)
    if line_code and not repo.line_exists(line_code):
        return fail(f"transit line {line_code} not found")
    by_cat = repo.category_stats(line_code)
    return ok({
        "scope": line_code or "all lines",
        "total_incidents": sum(r["incidents"] for r in by_cat),
        "total_passengers_affected": sum(r["passengers_affected"] for r in by_cat),
        "by_category": by_cat,
    })


TOOLS: dict[str, Callable[[Any, dict], dict]] = {
    "search_incidents": search_incidents,
    "get_incident": get_incident,
    "incident_stats": incident_stats,
}

_default_repo = None


def get_repo():
    global _default_repo
    if _default_repo is None:
        from repository import SqlRepository
        from resilience import ResilientRepository
        _default_repo = ResilientRepository(SqlRepository())   # Part 3: timeout + retries
    return _default_repo


def run_tool(name: str, inputs: dict | None, repo=None) -> dict:
    """Run one tool and always return an envelope dict (never raises)."""
    inputs = {} if inputs is None else inputs
    if isinstance(inputs, str):                  # agents sometimes send a JSON string
        try:
            inputs = json.loads(inputs) if inputs.strip() else {}
        except ValueError:
            return fail("invalid input: inputs is not valid JSON")
    if name not in TOOLS:
        return fail(f"unknown tool '{name}'; available: {sorted(TOOLS)}")
    try:
        result = TOOLS[name](repo if repo is not None else get_repo(), inputs)
    except InvalidInput as e:                      # bad input: never retried
        result = fail(f"invalid input: {e}")
    except RetriesExhausted as e:                  # Part 3: all retries used -> clean error
        result = fail(f"{name} unavailable: {e}")
    except Exception as e:                         # anything else: still no crash
        log.exception("tool %s failed", name)
        result = fail(f"{name} failed: {e.__class__.__name__}: {str(e).splitlines()[0][:200]}")
    log.info("%s %s -> ok=%s", name, inputs, result["ok"])
    return result


# ---- Part 5: domain safety rule -----------------------------------------------
UNSCOPED_ROW_CAP = 10


def safety_check(name: str, inputs) -> str | None:
    """Business rule: no bulk export of the incident log.
    A search with no filter (no category, line_code or text) may return at most
    10 rows. Larger pulls must be scoped, so an agent can't dump the whole
    5,000-row log in one call. Returns the reason if blocked, else None."""
    if name != "search_incidents" or not isinstance(inputs, dict):
        return None
    scoped = any(inputs.get(k) not in (None, "") for k in ("category", "line_code", "text"))
    limit = inputs.get("limit", 10)
    if not scoped and isinstance(limit, int) and limit > UNSCOPED_ROW_CAP:
        return (f"blocked by safety rule: unscoped search limited to {UNSCOPED_ROW_CAP} rows "
                f"(requested {limit}). Add a category, line_code or text filter to see more.")
    return None


def execute_tool(name: str, inputs: dict | None, repo=None) -> str:
    """Single safe entry point: safety rule first, then the tool.
    Always returns the {ok, data, error} envelope as a JSON string; never raises."""
    try:
        if isinstance(inputs, str) and inputs.strip():
            try:
                inputs = json.loads(inputs)
            except ValueError:
                pass                                   # run_tool reports the bad JSON
        reason = safety_check(name, inputs)
        if reason:
            log.warning("%s %s -> %s", name, inputs, reason)
            return to_json(fail(reason))
        return to_json(run_tool(name, inputs, repo))
    except Exception as e:                             # last-resort guard
        return to_json(fail(f"internal error: {e.__class__.__name__}"))
