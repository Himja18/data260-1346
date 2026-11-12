PYTHON ?= python

.PHONY: verify-hw06 hw06-experiments hw06-consolidation hw06-agent-check hw06-metrics hw06-test

verify-hw06:            ## smoke test -> reports/hw06/verification.json
	$(PYTHON) verify_hw06.py

hw06-test:              ## offline test suite (no MongoDB, Ollama or network)
	$(PYTHON) code/test_hw06.py

hw06-experiments:       ## Part 3 sweep (N=4/12/30 + policy) and probes
	$(PYTHON) code/run_memory_experiment.py

hw06-consolidation:     ## Part 4.5 consolidation of the 55-line MEMORY.md
	$(PYTHON) code/run_consolidation_test.py

hw06-agent-check:       ## Part 4.4 generate a function with AGENT.md and check it
	$(PYTHON) code/agent_md_check.py --generate

hw06-metrics:           ## rebuild reports/hw06/METRICS.md from raw files
	$(PYTHON) code/make_metrics_hw06.py

# ---------------------------------------------------------------- HW7 ----
.PHONY: verify-hw07 hw07-test lint hw07-part2 hw07-reliability hw07-part3 hw07-fault-demo \
        hw07-bike-data hw07-pricing-check hw07-part4 hw07-part5 hw07-part6 hw07-metrics

verify-hw07:            ## smoke test (backend + MySQL + Ollama up) -> reports/hw07/verification.json
	$(PYTHON) verify_hw07.py

hw07-test:              ## offline HW7 suite (SQLite + scripted models; no server, MySQL or Ollama)
	$(PYTHON) code/test_hw07.py

lint:                   ## Ruff over the whole repo (same rules as the pre-commit hook)
	ruff check .

hw07-part2:             ## Part 2: tasks A/B/C + error recovery
	$(PYTHON) code/run_hw07_part2.py --demo --recovery

hw07-reliability:       ## Part 2 III: 21 attempts (7 per task)
	$(PYTHON) code/run_hw07_part2.py --reliability 21

hw07-fault-demo:        ## Part 3: guaranteed failed-then-retried Reflexion example
	$(PYTHON) code/run_hw07_part3.py --fault-demo

hw07-part3:             ## Part 3: original vs Reflexion, 3 runs per task
	$(PYTHON) code/run_hw07_part3.py --repeats 3

hw07-bike-data:         ## Part 4: download Bay Wheels trips + build the two scenario CSVs
	$(PYTHON) code/bikeshare/prepare_scenarios.py

hw07-pricing-check:     ## Part 4: fetch the pricing page and show the extracted prices
	$(PYTHON) code/run_hw07_part4.py --check-pricing

hw07-part4:             ## Part 4: both acceptance cases from the CLI (the UI does the same)
	$(PYTHON) code/run_hw07_part4.py --scenario both

hw07-part5:             ## Part 5: 3 attacks x 3 defense configurations
	$(PYTHON) code/run_hw07_part5.py

hw07-part5-replay:      ## Part 5: deterministic tool-boundary replay (no model)
	$(PYTHON) code/run_hw07_part5.py --replay

hw07-part6:             ## Part 6: integration test + 10-command safety-gate test
	$(PYTHON) code/run_hw07_part6.py

hw07-metrics:           ## rebuild reports/hw07/METRICS.md from raw files
	$(PYTHON) code/make_metrics_hw07.py

# ---------------------------------------------------------------- HW8 ----
KAFKA_TOPICS = docker exec s1346-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092

.PHONY: hw08-up hw08-down hw08-topics hw08-ps hw08-demo hw08-demo-api hw08-ask hw08-part3 \
        hw08-test hw08-metrics verify-hw08

hw08-up:                ## start Kafka + incident worker + FastAPI (port 8446)
	docker compose up -d --build

hw08-down:              ## stop the HW8 containers
	docker compose down

hw08-topics:            ## create the 7 s1346 topics with the Kafka CLI, then describe them
	$(KAFKA_TOPICS) --create --if-not-exists --topic s1346_incident_requests  --partitions 1 --replication-factor 1
	$(KAFKA_TOPICS) --create --if-not-exists --topic s1346_incident_responses --partitions 1 --replication-factor 1
	$(KAFKA_TOPICS) --create --if-not-exists --topic s1346_inbox       --partitions 1 --replication-factor 1
	$(KAFKA_TOPICS) --create --if-not-exists --topic s1346_tasks       --partitions 2 --replication-factor 1
	$(KAFKA_TOPICS) --create --if-not-exists --topic s1346_drafts      --partitions 1 --replication-factor 1
	$(KAFKA_TOPICS) --create --if-not-exists --topic s1346_final       --partitions 1 --replication-factor 1
	$(KAFKA_TOPICS) --create --if-not-exists --topic s1346_dead_letter --partitions 1 --replication-factor 1
	$(KAFKA_TOPICS) --list
	$(KAFKA_TOPICS) --describe --topic s1346_tasks

hw08-ps:                ## containers + the worker/API startup lines
	docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
	docker logs s1346-incident-worker 2>&1 | grep -m1 "Consumer is ready"
	docker logs s1346-incident-api 2>&1 | grep -m1 "FastAPI server started"

hw08-demo:              ## Part 1: CREATE_INCIDENT -> GET_INCIDENT over Kafka (homework_demo.py)
	$(PYTHON) code/kafka_service/homework_demo.py

hw08-demo-api:          ## Part 1: the same flow through the FastAPI wrapper
	$(PYTHON) code/kafka_service/homework_demo.py --via-api

hw08-ask:               ## Part 2: send one question to s1346_inbox and wait for s1346_final
	$(PYTHON) code/kafka_agents/send_question.py

hw08-part3:             ## Part 3: duplicate / consumer death / poison / ordering, before + after
	$(PYTHON) code/run_hw08_part3.py --scenario all

hw08-reset-writers:     ## after Part 3: move group s1346_writers past the test messages (writer must be stopped)
	docker exec s1346-kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
		--group s1346_writers --topic s1346_tasks --reset-offsets --to-latest --execute

hw08-test:              ## offline HW8 tests (no Kafka, no Ollama)
	$(PYTHON) code/test_hw08.py

hw08-metrics:           ## rebuild reports/hw08/METRICS.md from raw files
	$(PYTHON) code/make_metrics_hw08.py

verify-hw08:            ## smoke test (stack + agents up) -> reports/hw08/verification.json
	$(PYTHON) verify_hw08.py

# ---------------------------------------------------------------- HW9 ----
.PHONY: hw09-redis hw09-migrate hw09-part1 hw09-part2 hw09-api hw09-sweep hw09-stale hw09-inspect \
        hw09-part4 hw09-part4-controlled hw09-part4-train hw09-part4-validate hw09-part4-test

hw09-redis:             ## start Redis Stack (RediSearch) as s1346-redis on 6379
	docker compose up -d redis
	docker exec s1346-redis redis-cli MODULE LIST

hw09-migrate:           ## add incidents.view_count to s1346_rel (run once)
	mysql -u root -p < code/backend/migrations/005_hw9_view_count.sql

hw09-part1:             ## Part 1: Redis view counter, MySQL sync every 10
	$(PYTHON) code/hw09/run_hw09_part1.py

hw09-part2:             ## Part 2: semantic cache in front of the HW8 pipeline, 12 queries
	$(PYTHON) code/hw09/run_hw09_part2.py

hw09-api:               ## Part 2: cached Q&A endpoint on port 8447
	uvicorn qa_api:app --app-dir code/hw09 --port 8447

hw09-sweep:             ## Part 3.2-3.4: 40 cases x 5 thresholds, false hit, cost
	$(PYTHON) code/hw09/run_hw09_part3_sweep.py

hw09-stale:             ## Part 3.5: stale hit, then version-marker invalidation
	$(PYTHON) code/hw09/run_hw09_part3_stale.py

hw09-inspect:           ## every s1346:* key + the vector index
	$(PYTHON) code/hw09/run_hw09_inspect.py

hw09-part4-controlled:  ## Part 4.1 controlled revision
	$(PYTHON) code/hw09/part4/run_hw09_part4.py controlled
hw09-part4-train:       ## Part 4.2 training + lesson reuse
	$(PYTHON) code/hw09/part4/run_hw09_part4.py train
hw09-part4-validate:    ## Part 4.3 validation gate
	$(PYTHON) code/hw09/part4/run_hw09_part4.py validate
hw09-part4-test:        ## Part 4.4 four variants on test_data
	$(PYTHON) code/hw09/part4/run_hw09_part4.py test
hw09-part4:             ## Part 4: all four steps
	$(PYTHON) code/hw09/part4/run_hw09_part4.py all

# ---------------------------------------------------------------- HW10 ----
.PHONY: hw10-install hw10-evaluator hw10-cases hw10-label hw10-judge hw10-replay hw10-traces hw10-latency hw10-dashboard

hw10-install:           ## DeepEval (GEval), Streamlit, SciPy
	$(PYTHON) -m pip install "deepeval>=4" "streamlit>=1.50" scipy requests

hw10-evaluator:         ## Part 2: evaluator service (joins plan/draft/final by correlation_id)
	$(PYTHON) code/hw10/evaluator.py

hw10-cases:             ## Part 3.1: freeze 20 Writer drafts -> eval_cases.json + empty human_labels.csv
	$(PYTHON) code/hw10/make_eval_cases.py

hw10-label:             ## Part 3.1: type YOUR 1-5 label for each draft
	$(PYTHON) code/hw10/label_drafts.py

hw10-judge:             ## Part 3.2-3.3: judge vs human labels, 3 repeat runs
	$(PYTHON) code/hw10/run_judge_validation.py

hw10-replay:            ## Part 2: evaluate one trace from the topics: make hw10-replay TRACE=<id>
	$(PYTHON) code/hw10/evaluator.py --trace-id $(TRACE)

hw10-traces:            ## Part 4.2: cache-hit, cache-miss and failed traces
	$(PYTHON) code/hw10/run_hw10_traces.py

hw10-latency:           ## Part 4.3: 50 confirmed cache misses, stage p50/p95
	$(PYTHON) code/hw10/run_hw10_latency.py

hw10-dashboard:         ## Part 1: Streamlit dashboard on port 8448
	streamlit run code/hw10/dashboard.py --server.port 8448
