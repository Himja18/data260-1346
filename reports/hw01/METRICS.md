# METRICS.md — DATA-260 HW1

## Part 3: Non-Determinism Experiment Results

Fixed input: `reports/hw01/cases/nondeterminism_input.json`
("Line 22 - Bus stalled on Main St")
Model: qwen2.5:3b (local, via Ollama)
20 runs per temperature, 40 runs total.

| Metric | Temp 0.7 | Temp 0.0 |
|---|---|---|
| Distinct tag sets | 15 | 1 |
| Tags in all 20 runs | (none) | Bus Delays, Intersection, Mechanical Issue |
| Tags in exactly 1 run | Bus, BusBreakdown, DelayedService, Intersection Troubles, MainStIntersection, Route22, Stalled, Stuck, Traffic Congestion | (none) |

| Metric | Temp 0.7 | Temp 0.0 |
|---|---|---|
| Latency p50 (ms) | 12070.6 | 11999.4 |
| Latency p95 (ms) | 14927.9 | 13257.0 |
| Latency p99 (ms) | 16754.7 | 13921.5 |

Raw per-run data: `reports/hw01/raw/nondeterminism_raw.json` and
`reports/hw01/raw/nondeterminism_raw.csv`.

### Analysis

At temperature 0.7, two users submitting the identical incident report
would very likely see different tags — 15 of 20 runs produced a unique
tag combination, and no single tag appeared in all 20 runs. At
temperature 0.0, both users would see the exact same 3 tags
(`Bus Delays`, `Intersection`, `Mechanical Issue`) and summary every
single time — 20/20 runs converged on one tag set.

Latency was comparable across temperatures (~12s median for both), so
determinism at temp 0.0 came at essentially no latency cost in this test.

**Where run-to-run variation is acceptable:** a low-stakes internal
dashboard suggesting alternative tag phrasings for a human editor to pick
from — creative variety can be a feature, not a bug.

**Where run-to-run variation is NOT acceptable:** automated regulatory or
compliance categorization of transit incidents, where consistent,
auditable labels are required for reporting to a transit authority or
for statistical tracking over time. Here, temperature 0.0 should be used
so that identical incidents are always categorized identically.