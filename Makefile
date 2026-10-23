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
