# HW5 METRICS - s1346 | Municipal Transit Incidents (DOMAIN_ID = 2)

SID4 1346 · PORT_BASE 8446 · PREFIX s1346 · SEED 1346 · VERIFY_SEED 261346 · model qwen2.5:3b (Ollama, temperature 0, seed 1346)

## Part 3.2 - Retry policy demo (`code/mcp/demo_retry.py`)
Policy: max 3 attempts, 2.0 s timeout per attempt, backoff 0.1 s × 2 (cap 1.0 s). Raw: `raw/retry_demo.json`

| Case | Attempt outcomes | Attempts | Total latency | Result |
|---|---|---|---|---|
| A - success on first attempt | ok | 1/3 | 0 ms | `ok: true` |
| B - failure, then success after retry | timeout, ok | 2/3 | 2111 ms | `ok: true` |
| C - fails every attempt | fault, fault, fault | 3/3 | 311 ms | `ok: false`, clean error, no crash |

## Part 3.3 - Seeded fault injection (`code/mcp/run_fault_injection.py`)
Backend: MySQL `s1346_rel`. 50 `search_incidents` calls per rate, 150 total.
Raw: `raw/fault_injection_calls.csv` / `.json` (150 records), `raw/fault_injection_summary.json`.
Percentiles: nearest-rank (with 50 samples, p99 is the slowest call).

| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) |
|---|---|---|---|
| 0% | 100% | 1.1 | 9.2 |
| 20% | 96% | 33.8 | 311.7 |
| 50% | 88% | 87.2 | 314.3 |

| Rate | Calls retried | Injected faults | Fault-sequence SHA-256 (prefix) | Replay matches |
|---|---|---|---|---|
| 0% | 0 | 0 | dd89800342a2adde | True |
| 20% | 9 | 14 | 63ffc9b4ddea006b | True |
| 50% | 19 | 36 | ca089130d46f7fcd | True |

Reproducibility: repeated runs with VERIFY_SEED 261346 produced identical sequence hashes (also identical on an
offline SQLite fixture), and replaying the draws with a fresh `random.Random(261346)` matched for every rate.

## Part 4 / 5.III - Offline test suite (`code/mcp/test_tools.py`)
FakeRepo + MockModel via dependency injection; no DB, network, LLM or API key.

| Group | Tests | Result |
|---|---|---|
| Tool contracts (valid + Part 3 invalid inputs, not-found, unknown tool, bad JSON, retries exhausted) | 10 | 10 PASS |
| Part 5: safety rule blocks, agent stops at max_steps (MockModel) | 2 | 2 PASS |
| **Total** | **12** | **12/12** |

## Part 5.I - Safety rule (`code/mcp/demo_safety.py`)
Rule: a `search_incidents` call with no category / line_code / text filter may return at most 10 rows.

| Call | Result |
|---|---|
| `{"category": "Delay", "limit": 50}` | allowed, `ok: true` |
| `{"limit": 50}` | blocked, `{ok: false, data: null, error: "blocked by safety rule: ..."}`, never reached storage |

## Part 5.IV - Agent scenarios (`code/mcp/run_scenarios.py`, local Ollama qwen2.5:3b)
Log: `raw/agent_runs.jsonl`, summary: `raw/agent_scenarios.json`

| Scenario | Steps (max) | Tool calls | Stop reason | run_id |
|---|---|---|---|---|
| S1 aggregate - category counts for L-005 | 2 (5) | 1 | completed | 40c802ac |
| S2 detail - INC-005005 | 2 (5) | 1 | completed | 7c5abf22 |
| S3 search - 3 most recent Breakdowns | 2 (5) | 1 | completed | d90b350d |
| S4 safety - export 50 incidents of any kind | 1 (5) | 1 | safety_block | c51c0f96 |
| S5 ceiling - stats + details for 4 lines | 3 (3) | 12 | max_steps | bb352ae8 |

Observations: S5 made 12 tool calls in 3 steps because the model requested 4 calls per turn - `max_steps`
limits model turns, not tool calls. In S5 step 2 the model sent an extra `line_code` field to `get_incident`;
validation rejected it and the model corrected itself in step 3. A hosted-model comparison was not run (optional).
