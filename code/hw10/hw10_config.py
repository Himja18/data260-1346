"""HW10 configuration (s1346): judge settings, paths, evaluator bounds."""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = REPO_ROOT / "code"
HW10_DIR = CODE_DIR / "hw10"
for p in (CODE_DIR, CODE_DIR / "hw09", CODE_DIR / "kafka_agents", REPO_ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import hw08_config as cfg8  # noqa: E402
import hw09_config as cfg9  # noqa: E402

SID4, PREFIX, PORT_BASE = cfg9.SID4, cfg9.PREFIX, cfg9.PORT_BASE
STUDENT_NAME = cfg9.STUDENT_NAME
DASHBOARD_PORT = PORT_BASE + 2                    # 8448 (8446 incident API, 8447 HW9 cached Q&A)

# ---- judge (Part 2/3) - documented settings --------------------------------------------
JUDGE_BACKEND = os.getenv("HW10_JUDGE_BACKEND", "ollama")          # ollama | fake (offline tests only)
JUDGE_MODEL = os.getenv("HW10_JUDGE_MODEL", "qwen2.5:3b")          # local, same Ollama as the agents
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
JUDGE_TEMPERATURE = float(os.getenv("HW10_JUDGE_TEMPERATURE", "0.3"))   # = the agents' temperature; no seed
JUDGE_NUM_PREDICT = int(os.getenv("HW10_JUDGE_NUM_PREDICT", "256"))
JUDGE_TIMEOUT_S = float(os.getenv("HW10_JUDGE_TIMEOUT_S", "120"))    # per metric call: HTTP + thread bound
SCORE_MIN, SCORE_MAX = 1, 5                                          # reported scale everywhere

# ---- evaluator service (Part 2) ----------------------------------------------------------
EVAL_GROUP = f"{PREFIX}_evaluators"
EVAL_TOPICS = [cfg8.TASKS_TOPIC, cfg8.DRAFTS_TOPIC, cfg8.FINAL_TOPIC, cfg8.DEAD_LETTER_TOPIC]
EVAL_WAIT_S = float(os.getenv("HW10_EVAL_WAIT_S", "240"))           # give up on an incomplete trace after this

# ---- paths ---------------------------------------------------------------------------------
REPORT_DIR = REPO_ROOT / "reports" / "hw10"
RAW_DIR = REPORT_DIR / "raw"
RUN_LOG = REPORT_DIR / "RUN_LOG.txt"
EVAL_RESULTS = REPORT_DIR / "eval_results.jsonl"      # one line per evaluated trace (Part 2)
EVAL_CASES = HW10_DIR / "eval_cases.json"             # Part 3.1 (frozen, committed before judging)
HUMAN_LABELS = HW10_DIR / "human_labels.csv"          # Part 3.1 (hand labels, committed before judging)
JUDGE_VALIDATION = REPORT_DIR / "judge_validation.json"
TRACE_EXAMPLES = REPORT_DIR / "trace_examples.json"
LATENCY_RESULTS = REPORT_DIR / "latency_experiment.json"
INTERPRETATION = REPORT_DIR / "interpretation.md"


def ensure_dirs() -> None:
    """reports/hw10/raw."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(component: str):  # noqa: ANN201
    """Name-stamped logger -> stdout + reports/hw10/RUN_LOG.txt (same format as HW8/HW9)."""
    import logging
    ensure_dirs()
    log = logging.getLogger(component)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter(f"%(asctime)s.%(msecs)03d | {STUDENT_NAME} | {PREFIX} | %(name)-12s | %(message)s",
                            "%Y-%m-%d %H:%M:%S")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(RUN_LOG, encoding="utf-8")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.propagate = False
    return log
