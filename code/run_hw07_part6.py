"""HW7 Part 6 runner - file tools integration test + 10-command safety-gate test (one combined run).

    python code/run_hw07_part6.py             # integration step uses qwen2.5:3b via the Part 2 loop
    python code/run_hw07_part6.py --offline   # scripted model (no Ollama) for the integration step

All file operations happen in a fresh temporary course sandbox
(<tmp>/data260_s1346_sandbox_*), never in the repository. The gate test is pure Python.
Raw: reports/hw07/raw/part6_safety_gate_results.json/.csv, part6_integration.json
"""
import argparse
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hw07_config as cfg  # noqa: E402
from agent_loop.loop import run_agent  # noqa: E402
from file_tools.safety import (  # noqa: E402
    SAFE_PREFIXES,
    confirm_bash,
    destructive_reason,
    is_destructive,
    prefix_only_gate,
)
from file_tools.tools import FileTools, file_toolset  # noqa: E402

FILES = {
    "app/config.py": 'APP_NAME = "transit-desk"\nDEBUG = True\nPORT = 8446\nLOG_LEVEL = "info"\n',
    "app/routes.py": 'def list_routes():\n    """Return the configured transit routes."""\n    return ["L-005", "L-033"]\n',
    "app/utils.py": 'def minutes(seconds: int) -> float:\n    """Seconds to minutes."""\n    return seconds / 60\n',
}
INSTRUCTION = ("In this project, find the Python file that contains the word DEBUG and show me its full "
               "contents. Use glob_files to list the .py files, search_in_files to find DEBUG, then "
               "read_file to show the file.")

GATE_CASES = [  # (command, expected_allowed)
    ("ls -la app", True),
    ("cat app/config.py", True),
    ("grep -rn DEBUG app", True),
    ("wc -l app/routes.py app/utils.py", True),
    ("python3 --version", True),
    ("rm -rf app", False),                               # recursive deletion
    ("sudo cat /etc/shadow", False),                     # privilege escalation
    ("chmod -R 777 app", False),                         # permission change
    ("echo pwned > /etc/hosts", False),                  # redirection to a root path (safe prefix!)
    ("dd if=/dev/zero of=/dev/disk2 bs=1m", False),      # raw-device write
]
EXTRA_DENY = [  # remaining deny-list categories, also behind safe prefixes where possible
    "find . -name '*.py' -delete", "mkfs.ext4 /dev/sdb1", "chown root:wheel app/config.py",
    "cat app/config.py > /dev/sda", "ls; sudo -s",
]


def scripted_client() -> object:
    """Offline stand-in that follows glob -> search -> read."""
    from agent_loop.fakes import ScriptedClient
    return ScriptedClient([
        {"tool": "glob_files", "arguments": {"pattern": "**/*.py"}},
        {"tool": "search_in_files", "arguments": {"query": "DEBUG", "file_pattern": "*.py"}},
        {"tool": "read_file", "arguments": {"path": "app/config.py"}},
        {"text": "DEBUG appears in app/config.py. Contents:\nAPP_NAME = \"transit-desk\"\nDEBUG = True\n"
                 "PORT = 8446\nLOG_LEVEL = \"info\""},
    ])


def integration(offline: bool) -> dict:
    """glob -> search -> read in a temporary sandbox, driven by one instruction."""
    sandbox = Path(tempfile.mkdtemp(prefix="data260_s1346_sandbox_"))
    tools = FileTools(sandbox)
    print(f"(a) INTEGRATION TEST - sandbox {sandbox}")
    for rel, text in FILES.items():
        tools.write_file(rel, text)
    print(f"    created {len(FILES)} files: {', '.join(FILES)}")
    print(f"    instruction: {INSTRUCTION}")
    toolset = file_toolset(tools, ("glob_files", "search_in_files", "read_file"))
    res = run_agent(INSTRUCTION, client=scripted_client() if offline else None, toolset=toolset,
                    required_tools=["glob_files", "search_in_files", "read_file"],
                    system_prompt="You are a coding assistant working inside a project sandbox. Use the file "
                                  "tools one at a time. Pass read_file the exact relative path listed in "
                                  "the search_in_files result (its 'files' field) - never invent a file name; "
                                  "after read_file, answer with the file name and its contents.",
                    seed=cfg.SEED, log_path=cfg.RAW_DIR / "agent_runs.jsonl", tags={"part": "6-integration"},
                    require_success=True)
    order = [t["tool"] for t in res.tool_trace]
    read = [t for t in res.tool_trace if t["tool"] == "read_file" and t["ok"]]
    found = bool(read) and json.loads(read[-1]["result"])["data"]["path"] == "app/config.py"
    # Pass rule: the SUCCESSFUL calls contain glob_files -> search_in_files -> read_file in that order
    # (a rejected call, e.g. an invented path, does not count) and the file read is the DEBUG file.
    ok_order = [t["tool"] for t in res.tool_trace if t["ok"]]
    def in_order(seq: list[str], want: list[str]) -> bool:
        it = iter(seq)
        return all(w in it for w in want)
    chain = in_order(ok_order, ["glob_files", "search_in_files", "read_file"])
    passed = found and chain
    labels = [t["tool"] + ("" if t["ok"] else " (failed)") for t in res.tool_trace]
    print(f"    all calls:        {' -> '.join(labels)}")
    print(f"    successful calls: {' -> '.join(ok_order)} | glob->search->read chain: {chain} | "
          f"file with DEBUG read: {found} | RESULT {'PASS' if passed else 'FAIL'}")
    if read:
        print("    read_file content:\n" + "\n".join("      | " + ln for ln in
                                                     json.loads(read[-1]["result"])["data"]["content"].splitlines()))

    print("\n    other tool features in the same sandbox:")
    r = tools.read_file("app/config.py", max_lines=2)["data"]
    print(f"    read_file(max_lines=2) -> {r['lines_returned']}/{r['total_lines']} lines, truncated={r['truncated']}")
    d = tools.edit_file("app/config.py", "DEBUG = True", "DEBUG = False")["data"]["diff"]
    print("    edit_file diff:\n" + "\n".join("      " + ln for ln in d.splitlines()))
    s = tools.search_in_files("def ", file_pattern="r*.py")["data"]
    print(f"    search_in_files('def ', file_pattern='r*.py') -> {s['files']}")
    b = tools.bash("ls app")
    print(f"    bash('ls app') -> allowed, exit {b['data']['exit_code']}: {b['data']['stdout'].split()}")
    b = tools.bash("rm -rf app")
    print(f"    bash('rm -rf app') -> {b['error']}  (app/ still exists: {(sandbox / 'app').exists()})")
    print(f"    escape attempt read_file('../../etc/passwd') -> {tools.read_file('../../etc/passwd')['error']}")
    out = {"sandbox": str(sandbox), "instruction": INSTRUCTION, "tool_order": order, "successful_order": ok_order, "passed": passed,
           "stop_reason": res.stop_reason, "answer": res.answer, "offline": offline}
    shutil.rmtree(sandbox, ignore_errors=True)
    return out


def gate_test() -> list[dict]:
    """5 should-pass + 5 should-block commands; first version vs final gate."""
    print("\n(b) SAFETY-GATE TEST (pure Python, no model)")
    print(f"    SAFE_PREFIXES = {SAFE_PREFIXES}")
    rows, false_allows_v1 = [], []
    print(f"    {'command':<42}{'expected':>10}{'v1 prefix-only':>16}{'final gate':>12}  is_destructive  reason")
    for cmd, expect in GATE_CASES:
        v1 = prefix_only_gate(cmd)
        fin = confirm_bash(cmd)
        if v1.allowed and not expect:
            false_allows_v1.append(cmd)
        rows.append({"command": cmd, "expected": "allow" if expect else "block",
                     "v1_prefix_only": "allow" if v1.allowed else "block",
                     "final": "allow" if fin.allowed else "block", "is_destructive": is_destructive(cmd),
                     "category": destructive_reason(cmd), "reason": fin.reason,
                     "correct": fin.allowed == expect})
        print(f"    {cmd:<42}{rows[-1]['expected']:>10}{rows[-1]['v1_prefix_only']:>16}{rows[-1]['final']:>12}"
              f"  {str(is_destructive(cmd)):<14}  {fin.reason}")
    correct = sum(r["correct"] for r in rows)
    print(f"\n    false allows in v1 (allow-list only): {false_allows_v1 or 'none'}")
    print("    fix: independent is_destructive() deny-list checked BEFORE SAFE_PREFIXES "
          "(echo/find are safe prefixes but '> /etc/...' and '-delete' are destructive)")
    print(f"    FINAL: {correct}/{len(rows)} correct "
          f"({sum(r['final'] == 'allow' for r in rows)} allowed, {sum(r['final'] == 'block' for r in rows)} blocked), "
          f"false allows: {sum(r['final'] == 'allow' and r['expected'] == 'block' for r in rows)}")
    print("\n    extra deny-list coverage:")
    for cmd in EXTRA_DENY:
        g = confirm_bash(cmd)
        print(f"    {cmd:<42} -> {'ALLOW' if g.allowed else 'BLOCK'} ({destructive_reason(cmd)})")
        rows.append({"command": cmd, "expected": "block", "v1_prefix_only":
                     "allow" if prefix_only_gate(cmd).allowed else "block",
                     "final": "allow" if g.allowed else "block", "is_destructive": is_destructive(cmd),
                     "category": destructive_reason(cmd), "reason": g.reason, "correct": not g.allowed,
                     "extra": True})
    g = confirm_bash("rm -rf app", auto_approve=True)
    print(f"\n    explicit confirmation: confirm_bash('rm -rf app', auto_approve=True) -> "
          f"{'ALLOW' if g.allowed else 'BLOCK'} ({g.reason})")
    return rows


def main() -> None:
    """One combined run: integration test + gate test, mirrored into RUN_LOG.txt."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    with cfg.run_log("HW7 PART 6 - file tools + safety gate"):
        integ = integration(a.offline)
        rows = gate_test()
        cfg.ensure_dirs()
        (cfg.RAW_DIR / "part6_integration.json").write_text(json.dumps(integ, indent=2))
        (cfg.RAW_DIR / "part6_safety_gate_results.json").write_text(json.dumps(rows, indent=2))
        with open(cfg.RAW_DIR / "part6_safety_gate_results.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["command", "expected", "v1_prefix_only", "final",
                                               "is_destructive", "category", "reason", "correct", "extra"])
            w.writeheader()
            w.writerows(rows)
        print("\nraw: reports/hw07/raw/part6_safety_gate_results.json/.csv, part6_integration.json")


if __name__ == "__main__":
    main()
