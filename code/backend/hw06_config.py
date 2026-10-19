"""HW6 server configuration - personal values and memory settings (s1346).

Every value can be overridden with an environment variable of the same name,
so experiments (Part 3) can change SHORT_TERM_N etc. without editing code.
"""
import os
from pathlib import Path

# ---- Section 0: personal configuration (fixed for the semester) -------------
SID4 = 1346
PORT_BASE = 8000 + SID4 % 900            # 8446
PREFIX = f"s{SID4}"                       # s1346
SEED = SID4                               # 1346
VERIFY_SEED = 260000 + SID4               # 261346
DOMAIN_ID = SID4 % 8                      # 2 -> Municipal Transit Incidents

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports" / "hw06"
RAW_DIR = REPORTS_DIR / "raw"


def _int(name: str, default: int) -> int:
    """Read an integer setting from the environment."""
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    """Read a float setting from the environment."""
    return float(os.getenv(name, str(default)))


# ---- MongoDB (Part 1 + Part 2 share one database) ----------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = f"{PREFIX}_doc"                # s1346_doc
INCIDENT_DOCS = "incident_reports"        # Part 1 collection (never touched by memory code)
MESSAGES = "messages"
SUMMARIES = "summaries"
EPISODES = "episodes"

# ---- Memory settings (Part 2 / Part 3) ---------------------------------------
SHORT_TERM_N = _int("SHORT_TERM_N", 12)                       # sliding window (messages)
SUMMARIZE_EVERY_USER_MSGS = _int("SUMMARIZE_EVERY_USER_MSGS", 4)
LIFETIME_EVERY_SESSION_SUMMARIES = _int("LIFETIME_EVERY_SESSION_SUMMARIES", 2)
EPISODIC_TOP_K = _int("EPISODIC_TOP_K", 3)
EPISODIC_MIN_SCORE = _float("EPISODIC_MIN_SCORE", 0.35)       # cosine floor for retrieval
EPISODE_DEDUP_SCORE = _float("EPISODE_DEDUP_SCORE", 0.95)     # skip near-identical facts
MAX_FACTS_PER_MESSAGE = 3
MEMORY_POLICY = os.getenv("MEMORY_POLICY", "none")            # "none" | "compress_assistant"
COMPRESS_KEEP_RECENT = _int("COMPRESS_KEEP_RECENT", 4)        # messages kept verbatim
COMPRESS_MAX_CHARS = _int("COMPRESS_MAX_CHARS", 120)          # older assistant turns cut to this

# ---- Model settings ------------------------------------------------------------
CHAT_TEMPERATURE = _float("CHAT_TEMPERATURE", 0.0)            # 0 + fixed seed for repeatable runs
REPLY_MAX_TOKENS = _int("REPLY_MAX_TOKENS", 256)
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "st")              # "st" | "ollama" | "hash" (offline tests)
EMBED_MODEL_ST = os.getenv("EMBED_MODEL_ST", "BAAI/bge-small-en-v1.5")   # same model as HW4 RAG
EMBED_MODEL_OLLAMA = os.getenv("EMBED_MODEL_OLLAMA", "nomic-embed-text")
TOKENIZER_NAME = os.getenv("TOKENIZER_NAME", "Qwen/Qwen2.5-3B-Instruct")

USAGE_LOG = Path(os.getenv("MEMORY_USAGE_LOG", str(RAW_DIR / "chat_usage.jsonl")))
