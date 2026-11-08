"""HW9 shared configuration (s1346): Section 0 values, Redis key names, cache settings, paths.

Every HW9 script reads from here, so key names and thresholds have one source of truth.
All Redis keys start with PREFIX ("s1346").
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

# ---- Redis ----------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Part 1 - view counter for the primary entity (Incident)
VIEWS_KEY = PREFIX + ":views:incident:{id}"        # s1346:views:incident:42
SYNC_EVERY = int(os.getenv("HW09_SYNC_EVERY", "10"))  # persist to MySQL every N increments

# Part 2/3 - semantic response cache
SEMCACHE_PREFIX = f"{PREFIX}:semcache:"             # one Redis hash per cached query
SEMCACHE_INDEX = f"{PREFIX}:idx:semcache"           # RediSearch vector index over those hashes
VECTOR_BACKEND = os.getenv("HW09_VECTOR_BACKEND", "redisearch")   # "redisearch" | "scan" (offline tests only)
EMBED_BACKEND = os.getenv("HW09_EMBED_BACKEND", "st")              # "st" | "hash" (offline tests only)
EMBED_MODEL = os.getenv("HW09_EMBED_MODEL", "BAAI/bge-small-en-v1.5")  # same model as HW4 RAG / HW6 memory
EMBED_DIM = 384
DEFAULT_THRESHOLD = float(os.getenv("HW09_THRESHOLD", "0.85"))
THRESHOLDS = (0.75, 0.80, 0.85, 0.90, 0.95)
# Part 3.4 result: bge-small scores "INC-000230" vs "INC-000231" questions at 0.93-0.98, above most
# paraphrases, so a hit must also name exactly the same incident codes as the cached question.
ENTITY_GUARD = os.getenv("HW09_ENTITY_GUARD", "1") != "0"
STATIC_VERSION = "static-v1"     # data-version marker for answers that do not depend on a s1346_rel row

# Part 3.4 - cost model (dollars per event; justified in the report)
COST_MISS = float(os.getenv("HW09_COST_MISS", "0.02"))
COST_FALSE_HIT = float(os.getenv("HW09_COST_FALSE_HIT", "0.50"))

# HW8 agent pipeline behind the cache
AGENT_TIMEOUT_S = float(os.getenv("HW09_AGENT_TIMEOUT_S", "300"))
QA_API_PORT = PORT_BASE + 1                          # 8447 (8446 is the HW8 incident API)

# ---- Paths ----------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
HW09_DIR = REPO_ROOT / "code" / "hw09"
BACKEND_DIR = REPO_ROOT / "code" / "backend"
CODE_DIR = REPO_ROOT / "code"
CACHE_CASES = HW09_DIR / "cache_cases.yaml"
PART4_DATA = HW09_DIR / "part4" / "data"
REPORT_DIR = REPO_ROOT / "reports" / "hw09"
RAW_DIR = REPORT_DIR / "raw"
RUN_LOG = REPORT_DIR / "RUN_LOG.txt"


def ensure_dirs() -> None:
    """Create reports/hw09/raw if missing."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
