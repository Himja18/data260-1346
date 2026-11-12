# HW10 - evaluation, judge validation, tracing, Streamlit dashboard (s1346 | Himja Patel)

| Part | Command | Output |
|---|---|---|
| setup | `make hw10-install`, restart planner/writer/reviewer, start `make hw10-evaluator` | agents now write spans |
| 2 | `make hw10-evaluator` (service) + any question, or `make hw10-replay TRACE=<id>` | `reports/hw10/eval_results.jsonl` |
| 3.1 | `make hw10-cases`, then `make hw10-label` (YOU type 1-5), then commit both files | `code/hw10/eval_cases.json`, `code/hw10/human_labels.csv` |
| 3.2-3.3 | `make hw10-judge` | `reports/hw10/judge_validation.json`, `raw/judge_scores.csv` |
| 4.2 | `make hw10-traces` | `reports/hw10/trace_examples.json` |
| 4.3 | `make hw10-latency` | `reports/hw10/latency_experiment.json`, `raw/latency_per_trace.csv` |
| 1 | `make hw10-dashboard` -> http://localhost:8448 | Summary / Evaluation / Trace lookup |

Tracing: `code/tracing.py` writes one JSON span per stage to `reports/hw10/spans.jsonl`. The trace_id is generated
once at the cache ingress and is the HW8 correlation_id on the Kafka path (no second id). Stages: request,
cache_lookup (hit|miss), queue_inbox, planner, queue_tasks, writer, queue_drafts, reviewer, queue_final, evaluation.

Judge: DeepEval GEval with a local Ollama model (qwen2.5:3b), temperature 0.3, no seed, fixed evaluation steps,
120 s bound per call; scores reported on 1-5 = round(1 + 4 * GEval score).
