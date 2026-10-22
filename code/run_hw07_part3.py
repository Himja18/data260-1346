"""HW7 Part 3 runner - original loop vs Reflexion loop on the same three fixed tasks.

    python code/run_hw07_part3.py --repeats 3        # 3 runs per task per loop (seeded)
    python code/run_hw07_part3.py --fault-demo       # guaranteed failed-then-retried example

--fault-demo makes ONLY the first attempt's get_incident return an injected outage error,
so task A fails, a reflection is written from that evidence, and the retry (normal tools)
is verified again. It is labelled as fault injection in the logs and raw files.

Raw data: reports/hw07/raw/part3_comparison_runs.csv/.json, part3_comparison_summary.json,
reflections.jsonl. Output mirrored to reports/hw07/RUN_LOG.txt.
"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hw07_config as cfg  # noqa: E402
from agent_loop.loop import run_agent  # noqa: E402
from agent_loop.reflexion import REFLECTIONS_PATH, run_with_reflexion  # noqa: E402
from agent_loop.tasks import TASKS, TASKS_BY_ID, lenient_verify, unsupported_claims, verify  # noqa: E402
from agent_loop.toolset import SchemaToolset, domain_toolset  # noqa: E402

USER_ID = cfg.PREFIX


def outage_toolset() -> SchemaToolset:
    """Domain tools where get_incident always fails (fault injection for the demo)."""
    ts = domain_toolset()
    desc, schema, _ = ts.tools["get_incident"]
    ts.tools["get_incident"] = (desc, schema, lambda args: json.dumps(
        {"ok": False, "data": None, "error": "get_incident unavailable: database timeout (injected fault)"}))
    return ts


def fault_demo(repo) -> None:
    """One failed-then-retried Reflexion run with stored reflection + evidence."""
    print("PART 3 - fault-injection demo (first attempt only: get_incident outage)\n")
    out = run_with_reflexion(TASKS_BY_ID["A"], USER_ID, repo, first_toolset=outage_toolset(),
                             seed=cfg.VERIFY_SEED, log_path=cfg.RAW_DIR / "agent_runs.jsonl")
    print(f"\nRESULT: stop_reason={out['stop_reason']} retries={out['retries']} "
          f"tool_calls={out['tool_calls']} tokens={out['tokens']}")
    print("Stored reflection(s):")
    from agent_loop.reflexion import load_reflections
    for r in load_reflections(USER_ID, out["reflexion_run_id"]):
        print(json.dumps(r, indent=2))


def compare(repeats: int, repo) -> None:
    """Same tasks, same seeds: original loop once vs Reflexion loop (<= 2 retries)."""
    print(f"PART 3 - comparison: {repeats} run(s) per task per loop | model {cfg.MODEL_NAME} "
          f"temperature {cfg.AGENT_TEMPERATURE} | Reflexion: <= {cfg.MAX_REFLEXION_RETRIES} retries, "
          f"budget {cfg.REFLEXION_TOOL_CALL_BUDGET} tool calls / {cfg.REFLEXION_TOKEN_BUDGET} tokens\n")
    rows = []
    for r in range(repeats):
        for task in TASKS:
            seed = cfg.VERIFY_SEED + 100 + r * 10
            print(f"--- task {task.task_id}, repeat {r + 1}, seed {seed}: ORIGINAL ---")
            res = run_agent(task.prompt, required_tools=list(task.required_tools), seed=seed,
                            tags={"part": "3-original", "task": task.task_id, "repeat": r + 1})
            v = verify(task, res, repo)
            rows.append({"loop": "original", "task": task.task_id, "repeat": r + 1, "seed": seed,
                         "success": v.passed, "verifier_reason": v.reason,
                         "lenient_pass": lenient_verify(task, res, repo),
                         "unsupported_claims": len(unsupported_claims(res, task.prompt)),
                         "unsupported_list": ";".join(unsupported_claims(res, task.prompt)),
                         "retries": 0, "stop_reason": "success" if v.passed else res.stop_reason,
                         "tool_calls": res.tool_calls, "tokens": res.total_tokens,
                         "latency_ms": res.latency_ms, "answer": (res.answer or "")[:400]})
            print(f"    original verifier: {'PASS' if v.passed else 'FAIL'} ({v.reason})\n")
            print(f"--- task {task.task_id}, repeat {r + 1}, seed {seed}: REFLEXION ---")
            out = run_with_reflexion(task, USER_ID, repo, seed=seed,
                                     log_path=cfg.RAW_DIR / "agent_runs.jsonl")
            fin, fv = out["final"], out["final_verdict"]
            rows.append({"loop": "reflexion", "task": task.task_id, "repeat": r + 1, "seed": seed,
                         "success": fv.passed, "verifier_reason": fv.reason,
                         "lenient_pass": lenient_verify(task, fin, repo),
                         "unsupported_claims": len(unsupported_claims(fin, task.prompt)),
                         "unsupported_list": ";".join(unsupported_claims(fin, task.prompt)),
                         "retries": out["retries"], "stop_reason": out["stop_reason"],
                         "tool_calls": out["tool_calls"], "tokens": out["tokens"],
                         "latency_ms": out["latency_ms"], "answer": (fin.answer or "")[:400],
                         "reflexion_run_id": out["reflexion_run_id"],
                         "attempt_verdicts": " | ".join(a["verdict"].reason for a in out["attempts"])})
            print(f"    reflexion stop={out['stop_reason']} retries={out['retries']}\n")

    cfg.ensure_dirs()
    fields = sorted({k for row in rows for k in row}, key=lambda k: list(rows[-1]).index(k)
                    if k in rows[-1] else 99)
    with open(cfg.RAW_DIR / "part3_comparison_runs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    (cfg.RAW_DIR / "part3_comparison_runs.json").write_text(json.dumps(rows, indent=2))

    def summarize(loop: str) -> dict:
        rs = [x for x in rows if x["loop"] == loop]
        n = len(rs)
        return {
            "runs": n,
            "task_success": f"{sum(x['success'] for x in rs)}/{n}",
            "task_success_rate": round(sum(x["success"] for x in rs) / n, 3),
            "unsupported_claims": sum(x["unsupported_claims"] for x in rs),
            "retry_rate": round(sum(x["retries"] > 0 for x in rs) / n, 3),
            "total_retries": sum(x["retries"] for x in rs),
            "tool_calls_mean": round(statistics.mean(x["tool_calls"] for x in rs), 2),
            "tool_calls_total": sum(x["tool_calls"] for x in rs),
            "tokens_mean": round(statistics.mean(x["tokens"] for x in rs)),
            "latency_ms_mean": round(statistics.mean(x["latency_ms"] for x in rs)),
            "verifier_possible_false_rejections": sum((not x["success"]) and x["lenient_pass"] for x in rs),
            "stop_reasons": {s: sum(x["stop_reason"] == s for x in rs) for s in
                             sorted({x["stop_reason"] for x in rs})},
        }

    summary = {"original": summarize("original"), "reflexion": summarize("reflexion"),
               "note": "verifier_possible_false_rejections = strict verifier FAIL but lenient re-check "
                       "PASS; each flagged run must be reviewed by hand (see part3_comparison_runs.csv)."}
    (cfg.RAW_DIR / "part3_comparison_summary.json").write_text(json.dumps(summary, indent=2))
    o, f = summary["original"], summary["reflexion"]
    print("=" * 72)
    print(f"{'Metric':<34}{'Original loop':>18}{'Reflexion loop':>18}")
    for label, key in [("Task success", "task_success"), ("Unsupported claims", "unsupported_claims"),
                       ("Retry rate", "retry_rate"), ("Tool calls (mean per task)", "tool_calls_mean"),
                       ("Tokens (mean per task)", "tokens_mean"), ("Latency ms (mean per task)", "latency_ms_mean"),
                       ("Verifier false rejections (flagged)", "verifier_possible_false_rejections")]:
        print(f"{label:<34}{o[key]!s:>18}{f[key]!s:>18}")
    print(f"stop reasons: original {o['stop_reasons']} | reflexion {f['stop_reasons']}")
    flagged = [x for x in rows if not x["success"] and x["lenient_pass"]]
    for x in flagged:
        print(f"FLAGGED for manual review: {x['loop']} task {x['task']} repeat {x['repeat']}: "
              f"{x['verifier_reason']} | answer: {x['answer'][:200]}")
    print(f"raw: reports/hw07/raw/part3_comparison_*.json/csv, {REFLECTIONS_PATH.name}")


def main() -> None:
    """Parse flags and run inside one RUN_LOG section."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=0)
    ap.add_argument("--fault-demo", action="store_true")
    a = ap.parse_args()
    if not (a.repeats or a.fault_demo):
        ap.error("choose --repeats N and/or --fault-demo")
    from repository import SqlRepository
    repo = SqlRepository()
    with cfg.run_log("HW7 PART 3 - Reflexion"):
        if a.fault_demo:
            fault_demo(repo)
        if a.repeats:
            compare(a.repeats, repo)


if __name__ == "__main__":
    main()
