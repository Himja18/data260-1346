"""HW8 shared configuration (s1346): Section 0 values, Kafka topic names and limits.

Every HW8 module (worker, client, FastAPI wrapper, the three agents, the Part 3 runner
and verify_hw08.py) reads topic names and limits from here, so there is one source of truth.
"""
import os
from pathlib import Path

# ---- Section 0: personal configuration (fixed for the semester) ----------------------
SID4 = 1346
PORT_BASE = 8000 + SID4 % 900            # 8446
PREFIX = f"s{SID4}"                       # s1346
SEED = SID4                               # 1346
VERIFY_SEED = 260000 + SID4               # 261346
DOMAIN_ID = SID4 % 8                      # 2 -> Municipal Transit Incidents
STUDENT_NAME = os.getenv("STUDENT_NAME", "Himja Patel")
HARDWARE = os.getenv("HW_DESCRIPTION", 'MacBook Pro 13" (Apple M2, 8 GB RAM), macOS')
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
MODEL_DESCRIPTION = f"{MODEL_NAME} via Ollama"

# ---- Kafka ----------------------------------------------------------------------------
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

# Part 1 - request/response service for the primary entity (Incident).
ENTITY = "incident"
REQUEST_TOPIC = f"{PREFIX}_{ENTITY}_requests"      # s1346_incident_requests
RESPONSE_TOPIC = f"{PREFIX}_{ENTITY}_responses"    # s1346_incident_responses
WORKER_GROUP = f"{PREFIX}_incident_worker"

# Part 2 - three-agent pipeline.
INBOX_TOPIC = f"{PREFIX}_inbox"
TASKS_TOPIC = f"{PREFIX}_tasks"            # 2 partitions (Part 3 IV ordering test)
DRAFTS_TOPIC = f"{PREFIX}_drafts"
FINAL_TOPIC = f"{PREFIX}_final"
PLANNER_GROUP = f"{PREFIX}_planners"
WRITER_GROUP = f"{PREFIX}_writers"
REVIEWER_GROUP = f"{PREFIX}_reviewers"

# Part 3 - poison messages.
DEAD_LETTER_TOPIC = f"{PREFIX}_dead_letter"
MAX_ATTEMPTS = int(os.getenv("HW08_MAX_ATTEMPTS", "3"))       # bounded retries per message
RETRY_BACKOFF_S = (0.5, 1.0, 2.0)                             # sleep before attempt 2, 3, ...

# topic -> partitions (replication factor is 1 on the single-broker dev cluster)
TOPICS: dict[str, int] = {
    REQUEST_TOPIC: 1,
    RESPONSE_TOPIC: 1,
    INBOX_TOPIC: 1,
    TASKS_TOPIC: 2,
    DRAFTS_TOPIC: 1,
    FINAL_TOPIC: 1,
    DEAD_LETTER_TOPIC: 1,
}

# ---- Domain: Incident fields (CREATE_INCIDENT data) -------------------------------------
CATEGORIES = ("Delay", "Breakdown", "Accident", "Service Change")

# ---- Paths ----------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "reports" / "hw08"
RAW_DIR = REPORT_DIR / "raw"
RUN_LOG = REPORT_DIR / "RUN_LOG.txt"
TRACE_FILE = RAW_DIR / "message_trace.jsonl"     # structured send/receive/reply events, all processes
STATE_DIR = REPO_ROOT / "data" / "hw08"           # idempotency stores (git-ignored)


def ensure_dirs() -> None:
    """Create reports/hw08/raw and data/hw08 if missing."""
    for d in (REPORT_DIR, RAW_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
