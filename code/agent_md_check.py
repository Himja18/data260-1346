"""DATA-260 HW6 Part 4.4 - verify that code follows the AGENT.md instructions.

    python code/agent_md_check.py --generate   # ask qwen2.5:3b (with AGENT.md + MEMORY.md in the
                                               # system prompt) to write a function, then check it
    python code/agent_md_check.py              # check the saved generated function and the
                                               # hand-written functions in code/file_memory.py

Static checks (AST) for the machine-checkable AGENT.md rules:
  C1 snake_case names   C2 type hints   C3 docstrings   C4 no print() in library code
  C5 no bare except     T2 no direct Ollama HTTP calls   N1 no hard-coded secrets
plus a behaviour test of the generated function, run in a separate process.
Output: reports/hw06/raw/agent_md_check.json
"""
import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import file_memory as fm  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "reports" / "hw06" / "raw"
GENERATED = RAW / "generated_function.py"
OUT = RAW / "agent_md_check.json"

SNAKE = re.compile(r"^_{0,2}[a-z][a-z0-9_]*$")
UPPER = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
SECRET_NAME = re.compile(r"(password|passwd|secret|api_?key|token)", re.I)

TASK = (
    "Write a Python function named incident_age_hours(occurred_at, now=None) for this project. "
    "It returns how many hours (a float) have passed between occurred_at and now (default: the "
    "current UTC time). Naive datetimes are treated as UTC. If occurred_at is later than now, "
    "raise ValueError. Follow every instruction in AGENT.md. Return only the code (imports + "
    "the function) in one ```python block."
)

BEHAVIOUR_TEST = """
import importlib.util, sys
from datetime import datetime, timezone
spec = importlib.util.spec_from_file_location("gen", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
f = mod.incident_age_hours
utc = timezone.utc
r = {}
r["aware_2.5h"] = abs(f(datetime(2026,10,16,8,0,tzinfo=utc), now=datetime(2026,10,16,10,30,tzinfo=utc)) - 2.5) < 1e-6
r["naive_is_utc"] = abs(f(datetime(2026,10,16,8,0), now=datetime(2026,10,16,10,30,tzinfo=utc)) - 2.5) < 1e-6
try:
    f(datetime(2026,10,17,0,0,tzinfo=utc), now=datetime(2026,10,16,0,0,tzinfo=utc)); r["future_raises"] = False
except ValueError:
    r["future_raises"] = True
r["default_now_works"] = isinstance(f(datetime(2020,1,1,tzinfo=utc)), float)
print(__import__("json").dumps(r))
"""


def check_source(code: str, library: bool = True, only: set = None) -> list:
    """Run the static AGENT.md checks on Python source. Returns [{rule, passed, detail}]."""
    tree = ast.parse(code)
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if only:
        funcs = [f for f in funcs if f.name in only]
    results = []

    bad_names = [f.name for f in funcs if not SNAKE.match(f.name)]
    bad_names += [a.arg for f in funcs for a in f.args.args + f.args.kwonlyargs
                  if not SNAKE.match(a.arg)]
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and not (SNAKE.match(t.id) or UPPER.match(t.id)):
                    bad_names.append(t.id)
    results.append({"rule": "C1 snake_case / UPPER_SNAKE_CASE names", "passed": not bad_names,
                    "detail": bad_names or "all names ok"})

    missing = []
    for f in funcs:
        args = [a for a in f.args.args + f.args.kwonlyargs if a.arg not in ("self", "cls")]
        missing += [f"{f.name}({a.arg})" for a in args if a.annotation is None]
        if f.returns is None:
            missing.append(f"{f.name} -> return")
    results.append({"rule": "C2 type hints on parameters and return", "passed": not missing,
                    "detail": missing or f"{len(funcs)} function(s) fully annotated"})

    no_doc = [f.name for f in funcs if not f.name.startswith("_") and not ast.get_docstring(f)]
    results.append({"rule": "C3 docstring on every public function", "passed": not no_doc,
                    "detail": no_doc or "all public functions documented"})

    scope = funcs if only else [tree]
    prints = sorted({n.lineno for s in scope for n in ast.walk(s) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == "print"})
    results.append({"rule": "C4 no print() in library code", "passed": not (library and prints),
                    "detail": f"print() on lines {prints}" if prints else "no print()"})

    bare = sorted({n.lineno for s in scope for n in ast.walk(s)
                   if isinstance(n, ast.ExceptHandler) and n.type is None})
    results.append({"rule": "C5 no bare except", "passed": not bare,
                    "detail": f"bare except on lines {bare}" if bare else "none"})

    consts = [n.value for s in scope for n in ast.walk(s)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    direct = [c for c in consts if re.search(r"11434|/api/(chat|generate|embed)", c)]
    imports = []
    for s in scope:
        for n in ast.walk(s):
            if isinstance(n, ast.Import):
                imports += [a.name for a in n.names if "ollama" in a.name]
            elif isinstance(n, ast.ImportFrom) and "ollama" in (n.module or ""):
                imports.append(n.module)
    results.append({"rule": "T2 no direct Ollama HTTP calls", "passed": not (direct or imports),
                    "detail": (direct + imports) or "none"})

    secrets = [t.id for s in scope for n in ast.walk(s) if isinstance(n, ast.Assign)
               and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str) and n.value.value
               for t in n.targets if isinstance(t, ast.Name) and SECRET_NAME.search(t.id)]
    results.append({"rule": "N1 no hard-coded secrets", "passed": not secrets,
                    "detail": secrets or "none"})
    return results


def extract_code(reply: str) -> str:
    """The first ```python block of a model reply (or the whole reply)."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", reply, re.S)
    return (match.group(1) if match else reply).strip() + "\n"


MAX_ATTEMPTS = 3


def _write_generated(code: str, model: str, attempt: int) -> None:
    """Save one generated version of the function."""
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(f"# Generated by {model} (attempt {attempt}) on "
                         f"{datetime.now().isoformat(timespec='seconds')} with AGENT.md + MEMORY.md in the "
                         f"system prompt (code/agent_md_check.py)\n" + code)


def _feedback(static: list, beh: dict) -> str:
    """Turn failed checks into a correction request for the model."""
    lines = [f"- AGENT.md rule {r['rule']} is violated: {r['detail']}" for r in static if not r["passed"]]
    if "error" in beh:
        lines.append(f"- The behaviour test crashed: {beh['error']}")
    else:
        lines += [f"- Behaviour test '{k}' failed" for k, v in beh.items() if v is not True]
    return ("Your function does not pass the project checks:\n" + "\n".join(lines) +
            "\nFix every problem and return the complete corrected code (imports + function) "
            "in one ```python block.")


def _safe_check(code: str) -> list:
    """check_source, reporting a syntax error as a failed rule instead of crashing."""
    try:
        return check_source(code)
    except SyntaxError as exc:
        return [{"rule": "syntax", "passed": False, "detail": str(exc)}]


def generate() -> dict:
    """Generate the function with the local model, check it, and feed failures back (max 3 attempts)."""
    from model_client import ModelClient
    agent, memory = fm.load_memory_files()
    system = fm.build_system_prompt("You are a careful Python developer on this project.", agent, memory)
    client = ModelClient(temperature=0, seed=1346, num_predict=600)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": TASK}]
    attempts = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = client.complete(messages)
        code = extract_code(result.content)
        _write_generated(code, client.model, attempt)
        try:
            static = check_source(GENERATED.read_text())
        except SyntaxError as exc:
            static = [{"rule": "syntax", "passed": False, "detail": str(exc)}]
        beh = behaviour(GENERATED)
        ok = all(r["passed"] for r in static) and "error" not in beh and all(v is True for v in beh.values())
        attempts.append({"attempt": attempt, "code": code, "static": static, "behaviour": beh, "passed": ok,
                         "input_tokens": result.input_tokens, "output_tokens": result.output_tokens})
        print(f"attempt {attempt}: static {sum(r['passed'] for r in static)}/{len(static)}, "
              f"behaviour {beh} -> {'PASS' if ok else 'FAIL'}")
        if ok:
            break
        messages += [{"role": "assistant", "content": result.content},
                     {"role": "user", "content": _feedback(static, beh)}]
    return {"model": client.model, "prompt": TASK, "attempts": attempts,
            "passed_on_attempt": next((a["attempt"] for a in attempts if a["passed"]), None)}


def behaviour(path: Path) -> dict:
    """Run the behaviour test of incident_age_hours in a separate Python process."""
    try:
        out = subprocess.run([sys.executable, "-c", BEHAVIOUR_TEST, str(path)], capture_output=True,
                             text=True, timeout=20)
        return json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 else \
            {"error": out.stderr.strip().splitlines()[-1] if out.stderr else "failed"}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, IndexError) as exc:
        return {"error": f"{exc.__class__.__name__}"}


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true", help="regenerate the function with the model")
    args = ap.parse_args()

    report = {"timestamp": datetime.now().isoformat(timespec="seconds"), "targets": []}
    if args.generate:
        report["generation"] = generate()
    if GENERATED.exists():
        code = GENERATED.read_text()
        report["targets"].append({"target": str(GENERATED.relative_to(REPO)), "kind": "model-generated",
                                  "static": _safe_check(code), "behaviour": behaviour(GENERATED)})
    handwritten = ["count_content_lines", "read_last_consolidated", "needs_consolidation",
                   "consolidate_text", "build_system_prompt"]
    report["targets"].append({
        "target": "code/file_memory.py :: " + ", ".join(handwritten), "kind": "implemented",
        "static": check_source((REPO / "code" / "file_memory.py").read_text(), only=set(handwritten))})

    for t in report["targets"]:
        print(f"\n== {t['target']} ({t['kind']})")
        for r in t["static"]:
            print(f"  [{'PASS' if r['passed'] else 'FAIL'}] {r['rule']}: {r['detail']}")
        if "behaviour" in t:
            print(f"  behaviour: {t['behaviour']}")
        t["all_static_passed"] = all(r["passed"] for r in t["static"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\nSaved {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
