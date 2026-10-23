"""HW7 shared configuration (s1346) and the RUN_LOG tee used by every HW7 runner.

Section 0 values are fixed for the semester; model settings can be overridden with
environment variables of the same name.
"""
import os
import platform
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# ---- Section 0: personal configuration --------------------------------------------
SID4 = 1346
PORT_BASE = 8000 + SID4 % 900            # 8446
PREFIX = f"s{SID4}"                       # s1346
SEED = SID4                               # 1346
VERIFY_SEED = 260000 + SID4               # 261346
DOMAIN_ID = SID4 % 8                      # 2 -> Municipal Transit Incidents
STUDENT_NAME = os.getenv("STUDENT_NAME", "Himja Patel")

# ---- Paths ------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "reports" / "hw07"
RAW_DIR = REPORT_DIR / "raw"
CASES_DIR = REPORT_DIR / "cases"
RUN_LOG = REPORT_DIR / "RUN_LOG.txt"

# ---- Model settings (same for every HW7 experiment) --------------------------------
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.3"))   # low but >0: attempts differ by seed
AGENT_NUM_PREDICT = int(os.getenv("AGENT_NUM_PREDICT", "400"))
BIKE_TEMPERATURE = float(os.getenv("BIKE_TEMPERATURE", "0"))       # Part 4/5: repeatable
MODEL_DESCRIPTION = f"{MODEL_NAME} via Ollama"
HARDWARE = os.getenv("HW_DESCRIPTION", 'MacBook Pro 13" (Apple M2, 8 GB RAM), macOS')

# ---- Agent loop limits (Part 2) ------------------------------------------------------
MAX_ITERATIONS = 8          # hard ceiling on model turns per run
MAX_REPAIRS = 3             # bounded repair reprompts per run (one per distinct problem)

# ---- Reflexion limits (Part 3) -------------------------------------------------------
MAX_REFLEXION_RETRIES = 2
REFLEXION_TOOL_CALL_BUDGET = 14      # all attempts of one task together
REFLEXION_TOKEN_BUDGET = 24000


def ensure_dirs() -> None:
    """Create reports/hw07/{raw,cases} if missing."""
    for d in (REPORT_DIR, RAW_DIR, CASES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    """Local timestamp with UTC offset, second precision."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


class _Tee:
    """Write to the real stream and to the RUN_LOG file, prefixing log lines with time."""

    def __init__(self, stream, fh) -> None:
        self.stream, self.fh, self.at_line_start = stream, fh, True

    def write(self, text: str) -> int:
        self.stream.write(text)
        for chunk in text.splitlines(keepends=True):
            if self.at_line_start and chunk.strip():
                self.fh.write(f"[{datetime.now().strftime('%H:%M:%S')}] ")
            self.fh.write(chunk)
            self.at_line_start = chunk.endswith("\n")
        return len(text)

    def flush(self) -> None:
        self.stream.flush()
        self.fh.flush()

    def isatty(self) -> bool:
        return False


@contextmanager
def run_log(section: str) -> Iterator[None]:
    """Mirror stdout into reports/hw07/RUN_LOG.txt under a dated section header."""
    ensure_dirs()
    with open(RUN_LOG, "a", encoding="utf-8") as fh:
        header = (f"\n{'=' * 78}\n{section}\nstarted {now_iso()} | {STUDENT_NAME} | {PREFIX} | "
                  f"model {MODEL_DESCRIPTION} | host {platform.node()} | python {platform.python_version()}\n"
                  f"{'=' * 78}\n")
        fh.write(header)
        sys.stdout.write(header)
        old = sys.stdout
        sys.stdout = _Tee(old, fh)
        try:
            yield
        finally:
            sys.stdout = old
            fh.write(f"finished {now_iso()}\n")
