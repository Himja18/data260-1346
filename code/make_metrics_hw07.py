"""Rebuild reports/hw07/METRICS.md from the raw result files (make hw07-metrics).

Every number in METRICS.md comes from reports/hw07/raw/*; missing parts are marked "not run yet".
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hw07_config as cfg  # noqa: E402

RAW = cfg.RAW_DIR


def load(name: str):
    """JSON file from raw/ or None."""
    p = RAW / name
    return json.loads(p.read_text()) if p.exists() else None


def part2() -> list[str]:
    """Reliability table."""
    s = load("part2_reliability_summary.json")
    if not s:
        return ["_not run yet - `make hw07-reliability`_"]
    f = s["failures_by_type"]
    out = [f"{s['attempts']} attempts over tasks A/B/C, {s['model']}, temperature {s['temperature']}, "
           f"{s['call_opportunities']} tool-call opportunities.", "",
           "| Metric | Before repair path | After repair path |", "|---|---|---|",
           f"| Well-formed tool calls | {s['well_formed_before_repair']}/{s['call_opportunities']} "
           f"({s['rate_before_repair']:.1%}) | {s['well_formed_after_repair']}/{s['call_opportunities']} "
           f"({s['rate_after_repair']:.1%}) |",
           f"| Attempts with no failure / completing the chain | {s['attempts_without_any_failure']}/{s['attempts']} | "
           f"{s['attempts_completed_full_chain']}/{s['attempts']} |", "",
           "| Failure class | Count |", "|---|---|"]
    out += [f"| {k.replace('_', ' ')} | {v} |" for k, v in f.items()]
    out += ["", f"Verifier pass: {s['verifier_pass']}/{s['attempts']}. Per task: " +
            ", ".join(f"{t}: {v['verifier_pass']}/{v['attempts']} pass, {v['repairs_used']} repairs"
                      for t, v in s["per_task"].items()),
            "", "Raw: `raw/part2_reliability_attempts.csv`, `raw/part2_reliability_summary.json`."]
    return out


def part3() -> list[str]:
    """Original vs Reflexion table."""
    s = load("part3_comparison_summary.json")
    if not s:
        return ["_not run yet - `make hw07-part3`_"]
    o, r = s["original"], s["reflexion"]
    rows = [("Task success", "task_success"), ("Unsupported claims", "unsupported_claims"),
            ("Retry rate", "retry_rate"), ("Tool calls (mean per task run)", "tool_calls_mean"),
            ("Tokens (mean per task run)", "tokens_mean"), ("Latency (ms, mean per task run)", "latency_ms_mean"),
            ("Verifier false rejections (flagged, then checked by hand)", "verifier_possible_false_rejections")]
    out = ["| Metric | Original loop | Reflexion loop |", "|---|---|---|"]
    out += [f"| {label} | {o[k]} | {r[k]} |" for label, k in rows]
    out += ["", f"Stop reasons - original: {o['stop_reasons']}; Reflexion: {r['stop_reasons']}.",
            "", "Raw: `raw/part3_comparison_runs.csv`, `raw/part3_comparison_summary.json`, `raw/reflections.jsonl`."]
    return out


def part4() -> list[str]:
    """Two acceptance cases."""
    out = ["| Scenario | Rows | Riders | Agent decision | Tool-computed | Pay-per-use | Membership total | "
           "Break-even vs actual (rides/rider-month) | Steps | Time (s) | Stop reason | Snapshot SHA-256 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    found = False
    for s in ("membership_wins", "payg_wins"):
        r = load(f"part4_{s}_summary.json")
        if not r:
            out.append(f"| {s} | _not run yet_ |" + " |" * 10)
            continue
        found = True
        c, m = r.get("computed", {}), r.get("metrics", {})
        out.append(f"| {s} | {r['dataset']['rows']} | {c.get('riders')} | {r.get('agent_decision')} | "
                   f"{c.get('decision')} | ${c.get('payg_total')} | ${c.get('membership_total')} | "
                   f"{c.get('break_even_rides_per_rider_month')} vs {c.get('actual_rides_per_rider_month')} | "
                   f"{m.get('step_count')} | {round((m.get('total_time_ms') or 0) / 1000, 1)} | "
                   f"{r.get('stop_reason')} | `{(r.get('snapshot') or {}).get('sha256', '')[:16]}...` |")
    if found:
        snap = load("pricing_snapshots/membership_wins/pricing_snapshot.json") or {}
        out += ["", f"Pricing source: {snap.get('url')} -> {snap.get('final_url')}, accessed {snap.get('accessed_at')}.",
                "Snapshots: `raw/pricing_snapshots/<scenario>/pricing_snapshot.txt|json`."]
    return out


def part5() -> list[str]:
    """Attack table."""
    rows = load("part5_attack_results.json")
    if not rows:
        return ["_not run yet - `make hw07-part5`_"]
    names = {"override": "Recommendation override", "sql": "Non-SELECT tool misuse", "exfil": "Data exfiltration"}
    out = ["| Attack | Before defenses | After prompt defense | After prompt + tool defense |", "|---|---|---|---|"]
    for a, label in names.items():
        cells = []
        for c in ("before", "prompt", "prompt_tool"):
            rs = [x for x in rows if x["attack"] == a and x["config"] == c]
            if not rs:
                cells.append("-")
                continue
            n = sum(x["succeeded"] for x in rs)
            cells.append(f"{'**succeeded**' if n else 'blocked'} ({n}/{len(rs)})")
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    out += ["", "Raw: `raw/part5_attack_results.json/.csv`; excerpts per cell in the CSV `excerpt` column."]
    return out


def part6() -> list[str]:
    """Gate results."""
    rows = load("part6_safety_gate_results.json")
    integ = load("part6_integration.json")
    if not rows:
        return ["_not run yet - `make hw07-part6`_"]
    main_rows = [r for r in rows if not r.get("extra")]
    out = ["| Command | Expected | v1 (allow-list only) | Final gate | is_destructive |", "|---|---|---|---|---|"]
    out += [f"| `{r['command']}` | {r['expected']} | {r['v1_prefix_only']} | {r['final']} | {r['is_destructive']} |"
            for r in main_rows]
    fa = [r["command"] for r in main_rows if r["v1_prefix_only"] == "allow" and r["expected"] == "block"]
    out += ["", f"Final: {sum(r['correct'] for r in main_rows)}/{len(main_rows)} correct; v1 false allows fixed: {fa}.",
            f"Integration (glob -> search -> read): {'PASS' if integ and integ['passed'] else 'FAIL / not run'}"
            + (f", tool order {' -> '.join(integ['tool_order'])}" if integ else "")]
    return out


def main() -> None:
    """Write METRICS.md."""
    lines = [f"# HW7 metrics - {cfg.STUDENT_NAME} ({cfg.PREFIX})", "",
             f"Model: {cfg.MODEL_DESCRIPTION} | hardware: {cfg.HARDWARE} | SEED {cfg.SEED} | "
             f"VERIFY_SEED {cfg.VERIFY_SEED} | generated {cfg.now_iso()} by `code/make_metrics_hw07.py`", "",
             "## Part 2 - tool-call reliability", "", *part2(), "",
             "## Part 3 - original vs Reflexion", "", *part3(), "",
             "## Part 4 - Bay Wheels acceptance cases", "", *part4(), "",
             "## Part 5 - prompt-injection attacks", "", *part5(), "",
             "## Part 6 - safety gate", "", *part6(), ""]
    (cfg.REPORT_DIR / "METRICS.md").write_text("\n".join(lines))
    print("wrote reports/hw07/METRICS.md")


if __name__ == "__main__":
    main()
