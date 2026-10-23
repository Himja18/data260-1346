"""HW7 Part 2 runner - agent loop demo, error recovery and the reliability measurement.

    python code/run_hw07_part2.py --demo           # tasks A, B, C once each (screenshot)
    python code/run_hw07_part2.py --recovery       # nonexistent / impossible incident IDs
    python code/run_hw07_part2.py --reliability 21 # 7 attempts per task, same model settings
    python code/run_hw07_part2.py --all

Needs MySQL (s1346_rel, MYSQL_PASSWORD) and Ollama (qwen2.5:3b). Output is mirrored to
reports/hw07/RUN_LOG.txt; raw per-attempt data goes to reports/hw07/raw/.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hw07_config as cfg  # noqa: E402
from agent_loop.loop import run_agent  # noqa: E402
from agent_loop.tasks import ERROR_RECOVERY_PROMPT, TASKS, unsupported_claims, verify  # noqa: E402
from agent_loop.toolset import FAILURE_TYPES, domain_toolset  # noqa: E402


def get_repo():
    """Plain SQL repository for ground truth (no retries needed for reads)."""
    from repository import SqlRepository
    return SqlRepository()


def demo(repo, seed: int = cfg.SEED) -> None:
    """Run tasks A, B, C once each without any follow-up prompt."""
    print(f"PART 2 I - three multi-step verification tasks (no follow-up prompting), seed {seed}\n")
    total = 0
    for task in TASKS:
        print(f"--- Task {task.task_id} ({task.kind}) ---")
        res = run_agent(task.prompt, required_tools=list(task.required_tools),
                        seed=seed, tags={"part": "2-demo", "task": task.task_id})
        v = verify(task, res, repo)
        total += res.tool_calls
        print(f"    verifier: {'PASS' if v.passed else 'FAIL'} ({v.reason})")
        print(f"    tool calls in this task: {res.tool_calls}\n")
    print(f"TOTAL tool calls across tasks A-C: {total}")


def recovery(seed: int = cfg.SEED) -> None:
    """Nonexistent and impossible IDs: execute_tool returns a useful error, the agent does not crash."""
    from domain_tools import execute_tool
    print("PART 2 II - error recovery\n")
    for code in ("INC-999999", "INC-12", "12345"):
        print(f"execute_tool('get_incident', {{'incident_code': '{code}'}}) ->")
        print("    " + execute_tool("get_incident", {"incident_code": code}))
    print("\nAgent run on a nonexistent ID:")
    res = run_agent(ERROR_RECOVERY_PROMPT, required_tools=["get_incident"], seed=seed,
                    tags={"part": "2-recovery"})
    print(f"\nRESULT: stop_reason={res.stop_reason}, tool_calls={res.tool_calls}, crashed=False")


def reliability(n: int, repo) -> None:
    """n tool-use attempts spread over the three fixed tasks; raw rows + summary."""
    print(f"PART 2 III - reliability: {n} attempts over tasks A/B/C | model {cfg.MODEL_NAME} "
          f"temperature {cfg.AGENT_TEMPERATURE} num_predict {cfg.AGENT_NUM_PREDICT} "
          f"max_iterations {cfg.MAX_ITERATIONS} max_repairs {cfg.MAX_REPAIRS} | seed per attempt = "
          f"VERIFY_SEED + attempt\n")
    rows, opp_total, first_ok, after_ok = [], 0, 0, 0
    failure_counts: Counter = Counter()
    toolset = domain_toolset()
    for i in range(n):
        task = TASKS[i % len(TASKS)]
        seed = cfg.VERIFY_SEED + i
        print(f"--- attempt {i + 1}/{n}: task {task.task_id}, seed {seed} ---")
        res = run_agent(task.prompt, toolset=toolset, required_tools=list(task.required_tools),
                        seed=seed, tags={"part": "2-reliability", "task": task.task_id, "attempt": i + 1})
        v = verify(task, res, repo)
        opps = res.opportunities
        n_first = sum(o.first_try_ok for o in opps)
        n_after = sum(o.first_try_ok or o.repaired for o in opps)
        opp_total += len(opps)
        first_ok += n_first
        after_ok += n_after
        failure_counts.update(res.failures)
        row = {"attempt": i + 1, "task": task.task_id, "seed": seed, "stop_reason": res.stop_reason,
               "iterations": res.iterations, "tool_calls": res.tool_calls,
               "call_opportunities": len(opps), "well_formed_first_try": n_first,
               "well_formed_after_repair": n_after, "repairs_used": res.repairs_used,
               "chain_complete": res.chain_complete,
               "failures": ";".join(res.failures) or "none",
               **{f"n_{f}": res.failures.count(f) for f in FAILURE_TYPES},
               "verifier_pass": v.passed, "verifier_reason": v.reason,
               "unsupported_claims": ";".join(unsupported_claims(res, task.prompt)),
               "tokens": res.total_tokens, "latency_ms": res.latency_ms,
               "tools_called": " > ".join(t["tool"] for t in res.tool_trace),
               "answer": (res.answer or "").replace("\n", " ")[:500]}
        rows.append(row)
        print(f"    => opportunities {len(opps)}, first-try ok {n_first}, after repair ok {n_after}, "
              f"failures [{row['failures']}], verifier {'PASS' if v.passed else 'FAIL'}\n")

    cfg.ensure_dirs()
    with open(cfg.RAW_DIR / "part2_reliability_attempts.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    attempts_clean = sum(1 for r in rows if r["failures"] == "none")
    attempts_ok_after = sum(1 for r in rows if r["chain_complete"] and r["stop_reason"] == "final_answer")
    summary = {
        "attempts": n, "model": cfg.MODEL_DESCRIPTION, "temperature": cfg.AGENT_TEMPERATURE,
        "call_opportunities": opp_total,
        "well_formed_before_repair": first_ok, "well_formed_after_repair": after_ok,
        "rate_before_repair": round(first_ok / opp_total, 3) if opp_total else None,
        "rate_after_repair": round(after_ok / opp_total, 3) if opp_total else None,
        "attempts_without_any_failure": attempts_clean,
        "attempts_completed_full_chain": attempts_ok_after,
        "verifier_pass": sum(r["verifier_pass"] for r in rows),
        "failures_by_type": {f: failure_counts.get(f, 0) for f in FAILURE_TYPES},
        "per_task": {t.task_id: {
            "attempts": sum(r["task"] == t.task_id for r in rows),
            "verifier_pass": sum(r["verifier_pass"] for r in rows if r["task"] == t.task_id),
            "repairs_used": sum(r["repairs_used"] for r in rows if r["task"] == t.task_id)}
            for t in TASKS},
    }
    (cfg.RAW_DIR / "part2_reliability_summary.json").write_text(json.dumps(summary, indent=2))
    (cfg.RAW_DIR / "part2_reliability_attempts.json").write_text(json.dumps(rows, indent=2))

    print("=" * 70)
    print(f"RELIABILITY SUMMARY ({n} attempts, {opp_total} tool-call opportunities)")
    print(f"  well-formed calls BEFORE repair : {first_ok}/{opp_total} = {summary['rate_before_repair']:.1%}")
    print(f"  well-formed calls AFTER repair  : {after_ok}/{opp_total} = {summary['rate_after_repair']:.1%}")
    print(f"  attempts with no failure        : {attempts_clean}/{n}")
    print(f"  attempts completing full chain  : {attempts_ok_after}/{n}")
    print(f"  verifier pass                   : {summary['verifier_pass']}/{n}")
    for f in FAILURE_TYPES:
        print(f"  failures - {f:<26}: {failure_counts.get(f, 0)}")
    print("raw: reports/hw07/raw/part2_reliability_attempts.csv / .json, part2_reliability_summary.json")


def main() -> None:
    """Parse flags and run the requested sections inside one RUN_LOG section."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--recovery", action="store_true")
    ap.add_argument("--reliability", type=int, default=0, metavar="N")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=cfg.SEED, help="model seed for --demo / --recovery")
    a = ap.parse_args()
    if a.all:
        a.demo, a.recovery, a.reliability = True, True, a.reliability or 21
    if not (a.demo or a.recovery or a.reliability):
        ap.error("choose --demo, --recovery, --reliability N or --all")
    repo = get_repo()
    with cfg.run_log("HW7 PART 2 - hand-written agent loop"):
        if a.demo:
            demo(repo, a.seed)
        if a.recovery:
            recovery(a.seed)
        if a.reliability:
            reliability(a.reliability, repo)


if __name__ == "__main__":
    main()
