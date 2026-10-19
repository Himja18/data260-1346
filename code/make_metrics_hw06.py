"""DATA-260 HW6 - build reports/hw06/METRICS.md (+ raw/memory_cost.json) from the raw files.

    python code/make_metrics_hw06.py

Inputs (reports/hw06/raw/): memory_summary.json, consolidation_report.json,
agent_md_check.json (optional), ../verification.json (optional).
Part 3.5 pricing: $1 per 1M input tokens, $5 per 1M output tokens, 10,000 conversations x 30 turns.
"""
import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HW = REPO / "reports" / "hw06"
RAW = HW / "raw"
ORDER = ["n4", "n12", "n30", "policy"]
NAMES = {"n4": "SHORT_TERM_N=4", "n12": "SHORT_TERM_N=12", "n30": "SHORT_TERM_N=30",
         "policy": "Eviction/compression policy (N=30 + compress_assistant)"}
PRICE_IN, PRICE_OUT = 1.0, 5.0          # USD per 1M tokens
CONVERSATIONS, TURNS = 10_000, 30
QUALITY_TOLERANCE = 0.5                 # "best" must be within 0.5 probe points of the top score


def load(name: str):
    """Read a JSON file from raw/ (None if missing)."""
    path = RAW / name
    return json.loads(path.read_text()) if path.exists() else None


def cost_rows(summary: dict) -> list:
    """Cost of 10,000 30-turn conversations per setting."""
    rows = []
    for key in [k for k in ORDER if k in summary]:
        s = summary[key]
        reply_in, reply_out = s["mean_prompt_tokens_full"] * TURNS, s["mean_completion_tokens"] * TURNS
        aux_in, aux_out = s["mean_aux_prompt_tokens"] * TURNS, s["mean_aux_completion_tokens"] * TURNS
        reply_cost = CONVERSATIONS * (reply_in * PRICE_IN + reply_out * PRICE_OUT) / 1e6
        total_cost = CONVERSATIONS * ((reply_in + aux_in) * PRICE_IN + (reply_out + aux_out) * PRICE_OUT) / 1e6
        rows.append({"setting": key, "name": NAMES[key], "probe": s["mean_probe_score"],
                     "input_tokens_per_conv": round(reply_in), "output_tokens_per_conv": round(reply_out),
                     "maintenance_input_per_conv": round(aux_in), "maintenance_output_per_conv": round(aux_out),
                     "cost_reply_only_usd": round(reply_cost, 2), "cost_total_usd": round(total_cost, 2)})
    return rows


def pick_best_worst(rows: list) -> tuple:
    """Best = cheapest setting whose probe score is within 0.5 of the top; worst = most expensive."""
    top = max(r["probe"] for r in rows)
    eligible = [r for r in rows if r["probe"] >= top - QUALITY_TOLERANCE]
    best = min(eligible, key=lambda r: (r["cost_total_usd"], -r["probe"]))
    worst = max(rows, key=lambda r: (r["cost_total_usd"], -r["probe"]))
    return best, worst


def part3(summary: dict) -> list:
    """Markdown for Part 3."""
    md = ["## Part 3 - What memory costs", "",
          "Same 30-message conversation (`reports/hw06/cases/conversation_30.json`) in a fresh user + session "
          "per setting, then the 5 probes of `reports/hw06/memory_probes.yaml` (1-5 rubric, scored automatically). "
          "Means are over the 30 conversation turns. Prompt tokens = full templated prompt counted with "
          f"`{summary[next(iter(summary))]['token_count_method']}`; Ollama's own "
          "`prompt_eval_count` is shown separately; it can be lower because Ollama may reuse a KV-cached prompt prefix. "
          "Latency = server time for the whole /api/chat request (reply + fact extraction + summaries).", "",
          "| Setting | Mean prompt tokens/turn | Mean latency (ms) | Probe quality (1-5) |",
          "|---|---|---|---|"]
    for k in [k for k in ORDER if k in summary]:
        s = summary[k]
        md.append(f"| {NAMES[k]} | {s['mean_prompt_tokens_full']:.1f} | {s['mean_latency_ms']:.0f} | "
                  f"{s['mean_probe_score']:.2f} |")
    md += ["", "### Where the prompt tokens go (means per turn)", "",
           "| Setting | System primer | Long-term summary | Short-term window | Episodic facts | "
           "Ollama prompt_eval_count | Completion | Model latency (ms) |", "|---|---|---|---|---|---|---|---|"]
    for k in [k for k in ORDER if k in summary]:
        s = summary[k]
        md.append(f"| {NAMES[k]} | {s['mean_tokens_system_primer']:.0f} | {s['mean_tokens_long_term_summary']:.0f} | "
                  f"{s['mean_tokens_short_term_window']:.0f} | {s['mean_tokens_episodic_facts']:.0f} | "
                  f"{s['mean_prompt_tokens_ollama']:.0f} | {s['mean_completion_tokens']:.0f} | "
                  f"{s['mean_model_latency_ms']:.0f} |")
    md += ["", "### Probe scores per setting", "", "| Probe | " + " | ".join(NAMES[k].split(' (')[0]
                                                                          for k in ORDER if k in summary) + " |",
           "|---" * (1 + sum(k in summary for k in ORDER)) + "|"]
    probe_ids = list(summary[next(iter(summary))]["probe_scores"])
    for pid in probe_ids:
        md.append(f"| {pid} | " + " | ".join(str(summary[k]["probe_scores"].get(pid, "-"))
                                             for k in ORDER if k in summary) + " |")
    if "policy" in summary and "n30" in summary:
        p, b = summary["policy"], summary["n30"]
        saved = b["mean_prompt_tokens_full"] - p["mean_prompt_tokens_full"]
        win_saved = b["mean_tokens_short_term_window"] - p["mean_tokens_short_term_window"]
        md += ["", "### Part 3.4 - Eviction/compression policy vs. its baseline (N=30)", "",
               "Policy `compress_assistant`: the newest 4 messages stay verbatim; older assistant replies in the "
               "window are cut to their first sentence (max 120 chars). User messages are never compressed.", "",
               "| | N=30 (no policy) | N=30 + compress_assistant | Change |", "|---|---|---|---|",
               f"| Mean prompt tokens/turn | {b['mean_prompt_tokens_full']:.1f} | {p['mean_prompt_tokens_full']:.1f} | "
               f"{-saved:+.1f} ({-100 * saved / b['mean_prompt_tokens_full']:+.1f}%) |",
               f"| Mean short-term window tokens | {b['mean_tokens_short_term_window']:.1f} | "
               f"{p['mean_tokens_short_term_window']:.1f} | {-win_saved:+.1f} "
               f"({-100 * win_saved / max(b['mean_tokens_short_term_window'], 1):+.1f}%) |",
               f"| Mean latency (ms) | {b['mean_latency_ms']:.0f} | {p['mean_latency_ms']:.0f} | "
               f"{p['mean_latency_ms'] - b['mean_latency_ms']:+.0f} |",
               f"| Probe quality (1-5) | {b['mean_probe_score']:.2f} | {p['mean_probe_score']:.2f} | "
               f"{p['mean_probe_score'] - b['mean_probe_score']:+.2f} |"]
    rows = cost_rows(summary)
    best, worst = pick_best_worst(rows)
    (RAW / "memory_cost.json").write_text(json.dumps({"pricing_usd_per_1m": {"input": PRICE_IN, "output": PRICE_OUT},
                                                      "conversations": CONVERSATIONS, "turns": TURNS,
                                                      "rows": rows, "best": best["setting"],
                                                      "worst": worst["setting"]}, indent=2))
    md += ["", "### Part 3.5 - Estimated cost of 10,000 30-turn conversations", "",
           "Pricing $1 / 1M input tokens, $5 / 1M output tokens. *Reply only* = the 30 chat calls; "
           "*with memory upkeep* also counts the fact-extraction and summary calls that keep the memory up to date.", "",
           "| Setting | Probe (1-5) | Input tok/conv | Output tok/conv | Cost - reply only | Cost - with memory upkeep |",
           "|---|---|---|---|---|---|"]
    for r in rows:
        tag = " **(best)**" if r is best else " **(worst)**" if r is worst else ""
        md.append(f"| {r['name']}{tag} | {r['probe']:.2f} | {r['input_tokens_per_conv']:,} | "
                  f"{r['output_tokens_per_conv']:,} | ${r['cost_reply_only_usd']:,.2f} | ${r['cost_total_usd']:,.2f} |")
    md += ["", f"Selection rule: **best** = the cheapest setting whose probe score is within {QUALITY_TOLERANCE} "
           f"of the highest score (cost only matters among settings that remember well enough); **worst** = the "
           f"most expensive setting. Best: {best['name']} (${best['cost_total_usd']:,.2f}); "
           f"worst: {worst['name']} (${worst['cost_total_usd']:,.2f}); difference "
           f"${worst['cost_total_usd'] - best['cost_total_usd']:,.2f} per 10,000 conversations."]
    return md


def part4() -> list:
    """Markdown for Part 4."""
    rep = load("consolidation_report.json")
    if not rep:
        return []
    md = ["## Part 4 - File-based memory consolidation", "",
          "`reports/hw06/memory_test/MEMORY_original.md` -> `MEMORY_consolidated.md` (`code/run_consolidation_test.py`)", "",
          "| Metric | Before | After |", "|---|---|---|",
          f"| Lines | {rep['lines_before']} | {rep['lines_after']} |",
          f"| Non-empty, non-comment lines | {rep['content_lines_before']} | {rep['content_lines_after']} |",
          f"| Fact lines | {rep['facts_before']} | {rep['facts_after']} |",
          f"| Duplicate lines merged | - | {len(rep['duplicates_merged'])} |",
          f"| Contradictions resolved (moved to ## Superseded) | - | {len(rep['contradictions'])} |",
          f"| Conflicting values silently lost | - | {len(rep.get('conflicting_values_lost', []))} |", "",
          "| Topic | Kept (newest) | Superseded | Flag | Correct? |", "|---|---|---|---|---|"]
    correct = {c["topic"]: c["correct"] for c in rep.get("resolution_checks", [])}
    for c in rep["contradictions"]:
        old = "; ".join(s["text"] for s in c["superseded"])
        md.append(f"| {c['topic']} | {c['kept']} | {old} | {c['flag']} | "
                  f"{'yes' if correct.get(c['topic'], True) else '**NO**'} |")
    check = load("agent_md_check.json")
    if check:
        md += ["", "### Part 4.4 - AGENT.md compliance (`code/agent_md_check.py`)", "",
               "| Target | Static rules passed | Behaviour test |", "|---|---|---|"]
        for t in check["targets"]:
            passed = sum(r["passed"] for r in t["static"])
            beh = t.get("behaviour")
            beh_txt = "-" if beh is None else (f"{sum(v is True for v in beh.values())}/{len(beh)} passed"
                                               if "error" not in beh else f"error: {beh['error']}")
            md.append(f"| {t['target']} | {passed}/{len(t['static'])} | {beh_txt} |")
    return md


def main() -> None:
    """Write METRICS.md."""
    md = ["# HW6 METRICS - s1346 | Municipal Transit Incidents (DOMAIN_ID = 2)", "",
          "SID4 1346 · PORT_BASE 8446 · PREFIX s1346 · SEED 1346 · VERIFY_SEED 261346 · "
          "model qwen2.5:3b (Ollama, temperature 0, seed 1346) · embeddings BAAI/bge-small-en-v1.5", "",
          f"_Generated by `code/make_metrics_hw06.py` on {datetime.now().isoformat(timespec='seconds')}._", ""]
    summary = load("memory_summary.json")
    if summary:
        md += part3(summary) + [""]
    else:
        md += ["## Part 3", "", "_Run `python code/run_memory_experiment.py` first._", ""]
    md += part4() + [""]
    ver = HW / "verification.json"
    if ver.exists():
        v = json.loads(ver.read_text())
        md += ["## Verification", "", f"`verification.json`: {v['summary']} (commit `{v['commit_hash'][:10]}`)", ""]
    (HW / "METRICS.md").write_text("\n".join(md))
    print(f"Wrote {(HW / 'METRICS.md').relative_to(REPO)}")


if __name__ == "__main__":
    main()
