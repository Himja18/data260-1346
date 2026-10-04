"""DATA-260 HW5 Part 2B - domain MCP server over s1346_rel (Municipal Transit Incidents).

Exactly three tools, all returning the shared envelope {ok, data, error}:
  search_incidents(category?, line_code?, text?, limit=10)   search
  get_incident(incident_code)                                detail lookup
  incident_stats(line_code?)                                 aggregate

Parameters are deliberately loose types (str / int / None) so that bad values
reach our own validation and come back as {ok: false, error: "..."} instead of
a protocol-level schema error.

Run:  npx @modelcontextprotocol/inspector@0 "$PWD/venv/bin/python" code/mcp/domain_server.py
Needs MYSQL_PASSWORD (and optionally MYSQL_USER/HOST/PORT) in the environment.
Logs go to stderr only.
"""
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from domain_tools import run_tool

mcp = FastMCP("s1346_rel")

# All three tools only read data.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                            idempotentHint=True, openWorldHint=False)


def _args(**kw):
    return {k: v for k, v in kw.items() if v is not None}


@mcp.tool(annotations=READ_ONLY)
def search_incidents(category: Optional[str] = None, line_code: Optional[str] = None,
                     text: Optional[str] = None, limit: int = 10) -> dict:
    """Search transit incidents, newest first. Filters (all optional): category
    (Delay | Breakdown | Accident | Service Change), line_code like 'L-005',
    text found in the route title. limit 1-50 (default 10)."""
    return run_tool("search_incidents", _args(category=category, line_code=line_code,
                                              text=text, limit=limit))


@mcp.tool(annotations=READ_ONLY)
def get_incident(incident_code: str) -> dict:
    """Full details for one incident by its code, e.g. 'INC-000123', including
    its transit line name and mode."""
    return run_tool("get_incident", {"incident_code": incident_code})


@mcp.tool(annotations=READ_ONLY)
def incident_stats(line_code: Optional[str] = None) -> dict:
    """Aggregate: incident count and total passengers affected per category,
    for one line ('L-005') or for all lines if line_code is omitted."""
    return run_tool("incident_stats", _args(line_code=line_code))


if __name__ == "__main__":
    mcp.run()
