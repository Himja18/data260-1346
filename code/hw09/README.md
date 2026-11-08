# HW9 - caching in front of the HW8 system (s1346 | Himja Patel)

All Redis keys start with `s1346:` and every log line carries `Himja Patel | s1346`.
Logs are appended to `reports/hw09/RUN_LOG.txt`; raw results go to `reports/hw09/raw/`.

| Part | Command | What it shows |
|---|---|---|
| setup | `make hw09-redis`, `make hw09-migrate` | Redis Stack (RediSearch) on 6379; `incidents.view_count` column |
| 1 | `make hw09-part1` | `s1346:views:incident:42` INCR x25, MySQL sync at 10 and 20 |
| 2 | `make hw09-part2` | 12 queries through the semantic cache -> HW8 pipeline; hit rate, cached vs non-cached latency |
| 2 | `make hw09-api` | the same cache as `POST /ask` on port 8447 |
| 3.1 | `code/hw09/cache_cases.yaml` | 40 labelled cases (commit before the sweep) |
| 3.2-3.4 | `make hw09-sweep` | thresholds 0.75-0.95: hit rate, false-hit rate, mean latency, cost; one false hit in full |
| 3.5 | `make hw09-stale` | stale hit, then data-version invalidation |
| 4 | `make hw09-part4-controlled / -train / -validate / -test` | Answering + Evaluator agents, lessons, validation, four variants |
| any | `make hw09-inspect` | every `s1346:*` key and the vector index |

Files
- `incident_cache.py` - `IncidentCache.increment_incident_views()` (Part 1), s1346_rel facts + data-version marker (3.5)
- `semantic_cache.py` - `SemanticCache.ask()`: embed (bge-small, 384-d) -> RediSearch KNN 1 (COSINE) -> hit / version check / miss
- `pipeline_agent.py` - the cache-miss path: question -> `s1346_inbox` ... `s1346_final` (HW8 Planner/Writer/Reviewer)
- `part4/answering_agent.py`, `part4/evaluator_agent.py`, `part4/lessons.py`, `part4/run_hw09_part4.py`
- `part4/data/` - `reference_data.json` (ground truth), `dispatch_snapshot.json` (what the Answering Agent reads),
  `training_data.json`, `validation_data.json`, `test_data.json` (questions only), `lessons.json` (written by the system)

Needs: MySQL `s1346_rel` (MYSQL_PASSWORD as in HW7), Redis Stack, and for Parts 2-3 the HW8 stack
(`make hw08-up`, planner.py, writer.py, reviewer.py) with Ollama `qwen2.5:3b`. Part 4 only needs Ollama.
