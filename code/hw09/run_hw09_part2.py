"""HW9 Part 2 - semantic cache in front of the HW8 agent pipeline: 12 test queries.

    python code/hw09/run_hw09_part2.py                 # clears s1346:semcache:*, threshold 0.85
    python code/hw09/run_hw09_part2.py --threshold 0.85 --keep

Needs: Redis Stack (make hw09-redis), Kafka + planner/writer/reviewer running (HW8), MySQL s1346_rel.
Every response is printed with is_cached, similarity and latency; the summary gives the hit rate and
the measured average latency of cached vs non-cached queries.
"""
import argparse
import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw09_config as cfg  # noqa: E402
from hw09_common import (  # noqa: E402
    banner,
    get_embedder,
    get_engine,
    get_redis,
    setup_logging,
    short,
    write_json,
)
from incident_cache import IncidentCache  # noqa: E402
from semantic_cache import SemanticCache  # noqa: E402

# (type, query) - exact duplicates, paraphrases and completely new questions
QUERIES = [
    ("new", "How do I report a bus breakdown to the transit incident desk?"),
    ("new", "What category is incident INC-000042?"),
    ("exact duplicate of #1", "How do I report a bus breakdown to the transit incident desk?"),
    ("paraphrase of #1", "What's the process for reporting a broken-down bus?"),
    ("paraphrase of #2", "Which category was incident INC-000042 filed under?"),
    ("new", "How many passengers were affected by incident INC-000105?"),
    ("exact duplicate of #2", "What category is incident INC-000042?"),
    ("new", "What should I do if my bus is detoured because of a service change?"),
    ("paraphrase of #6", "How many riders were impacted by incident INC-000105?"),
    ("paraphrase of #8", "My bus got rerouted due to a service change, what should I do?"),
    ("new (unrelated)", "What is the weather in San Jose tomorrow?"),
    ("exact duplicate of #6", "How many passengers were affected by incident INC-000105?"),
]


def build_cache(log, threshold: float, fake_agent: bool = False) -> SemanticCache:  # noqa: ANN001
    """Wire Redis, the embedder, s1346_rel and the HW8 pipeline together."""
    from pipeline_agent import FakeAgent, KafkaPipelineAgent
    agent = FakeAgent() if fake_agent else KafkaPipelineAgent(log)
    r = get_redis()
    emb = get_embedder()
    log.info("embedder=%s dim=%d | vector backend=%s | agent=%s", emb.name, emb.dim, cfg.VECTOR_BACKEND, agent.name)
    return SemanticCache(r, emb, IncidentCache(r, get_engine(), log), agent, log, threshold=threshold)


def main() -> None:
    """Run the 12 queries."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=cfg.DEFAULT_THRESHOLD)
    ap.add_argument("--keep", action="store_true", help="keep existing cache entries")
    ap.add_argument("--fake-agent", action="store_true", help="offline test only")
    args = ap.parse_args()
    log = setup_logging("part2")
    banner(log, "Part 2 - semantic response cache")
    cache = build_cache(log, args.threshold, args.fake_agent)
    if not args.keep:
        log.info("cleared %d old entries under %s*", cache.clear(), cfg.SEMCACHE_PREFIX)

    rows = []
    for i, (kind, q) in enumerate(QUERIES, 1):
        log.info("---- Q%02d [%s] %s", i, kind, q)
        res = cache.ask(q)
        log.info("     is_cached=%s similarity=%s latency_ms=%.1f answer=\"%s\"", res.is_cached, res.similarity,
                 res.latency_ms, short(res.answer, 140))
        rows.append({"n": i, "type": kind, **res.to_dict()})

    hits = [r for r in rows if r["is_cached"]]
    misses = [r for r in rows if not r["is_cached"]]
    summary = {
        "queries": len(rows), "hits": len(hits), "misses": len(misses),
        "hit_rate": round(len(hits) / len(rows), 3), "threshold": args.threshold,
        "avg_latency_cached_ms": round(statistics.mean(r["latency_ms"] for r in hits), 1) if hits else None,
        "avg_latency_non_cached_ms": round(statistics.mean(r["latency_ms"] for r in misses), 1) if misses else None,
    }
    if hits and misses:
        summary["observed_speedup_x"] = round(summary["avg_latency_non_cached_ms"] / summary["avg_latency_cached_ms"], 1)

    log.info("==== Part 2 results (threshold %.2f) ====", args.threshold)
    log.info("  #  %-22s cached  sim     latency_ms  query", "type")
    for r in rows:
        log.info("%3d  %-22s %-6s  %-6s  %10.1f  %s", r["n"], r["type"], r["is_cached"],
                 "-" if r["similarity"] is None else f"{r['similarity']:.3f}", r["latency_ms"], short(r["query"], 60))
    log.info("hit rate %d/%d = %.0f%% | avg latency cached %s ms vs non-cached %s ms | speed-up %sx",
             len(hits), len(rows), 100 * summary["hit_rate"], summary["avg_latency_cached_ms"],
             summary["avg_latency_non_cached_ms"], summary.get("observed_speedup_x", "-"))
    log.info("index: %s", cache.index.info())
    log.info("saved %s", write_json("part2_runs.json", {"summary": summary, "rows": rows}))
    with open(cfg.RAW_DIR / "part2_runs.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["n", "type", "query", "is_cached", "similarity", "latency_ms", "matched_query", "answer"])
        for r in rows:
            w.writerow([r["n"], r["type"], r["query"], r["is_cached"], r["similarity"], r["latency_ms"],
                        r["matched_query"], r["answer"]])
    cache.agent.close()


if __name__ == "__main__":
    main()
