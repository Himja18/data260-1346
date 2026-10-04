"""HW5 Part 3 - seeded fault injection: 3 failure rates x 50 calls = 150 calls.

  python code/mcp/run_fault_injection.py            # against MySQL s1346_rel
  python code/mcp/run_fault_injection.py --sqlite   # offline fixture (no MySQL)

Every call goes through the real tool path:
  run_tool -> ResilientRepository (timeout + retries)
           -> FaultInjectingRepository(rate, VERIFY_SEED) -> SqlRepository

The injector uses random.Random(VERIFY_SEED) and is re-created for each rate,
so the same seed always gives the same success/failure sequence. The script
proves this by replaying the draws with a fresh RNG and comparing.

Writes reports/hw05/raw/fault_injection_calls.{csv,json} (all 150 records)
and reports/hw05/raw/fault_injection_summary.json.
"""
import argparse
import csv
import getpass
import hashlib
import json
import math
import os
import random
import sys
from datetime import datetime

from domain_tools import run_tool
from repository import SqlRepository
from resilience import INTERACTIVE, FaultInjectingRepository, ResilientRepository

SID4 = 1346
VERIFY_SEED = 260000 + SID4          # 261346
RATES = [0.0, 0.2, 0.5]
CALLS_PER_RATE = 50
CATEGORIES = ["Delay", "Breakdown", "Accident", "Service Change"]

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "reports", "hw05", "raw")


def percentile(values, p):
    """Nearest-rank percentile (with 50 samples, p99 = the slowest call)."""
    s = sorted(values)
    k = max(1, math.ceil(p / 100 * len(s)))
    return s[k - 1]


def sqlite_fixture(path="/tmp/s1346_fault_fixture.db"):
    from sqlalchemy import create_engine, text
    if os.path.exists(path):
        os.remove(path)
    e = create_engine(f"sqlite:///{path}")
    rng = random.Random(SID4)
    with e.begin() as c:
        c.execute(text("CREATE TABLE transit_lines(id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, mode TEXT)"))
        c.execute(text("CREATE TABLE incidents(id INTEGER PRIMARY KEY, incident_code TEXT UNIQUE, route_title TEXT,"
                       " category TEXT, passengers_affected INT, line_id INT, created_at TEXT, updated_at TEXT)"))
        for i in range(1, 21):
            c.execute(text("INSERT INTO transit_lines VALUES (:i, :c, :n, 'Bus')"),
                      {"i": i, "c": f"L-{i:03d}", "n": f"Route {i}"})
        for i in range(1, 501):
            c.execute(text("INSERT INTO incidents VALUES (:i, :code, :t, :cat, :p, :l, '2026-09-01', '2026-09-01')"),
                      {"i": i, "code": f"INC-{i:06d}", "t": f"Route {i % 20 + 1} - incident {i}",
                       "cat": rng.choice(CATEGORIES), "p": rng.randint(0, 80), "l": i % 20 + 1})
    return f"sqlite:///{path}"


def run_rate(base_repo, rate):
    injector = FaultInjectingRepository(base_repo, rate=rate, seed=VERIFY_SEED)
    repo = ResilientRepository(injector, INTERACTIVE)
    records = []
    for i in range(CALLS_PER_RATE):
        inputs = {"category": CATEGORIES[i % 4], "limit": 10}
        env = run_tool("search_incidents", inputs, repo=repo)
        r = repo.last_report
        records.append({
            "failure_rate": rate, "call_index": i + 1, "tool": "search_incidents",
            "inputs": json.dumps(inputs), "ok": env["ok"], "attempts": r.attempts,
            "attempt_outcomes": "|".join(r.attempt_outcomes),
            "injected_faults": r.attempt_outcomes.count("fault"),
            "latency_ms": round(r.latency_ms, 3), "error": env["error"] or "",
        })
    # Reproducibility proof: replay the same number of draws with a fresh RNG.
    replay_rng = random.Random(VERIFY_SEED)
    replay = [replay_rng.random() < rate for _ in injector.draws]
    seq = "".join("F" if d else "." for d in injector.draws)
    return records, {"draws": len(injector.draws), "replay_matches": replay == injector.draws,
                     "sequence_sha256": hashlib.sha256(seq.encode()).hexdigest()[:16],
                     "sequence_first_40": seq[:40]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", action="store_true", help="use an offline SQLite fixture")
    args = ap.parse_args()

    url = sqlite_fixture() if args.sqlite else None
    base = SqlRepository(url)
    backend = "sqlite-fixture" if args.sqlite else "mysql s1346_rel"
    p = INTERACTIVE
    print(f"Run by {getpass.getuser()} at {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"VERIFY_SEED={VERIFY_SEED}  backend={backend}  calls/rate={CALLS_PER_RATE}")
    print(f"Policy: max_attempts={p.max_attempts}, timeout/attempt={p.attempt_timeout_s}s, "
          f"backoff={p.base_delay_s}s x{p.multiplier} cap {p.max_delay_s}s\n")

    base.search_incidents(None, None, None, 1)   # warm-up connection (not measured)

    all_records, summary = [], []
    for rate in RATES:
        recs, repro = run_rate(base, rate)
        lat = [r["latency_ms"] for r in recs]
        ok = sum(r["ok"] for r in recs)
        row = {
            "failure_rate": f"{rate:.0%}", "calls": len(recs), "succeeded": ok,
            "success_rate": f"{ok / len(recs):.0%}",
            "mean_latency_ms": round(sum(lat) / len(lat), 1),
            "p50_latency_ms": round(percentile(lat, 50), 1),
            "p99_latency_ms": round(percentile(lat, 99), 1),
            "total_attempts": sum(r["attempts"] for r in recs),
            "injected_faults": sum(r["injected_faults"] for r in recs),
            "calls_needing_retry": sum(r["attempts"] > 1 for r in recs),
            **repro,
        }
        summary.append(row)
        all_records += recs
        print(f"rate {row['failure_rate']:>3}: success {row['success_rate']:>4}  "
              f"mean {row['mean_latency_ms']:>7.1f} ms  p99 {row['p99_latency_ms']:>7.1f} ms  "
              f"retried {row['calls_needing_retry']:>2}  faults {row['injected_faults']:>2}  "
              f"seq {row['sequence_sha256']}  replay_matches={row['replay_matches']}")

    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, "fault_injection_calls.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_records[0]))
        w.writeheader()
        w.writerows(all_records)
    json.dump(all_records, open(os.path.join(RAW, "fault_injection_calls.json"), "w"), indent=1)
    meta = {"generated_at": datetime.now().isoformat(timespec="seconds"), "run_by": getpass.getuser(),
            "verify_seed": VERIFY_SEED, "backend": backend, "policy": p.__dict__,
            "percentile_method": "nearest-rank", "rates": summary}
    json.dump(meta, open(os.path.join(RAW, "fault_injection_summary.json"), "w"), indent=2)

    print("\n| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) |")
    print("|---|---|---|---|")
    for r in summary:
        print(f"| {r['failure_rate']} | {r['success_rate']} | {r['mean_latency_ms']} | {r['p99_latency_ms']} |")
    print(f"\n{len(all_records)} call records saved to reports/hw05/raw/")


if __name__ == "__main__":
    sys.exit(main())
