"""HW7 Part 6 - six file tools, confined to one sandbox directory.

    read_file(path, max_lines=None)                        -> content (+ truncated flag)
    write_file(path, content, overwrite=True)              -> bytes written
    edit_file(path, old, new, count=1)                     -> short unified diff
    glob_files(pattern)                                    -> matching relative paths
    search_in_files(query, file_pattern="*", regex=False)  -> [{file, line, text}]
    bash(command, auto_approve=False, timeout_s=10)        -> runs ONLY if confirm_bash allows it

Every path is resolved inside FileTools.root; anything that escapes it (../, absolute paths
elsewhere, symlinks out) is refused. Every tool returns {"ok", "data", "error"} like HW5.
"""
import difflib
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from file_tools.safety import confirm_bash

MAX_DIFF_LINES = 30
MAX_MATCHES = 100


def ok(data: Any) -> dict:
    """Success envelope."""
    return {"ok": True, "data": data, "error": None}


def fail(error: str) -> dict:
    """Error envelope."""
    return {"ok": False, "data": None, "error": error}


class FileTools:
    """The six tools bound to one sandbox root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, path: str) -> Path:
        p = (self.root / path).resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError(f"path '{path}' is outside the sandbox")
        return p

    def _rel(self, p: Path) -> str:
        return str(p.relative_to(self.root))

    def read_file(self, path: str, max_lines: int | None = None) -> dict:
        """Return a file's text, optionally only the first max_lines lines."""
        try:
            p = self._path(path)
            lines = p.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            known = sorted(self._rel(f) for f in self.root.rglob("*") if f.is_file())[:20]
            return fail(f"read_file: file not found: '{path}'. Use a path exactly as returned by "
                        f"glob_files/search_in_files. Existing files: {known}")
        except (OSError, PermissionError, UnicodeDecodeError) as exc:
            return fail(f"read_file: {exc}")
        if max_lines is not None and (not isinstance(max_lines, int) or max_lines < 1):
            return fail("read_file: max_lines must be a positive integer")
        shown = lines[:max_lines] if max_lines else lines
        return ok({"path": self._rel(p), "content": "\n".join(shown), "lines_returned": len(shown),
                   "total_lines": len(lines), "truncated": len(shown) < len(lines)})

    def write_file(self, path: str, content: str, overwrite: bool = True) -> dict:
        """Create or replace a text file inside the sandbox."""
        try:
            p = self._path(path)
            if p.exists() and not overwrite:
                return fail(f"write_file: {path} exists and overwrite=False")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except (OSError, PermissionError) as exc:
            return fail(f"write_file: {exc}")
        return ok({"path": self._rel(p), "bytes": len(content.encode())})

    def edit_file(self, path: str, old: str, new: str, count: int = 1) -> dict:
        """Replace `old` with `new` (exactly `count` occurrences must exist); return a short diff."""
        try:
            p = self._path(path)
            before = p.read_text(encoding="utf-8")
        except (OSError, PermissionError, UnicodeDecodeError) as exc:
            return fail(f"edit_file: {exc}")
        found = before.count(old) if old else 0
        if found == 0:
            return fail(f"edit_file: text not found in {path}")
        if found != count:
            return fail(f"edit_file: expected {count} occurrence(s), found {found}; make `old` more specific")
        after = before.replace(old, new, count)
        p.write_text(after, encoding="utf-8")
        diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                         f"a/{path}", f"b/{path}", n=1, lineterm=""))
        short = diff[:MAX_DIFF_LINES] + ([f"... ({len(diff) - MAX_DIFF_LINES} more diff lines)"]
                                         if len(diff) > MAX_DIFF_LINES else [])
        return ok({"path": self._rel(p), "replacements": count, "diff": "\n".join(short)})

    def glob_files(self, pattern: str) -> dict:
        """Files under the sandbox matching a glob such as '**/*.py'."""
        if not pattern or pattern.startswith("/") or ".." in Path(pattern).parts:
            return fail("glob_files: pattern must be relative to the sandbox")
        files = sorted(self._rel(p) for p in self.root.glob(pattern) if p.is_file())
        return ok({"pattern": pattern, "count": len(files), "files": files})

    def search_in_files(self, query: str, file_pattern: str = "*", regex: bool = False) -> dict:
        """Lines containing `query` in files whose name matches file_pattern (e.g. '*.py')."""
        if not query:
            return fail("search_in_files: query is required")
        try:
            rx = re.compile(query if regex else re.escape(query))
        except re.error as exc:
            return fail(f"search_in_files: bad regex: {exc}")
        matches = []
        for p in sorted(self.root.rglob("*")):
            if not p.is_file() or not fnmatch.fnmatch(p.name, file_pattern):
                continue
            try:
                for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                    if rx.search(line):
                        matches.append({"file": self._rel(p), "line": i, "text": line.strip()[:200]})
            except UnicodeDecodeError:
                continue
            if len(matches) >= MAX_MATCHES:
                break
        return ok({"query": query, "file_pattern": file_pattern, "count": len(matches),
                   "files": sorted({m["file"] for m in matches}), "matches": matches})

    def bash(self, command: str, auto_approve: bool = False, timeout_s: int = 10) -> dict:
        """Run a shell command in the sandbox - only if the safety gate allows it."""
        gate = confirm_bash(command, auto_approve=auto_approve)
        if not gate.allowed:
            return {"ok": False, "data": {"gate": gate.as_dict()}, "error": gate.reason}
        try:
            proc = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True,
                                  timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return fail(f"bash: timed out after {timeout_s}s")
        return ok({"gate": gate.as_dict(), "exit_code": proc.returncode,
                   "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-1000:]})


SCHEMAS = {
    "read_file": {"type": "object", "properties": {"path": {"type": "string", "minLength": 1},
                                                   "max_lines": {"type": "integer", "minimum": 1}},
                  "required": ["path"], "additionalProperties": False},
    "write_file": {"type": "object", "properties": {"path": {"type": "string", "minLength": 1},
                                                    "content": {"type": "string"},
                                                    "overwrite": {"type": "boolean"}},
                   "required": ["path", "content"], "additionalProperties": False},
    "edit_file": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"},
                                                   "new": {"type": "string"},
                                                   "count": {"type": "integer", "minimum": 1}},
                  "required": ["path", "old", "new"], "additionalProperties": False},
    "glob_files": {"type": "object", "properties": {"pattern": {"type": "string", "minLength": 1}},
                   "required": ["pattern"], "additionalProperties": False},
    "search_in_files": {"type": "object", "properties": {"query": {"type": "string", "minLength": 1},
                                                         "file_pattern": {"type": "string"},
                                                         "regex": {"type": "boolean"}},
                        "required": ["query"], "additionalProperties": False},
    "bash": {"type": "object", "properties": {"command": {"type": "string", "minLength": 1}},
             "required": ["command"], "additionalProperties": False},
}
DESCRIPTIONS = {
    "read_file": "Read a text file in the sandbox. Optional max_lines limits how many lines come back.",
    "write_file": "Create or overwrite a text file in the sandbox.",
    "edit_file": "Replace exact text `old` with `new` in a file; returns a short diff.",
    "glob_files": "List files matching a glob pattern relative to the sandbox, e.g. '**/*.py'.",
    "search_in_files": "Find lines containing `query` in files whose name matches file_pattern (e.g. '*.py').",
    "bash": "Run a shell command in the sandbox (passes a safety gate; destructive commands are refused).",
}


def file_toolset(tools: FileTools, names: tuple[str, ...] = tuple(SCHEMAS)) -> Any:
    """The file tools as a Part 2 SchemaToolset (bash never gets auto_approve from the model)."""
    from agent_loop.toolset import SchemaToolset

    def runner(name: str) -> Any:
        return lambda args: json.dumps(getattr(tools, name)(**args), default=str)

    return SchemaToolset({n: (DESCRIPTIONS[n], SCHEMAS[n], runner(n)) for n in names})
