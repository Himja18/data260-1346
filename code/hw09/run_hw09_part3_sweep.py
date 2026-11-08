"""HW9 Part 3.2-3.4 - threshold sweep over the 40 labelled cases in cache_cases.yaml.

    python code/hw09/run_hw09_part3_sweep.py              # agent runs are saved and reused on a re-run
    python code/hw09/run_hw09_part3_sweep.py --fresh-agent-runs

Method
 1. Clear s1346:semcache:* and fill the cache with the 12 seeds (answers from the HW8 pipeline).
 2. Run every distinct case question through the HW8 pipeline ONCE -> its correct answer and its real
    miss latency (exact duplicates have the seed's text, so they reuse the seed run).
    Saved to reports/hw09/raw/part3_agent_runs.json (re-runs reuse it unless --fresh-agent-runs).
 3. For each threshold 0.75 ... 0.95 and each case: a real cache lookup (embed + RediSearch KNN 1 +
    version check on a hit). HIT -> latency = lookup. MISS -> latency = lookup + that question's measured
    agent latency. Case answers are not inserted during the sweep, so every case sees the same 12 seeds.
 4. hit rate, false-hit rate, mean latency and total cost (cost model from hw09_config / --cost-*).
"""
import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

import hw09_config as cfg  # noqa: E402
from hw09_common import banner, incident_codes, setup_logging, short, write_json  # noqa: E402
from run_hw09_part2 import build_cache  # noqa: E402

AGENT_RUNS = "part3_agent_runs.json"


def load_cases() -> tuple[dict, list]:
    """seeds (id -> query) and the 40 cases, with basic checks."""
    data = yaml.safe_load(cfg.CACHE_CASES.read_text(encoding="utf-8"))
    seeds = {s["id"]: s["query"] for s in data["seeds"]}
    cases = data["cases"]
    groups = {}
    for c in cases:
        groups[c["group"]] = groups.get(c["group"], 0) + 1
    assert len(cases) == 40 and all(n == 10 for n in groups.values()), groups
    return seeds, cases


def agent_runs(cache, queries: list[str], log, fresh: bool) -> dict:  # noqa: ANN001
    """query -> {answer, agent_ms, data_version}; each distinct query through the pipeline once."""
    path = cfg.RAW_DIR / AGENT_RUNS
    runs = {} if fresh or not path.exists() else json.loads(path.read_text(encoding="utf-8"))
    todo = [q for q in queries if q not in runs]
    log.info("agent runs: %d saved, %d to run through the HW8 pipeline", len(queries) - len(todo), len(todo))
    for i, q in enumerate(todo, 1):
        log.info("agent run %d/%d: %s", i, len(todo), short(q, 90))
        answer, codes, version, t = cache.run_agent(q)
        runs[q] = {"answer": answer, "agent_ms": t["agent"], "deps": codes, "data_version": version}
        log.info("   %.0f ms | %s", t["agent"], short(answer, 120))
        write_json(AGENT_RUNS, runs)                       # save as we go (resume after a crash)
    return runs


def main() -> None:  # noqa: PLR0915
    """Run the sweep."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh-agent-runs", action="store_true")
    ap.add_argument("--cost-miss", type=float, default=cfg.COST_MISS)
    ap.add_argument("--cost-false-hit", type=float, default=cfg.COST_FALSE_HIT)
    ap.add_argument("--fake-agent", action="store_true", help="offline test only")
    args = ap.parse_args()
    log = setup_logging("part3-sweep")
    banner(log, "Part 3 - threshold sweep")
    seeds, cases = load_cases()
    cache = build_cache(log, cfg.DEFAULT_THRESHOLD, args.fake_agent)

    # 1-2. one pipeline run per distinct question
    distinct = list(dict.fromkeys(list(seeds.values()) + [c["query"] for c in cases]))
    runs = agent_runs(cache, distinct, log, args.fresh_agent_runs)
    log.info("cleared %d entries; storing the %d seeds", cache.clear(), len(seeds))
    for q in seeds.values():
        run = runs[q]
        cache.store(q, cache.embedder.embed(q), run["answer"], run["deps"], run["data_version"], run["agent_ms"])
    seed_by_query = {q: sid for sid, q in seeds.items()}

    # 3. sweep
    rows, table = [], []
    for thr in cfg.THRESHOLDS:
        for c in cases:
            t0 = time.perf_counter()
            match, _vec, _tm = cache.lookup(c["query"])
            sim = match.similarity if match else 0.0
            nearest = seed_by_query.get(match.fields["query"]) if match else None
            hit = match is not None and sim >= thr
            if hit and match.fields["deps"]:
                cache.facts.data_version([d for d in match.fields["deps"].split(",") if d])  # same work as ask()
            lookup_ms = (time.perf_counter() - t0) * 1000
            latency = lookup_ms if hit else lookup_ms + runs[c["query"]]["agent_ms"]
            false_hit = hit and (not c["should_hit"] or nearest != c["seed"])
            rows.append({"threshold": thr, "id": c["id"], "group": c["group"], "should_hit": c["should_hit"],
                         "expected_seed": c["seed"], "nearest_seed": nearest, "similarity": round(sim, 4),
                         "hit": hit, "false_hit": false_hit, "correct_hit": hit and not false_hit,
                         "latency_ms": round(latency, 1), "lookup_ms": round(lookup_ms, 2), "query": c["query"]})
        cur = [r for r in rows if r["threshold"] == thr]
        hits = sum(r["hit"] for r in cur)
        false_hits = sum(r["false_hit"] for r in cur)
        misses = len(cur) - hits
        cost = misses * args.cost_miss + false_hits * args.cost_false_hit
        table.append({"threshold": thr, "hits": hits, "hit_rate": round(hits / len(cur), 3),
                      "false_hits": false_hits,
                      "false_hit_rate": round(false_hits / hits, 3) if hits else 0.0,       # of hits served
                      "false_hit_rate_all": round(false_hits / len(cur), 3),                # of all 40 queries
                      "missed_should_hit": sum(r["should_hit"] and not r["hit"] for r in cur),
                      "misses": misses, "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in cur), 1),
                      "total_cost": round(cost, 2)})

    # similarity of every case (identical for every threshold)
    log.info("==== similarity of each case to its nearest cached seed ====")
    for r in [r for r in rows if r["threshold"] == cfg.THRESHOLDS[0]]:
        log.info("%s %-22s sim=%.4f nearest=%-4s expected=%-4s should_hit=%-5s | %s", r["id"], r["group"],
                 r["similarity"], r["nearest_seed"], r["expected_seed"], r["should_hit"], short(r["query"], 70))
    for grp in ("exact_duplicate", "paraphrase", "superficially_similar", "unrelated"):
        sims = [r["similarity"] for r in rows if r["threshold"] == cfg.THRESHOLDS[0] and r["group"] == grp]
        log.info("  %-22s similarity min %.3f  mean %.3f  max %.3f", grp, min(sims), statistics.mean(sims), max(sims))

    log.info("==== threshold table (cost: miss $%.2f, false hit $%.2f) ====", args.cost_miss, args.cost_false_hit)
    log.info("threshold | hit rate      | false-hit rate (of hits) | mean latency (ms) | total cost")
    for t in table:
        log.info("  %.2f    | %2d/40 = %4.0f%% | %2d/%-2d = %5.1f%%          | %17.1f | $%.2f", t["threshold"],
                 t["hits"], 100 * t["hit_rate"], t["false_hits"], t["hits"], 100 * t["false_hit_rate"],
                 t["mean_latency_ms"], t["total_cost"])
    best = min(table, key=lambda t: (t["total_cost"], -t["threshold"]))
    log.info("lowest total cost: threshold %.2f ($%.2f)", best["threshold"], best["total_cost"])

    # 3.3 one false hit in full (prefer 0.85, prefer a superficially-similar case)
    fh = None
    for thr in (0.85, *cfg.THRESHOLDS):
        cands = [r for r in rows if r["threshold"] == thr and r["false_hit"]]
        cands.sort(key=lambda r: (r["group"] != "superficially_similar", -r["similarity"]))
        if cands:
            fh = cands[0]
            break
    if fh:
        cached_q = seeds[fh["nearest_seed"]]
        incoming = fh["query"]
        codes = incident_codes(cached_q) + incident_codes(incoming)
        example = {"threshold": fh["threshold"], "case_id": fh["id"], "group": fh["group"],
                   "cached_query": cached_q, "incoming_query": incoming, "similarity": fh["similarity"],
                   "cached_answer_returned": runs[cached_q]["answer"], "correct_answer": runs[incoming]["answer"],
                   "s1346_rel_rows": {k: {f: str(v) for f, v in row.items()}
                                      for k, row in cache.facts.facts_for_codes(codes).items()}}
        log.info("==== 3.3 false hit (threshold %.2f, case %s) ====", fh["threshold"], fh["id"])
        for k, v in example.items():
            log.info("  %-22s %s", k, v if isinstance(v, (int, float)) else short(json.dumps(v, default=str)
                                                                                   if isinstance(v, dict) else v, 400))
        write_json("part3_false_hit.json", example)
    else:
        log.info("no false hit at any threshold")

    write_json("part3_thresholds.json", {"cost_miss": args.cost_miss, "cost_false_hit": args.cost_false_hit,
                                         "table": table, "lowest_cost_threshold": best["threshold"]})
    with open(cfg.RAW_DIR / "part3_sweep.csv", "w", newline="", encoding="utf-8") as fh_csv:
        w = csv.DictWriter(fh_csv, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    log.info("saved reports/hw09/raw/part3_thresholds.json, part3_sweep.csv, part3_false_hit.json, %s", AGENT_RUNS)
    cache.agent.close()


if __name__ == "__main__":
    main()
