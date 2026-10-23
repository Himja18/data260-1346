"""Toolsets for the HW7 hand-written agent loop.

A toolset bundles what the loop needs to know about its tools:
  specs           OpenAI/Ollama function specs sent to the model
  check(call)     validate one raw model tool call BEFORE running it
                  -> CallCheck(ok, failure, message, arguments)
  execute(n, a)   run a validated call, always returning a JSON string

DomainToolset wraps the three HW5 s1346_rel tools (search_incidents, get_incident,
incident_stats) and reuses their JSON schemas and execute_tool() unchanged.
"""
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / "code" / "mcp", REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Failure classes reported in Part 2 III (plus "ok").
MALFORMED_ARGS = "malformed_arguments"
UNKNOWN_TOOL = "unknown_tool"
TEXT_INSTEAD_OF_TOOL = "text_when_tool_required"
LOST_CHAIN = "lost_multistep_chain"
FAILURE_TYPES = (MALFORMED_ARGS, UNKNOWN_TOOL, TEXT_INSTEAD_OF_TOOL, LOST_CHAIN)


@dataclass
class CallCheck:
    """Result of validating one raw tool call."""
    ok: bool
    failure: str | None = None          # one of FAILURE_TYPES when not ok
    message: str = ""                   # specific problem, sent back to the model on repair
    arguments: dict = field(default_factory=dict)


def parse_arguments(raw: Any) -> tuple[dict | None, str]:
    """Turn the model's arguments (dict or JSON string) into a dict, or explain why not."""
    if raw is None or raw == "":
        return {}, ""
    if isinstance(raw, dict):
        return raw, ""
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
        except ValueError as exc:
            return None, f"arguments are not valid JSON ({exc.msg} at char {exc.pos})"
        if isinstance(val, dict):
            return val, ""
        return None, f"arguments must be a JSON object, got {type(val).__name__}"
    return None, f"arguments must be a JSON object, got {type(raw).__name__}"


class SchemaToolset:
    """Generic toolset: name -> (description, JSON schema, function(args) -> JSON string)."""

    def __init__(self, tools: dict[str, tuple[str, dict, Callable[[dict], str]]]) -> None:
        self.tools = tools
        self.validators = {n: Draft202012Validator(s) for n, (_, s, _) in tools.items()}
        self.specs = [{"type": "function",
                       "function": {"name": n, "description": d, "parameters": s}}
                      for n, (d, s, _) in tools.items()]

    @property
    def names(self) -> list[str]:
        """Tool names in registration order."""
        return list(self.tools)

    def check(self, call: dict) -> CallCheck:
        """Validate tool name, argument JSON and schema; never raises."""
        name = (call or {}).get("name") or ""
        if name not in self.tools:
            return CallCheck(False, UNKNOWN_TOOL,
                             f"unknown tool '{name}'. Available tools: {', '.join(self.names)}")
        args, why = parse_arguments(call.get("arguments"))
        if args is None:
            return CallCheck(False, MALFORMED_ARGS, f"{name}: {why}")
        errors = sorted(self.validators[name].iter_errors(args), key=lambda e: list(e.path))
        if errors:
            details = "; ".join(
                f"{'.'.join(str(p) for p in e.path) or 'arguments'}: {e.message}" for e in errors[:3])
            return CallCheck(False, MALFORMED_ARGS,
                             f"{name} schema validation failed - {details}. {self.hint(name, args)}", args)
        return CallCheck(True, arguments=args)

    def describe(self, name: str) -> str:
        """One-line argument summary of a tool, e.g. "line_code (optional, string like ^L-\\d{3}$)"."""
        schema = self.tools[name][1]
        req = set(schema.get("required", []))
        parts = []
        for prop, spec in schema.get("properties", {}).items():
            kind = spec.get("type", "any")
            extra = (f" one of {spec['enum']}" if "enum" in spec else
                     f" matching {spec['pattern']}" if "pattern" in spec else "")
            if "minimum" in spec or "maximum" in spec:
                extra += f" from {spec.get('minimum', '-inf')} to {spec.get('maximum', 'inf')}"
            parts.append(f"{prop} ({'required' if prop in req else 'optional'} {kind}{extra})")
        return ", ".join(parts) or "no arguments"

    def hint(self, name: str, args: dict) -> str:
        """Repair hint (HW7 fix after the first real run): the allowed arguments, empty optional
        fields to drop, and which other tool takes an argument this tool does not accept."""
        allowed = set(self.tools[name][1].get("properties", {}))
        tips = [f"{name} accepts ONLY: {self.describe(name)}."]
        empty = [k for k, v in args.items() if v in ("", None)]
        if empty:
            tips.append(f"Omit optional arguments instead of sending empty values: {empty}.")
        for key in sorted(set(args) - allowed):
            owners = [n for n in self.tools if key in self.tools[n][1].get("properties", {})]
            if owners:
                tips.append(f"'{key}' is an argument of {' / '.join(owners)}, not of {name}.")
        return " ".join(tips)

    def execute(self, name: str, arguments: dict) -> str:
        """Run one validated call; the tool itself returns a JSON envelope string."""
        return self.tools[name][2](arguments)


DOMAIN_DESCRIPTIONS = {
    "search_incidents": "Search transit incidents, newest first. Optional filters: category "
                        "(Delay|Breakdown|Accident|Service Change), line_code = 'L-' plus exactly 3 digits "
                        "(e.g. 'L-033', never 'L-0033'), text = words in the route title (e.g. a street). "
                        "limit 1-50 (default 10). Returns incident_code values like 'INC-004979'.",
    "get_incident": "Full details of ONE incident by its exact incident_code, e.g. 'INC-004979' "
                    "(line name, mode, category, timestamps).",
    "incident_stats": "Counts for ALL categories in one call: number of incidents and passengers affected "
                      "per category (read the category you need from by_category). It has NO category "
                      "argument. Call it with no arguments for all lines, or with line_code ('L-033') "
                      "for one line.",
}


def domain_toolset(repo: Any = None) -> SchemaToolset:
    """The three HW5 domain tools, validated with their HW5 JSON schemas."""
    from domain_tools import SCHEMAS, execute_tool

    def runner(name: str) -> Callable[[dict], str]:
        return lambda args: execute_tool(name, args, repo=repo)

    return SchemaToolset({n: (DOMAIN_DESCRIPTIONS[n], SCHEMAS[n], runner(n)) for n in SCHEMAS})
