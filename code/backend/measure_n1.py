"""HW4 Part 3.4-3.7: measure naive vs fixed list endpoints.

3 page sizes (10, 50, 200) x 2 versions (naive, fixed) x 30 requests = 180 measured
requests. For each request we record the SQL statement count reported by the
endpoint and the client-side latency. A few warm-up requests per combination run
first and are NOT recorded.

Needs the backend running on PORT_BASE 8446 and the seeded data.
    python measure_n1.py
Writes (repo root)/reports/hw04/raw/n1_raw.csv, n1_raw.json, n1_summary.json
and appends timestamped lines to reports/hw04/RUN_LOG.txt.
"""
import argparse
import csv
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path

import requests

PORT_BASE = 8446
BASE = f"http://127.0.0.1:{PORT_BASE}"
PAGE_SIZES = (10, 50, 200)
VERSIONS = ("naive", "fixed")

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "reports" / "hw04" / "raw"
RUN_LOG = REPO_ROOT / "reports" / "hw04" / "RUN_LOG.txt"


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(RUN_LOG, "a") as f:
        f.write(line + "\n")


def pct(values, p):
    """p-th percentile, linear interpolation (statistics.quantiles, inclusive)."""
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--email", default=os.getenv("HW4_EMAIL", "dispatcher1346@transit.test"))
    ap.add_argument("--password", default=os.getenv("HW4_PASSWORD", "TransitLine22!"))
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": args.email, "password": args.password})
    r.raise_for_status()
    log(f"=== N+1 measurement start: {BASE}, logged in as {args.email}, "
        f"{args.requests} requests x {len(PAGE_SIZES)} sizes x {len(VERSIONS)} versions")

    rows, seq = [], 0
    for size in PAGE_SIZES:
        for version in VERSIONS:                      # warm-up (not recorded)
            for _ in range(args.warmup):
                s.get(f"{BASE}/api/incidents/{version}", params={"limit": size}).raise_for_status()
        for i in range(1, args.requests + 1):
            for version in VERSIONS:                  # alternate so both see the same conditions
                seq += 1
                t0 = time.perf_counter()
                resp = s.get(f"{BASE}/api/incidents/{version}", params={"limit": size})
                latency_ms = (time.perf_counter() - t0) * 1000
                resp.raise_for_status()
                body = resp.json()
                if body["returned"] != size:
                    raise SystemExit(f"expected {size} rows, got {body['returned']} - is the data seeded?")
                rows.append({
                    "seq": seq,
                    "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                    "page_size": size,
                    "version": version,
                    "request_no": i,
                    "status": resp.status_code,
                    "rows_returned": body["returned"],
                    "sql_statements": body["sql_statements"],
                    "latency_ms": round(latency_ms, 3),
                    "server_ms": body["server_ms"],
                })
        log(f"page_size={size}: {args.requests} naive + {args.requests} fixed requests done")

    # Raw data: all 180 requests
    with open(RAW_DIR / "n1_raw.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(RAW_DIR / "n1_raw.json", "w") as f:
        json.dump(rows, f, indent=2)

    # Summary per (page size, version)
    summary = {"n_requests_total": len(rows), "per_combination": [], "speedup": []}
    for size in PAGE_SIZES:
        stats = {}
        for version in VERSIONS:
            sub = [r for r in rows if r["page_size"] == size and r["version"] == version]
            lat = [r["latency_ms"] for r in sub]
            sqls = sorted({r["sql_statements"] for r in sub})
            stats[version] = {
                "page_size": size, "version": version, "n": len(sub),
                "sql_stmts_per_req": sqls[0] if len(sqls) == 1 else sqls,
                "p50_ms": round(pct(lat, 50), 2), "p95_ms": round(pct(lat, 95), 2),
                "p99_ms": round(pct(lat, 99), 2),
                "server_p50_ms": round(statistics.median(r["server_ms"] for r in sub), 2),
            }
            summary["per_combination"].append(stats[version])
        summary["speedup"].append({
            "page_size": size,
            "p50_speedup_x": round(stats["naive"]["p50_ms"] / stats["fixed"]["p50_ms"], 2),
            "p95_speedup_x": round(stats["naive"]["p95_ms"] / stats["fixed"]["p95_ms"], 2),
            "p50_saved_ms": round(stats["naive"]["p50_ms"] - stats["fixed"]["p50_ms"], 2),
        })
    with open(RAW_DIR / "n1_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Results table (paste into METRICS.md)
    table = ["| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |",
             "|---|---|---|---|---|---|"]
    for c in summary["per_combination"]:
        table.append(f"| {c['page_size']} | {c['version']} | {c['sql_stmts_per_req']} | "
                     f"{c['p50_ms']} | {c['p95_ms']} | {c['p99_ms']} |")
    table += ["", "| Page size | p50 speed-up | p95 speed-up | p50 time saved (ms) |",
              "|---|---|---|---|"]
    for sp in summary["speedup"]:
        table.append(f"| {sp['page_size']} | {sp['p50_speedup_x']}x | {sp['p95_speedup_x']}x | "
                     f"{sp['p50_saved_ms']} |")
    for line in table:
        log(line)
    log(f"Saved {len(rows)} raw rows to {RAW_DIR / 'n1_raw.csv'} and n1_raw.json; "
        f"summary in n1_summary.json")


if __name__ == "__main__":
    main()
