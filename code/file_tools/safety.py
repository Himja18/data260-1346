"""HW7 Part 6 - safety gate for the bash tool (pure Python, testable without a model).

Observable contract
    is_destructive(command) -> bool
    confirm_bash(command, auto_approve=False) -> GateResult(allowed: bool, reason: str)

Decision order in confirm_bash
    1. empty command                      -> block
    2. is_destructive(command)            -> block unless auto_approve=True (explicit confirmation),
                                             EVEN IF the command starts with a SAFE_PREFIXES entry
    3. every ;/&&/||/| segment starts with a SAFE_PREFIXES entry -> allow
    4. anything else                      -> needs confirmation: allow only with auto_approve=True

The deny-list is independent of the allow-list: `echo x > /etc/hosts` starts with the safe
prefix `echo` and `find . -delete` with the safe prefix `find`, but both are destructive.
"""
import re
import tempfile
from dataclasses import dataclass

SAFE_PREFIXES: tuple[str, ...] = (
    "ls", "pwd", "cat", "head", "tail", "wc", "grep", "find", "echo", "sort", "uniq", "diff",
    "file", "stat", "du", "df", "date", "whoami", "which", "python3 --version", "python --version",
    "python3 -m pytest", "python -m pytest", "git status", "git diff", "git log", "git show",
)

_SEG_SPLIT = re.compile(r"\s*(?:;|&&|\|\||\||\n|`|\$\()\s*")
_TEMP_ROOTS = tuple({tempfile.gettempdir().rstrip("/") + "/", "/tmp/", "/private/tmp/", "/var/folders/",
                     "/private/var/folders/"})

# (category, pattern) - each pattern is searched in the whole command string.
DENY_RULES: list[tuple[str, re.Pattern]] = [
    ("recursive deletion", re.compile(
        r"(^|[\s;&|(`])(sudo\s+)?rm\s+(-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)\b"
        r"|(^|[\s;&|(`])find\b[^;&|]*\s-(delete|exec\s+rm)\b"
        r"|\brmtree\s*\(|(^|[\s;&|(`])git\s+clean\s+-[a-zA-Z]*d"
        r"|(^|[\s;&|(`])rm\s+[^;&|]*(\s|^)/(\s|$|\*)")),
    ("privilege escalation", re.compile(
        r"(^|[\s;&|(`])(sudo|su|doas|pkexec|runas)(\s|$)|\bchmod\s+[^;&|]*[ug]\+s\b|\bsetuid\b")),
    ("permission/ownership change", re.compile(
        r"(^|[\s;&|(`])(chmod|chown|chgrp|chattr|setfacl|icacls|takeown)\s")),
    ("raw-device write", re.compile(
        r"\bdd\b[^;&|]*\bof=/dev/|>\s*/dev/(?!null\b|stdout\b|stderr\b|tty\b)\w"
        r"|\btee\s+(-a\s+)?/dev/(?!null\b)\w|(^|[\s;&|(`])(shred|wipefs|blkdiscard)\s")),
    ("filesystem creation", re.compile(
        r"(^|[\s;&|(`])(mkfs(\.\w+)?|mke2fs|mkswap|newfs(_\w+)?|mkdosfs|format)\s"
        r"|\bdiskutil\s+(erase\w*|partitionDisk|reformat)\b")),
    ("redirection to root path", re.compile(r"(>>?|\btee\s+(?:-a\s+)?)\s*(/[^\s;&|]*)")),
]


@dataclass(frozen=True)
class GateResult:
    """Allow/block decision with a short reason."""
    allowed: bool
    reason: str

    def as_dict(self) -> dict:
        """JSON-friendly form."""
        return {"allowed": self.allowed, "reason": self.reason}


def destructive_reason(command: str) -> str | None:
    """Name of the first deny-list category the command hits, or None."""
    cmd = command or ""
    for category, pattern in DENY_RULES:
        for m in pattern.finditer(cmd):
            if category == "redirection to root path":
                target = m.group(2)
                if target.startswith("/dev/") or target.startswith(_TEMP_ROOTS):
                    continue            # /dev/* handled as raw-device; temp dirs are the sandbox
            return category
    return None


def is_destructive(command: str) -> bool:
    """True if the command matches any deny-list category."""
    return destructive_reason(command) is not None


def _segments(command: str) -> list[str]:
    return [s.strip() for s in _SEG_SPLIT.split(command or "") if s and s.strip()]


def _starts_with_safe_prefix(segment: str) -> bool:
    return any(segment == p or segment.startswith(p + " ") for p in SAFE_PREFIXES)


def prefix_only_gate(command: str) -> GateResult:
    """FIRST VERSION of the gate (allow-list only). Kept to show the false allows it had."""
    if command.strip() and all(_starts_with_safe_prefix(s) for s in _segments(command)):
        return GateResult(True, "matches SAFE_PREFIXES")
    return GateResult(False, "not on SAFE_PREFIXES allow-list")


def confirm_bash(command: str, auto_approve: bool = False) -> GateResult:
    """Final gate: independent deny-list first, then the allow-list, else ask for confirmation."""
    if not (command or "").strip():
        return GateResult(False, "empty command")
    reason = destructive_reason(command)
    if reason:
        if auto_approve:
            return GateResult(True, f"destructive ({reason}) - allowed by explicit confirmation")
        return GateResult(False, f"blocked: destructive ({reason}); needs explicit confirmation")
    if all(_starts_with_safe_prefix(s) for s in _segments(command)):
        return GateResult(True, "allowed: every part matches SAFE_PREFIXES")
    if auto_approve:
        return GateResult(True, "not on allow-list - allowed by explicit confirmation")
    return GateResult(False, "blocked: not on SAFE_PREFIXES allow-list; needs confirmation")
