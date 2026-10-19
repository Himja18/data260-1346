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
