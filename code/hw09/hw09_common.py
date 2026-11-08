"""HW9 helpers: name-stamped logging, Redis client, s1346_rel engine, embedder, JSON helpers."""
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime
from functools import lru_cache
from typing import Any

import numpy as np

import hw09_config as cfg

_LOG_FORMAT = f"%(asctime)s.%(msecs)03d | {cfg.STUDENT_NAME} | {cfg.PREFIX} | %(name)-12s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(component: str) -> logging.Logger:
    """Logger that prints to stdout and appends to reports/hw09/RUN_LOG.txt (name on every line)."""
    cfg.ensure_dirs()
    logger = logging.getLogger(component)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)
    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(fmt)
    logger.addHandler(out)
    if os.getenv("HW09_RUN_LOG", "1") != "0":
        fh = logging.FileHandler(cfg.RUN_LOG, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    logger.propagate = False
    return logger


def banner(log: logging.Logger, title: str) -> None:
    """Header line that identifies the run (name, SID4, model, Redis)."""
    log.info("HW9 %s | %s | %s | model=%s | redis=%s", title, cfg.STUDENT_NAME, cfg.PREFIX,
             cfg.MODEL_NAME, cfg.REDIS_URL)


def now_iso() -> str:
    """Local timestamp with offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_redis():  # noqa: ANN201
    """Binary-safe Redis client (embeddings are stored as raw float32 bytes)."""
    import redis
    return redis.Redis.from_url(cfg.REDIS_URL, decode_responses=False)


def get_engine():  # noqa: ANN201
    """SQLAlchemy engine for s1346_rel (MySQL by default; DATABASE_URL overrides, e.g. SQLite in tests)."""
    sys.path.insert(0, str(cfg.BACKEND_DIR))
    from database import engine  # HW4 module: MYSQL_* env vars, same as HW4-HW7
    return engine


def write_json(name: str, obj: Any) -> str:
    """Write reports/hw09/raw/<name> and return the repo-relative path."""
    cfg.ensure_dirs()
    path = cfg.RAW_DIR / name
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return str(path.relative_to(cfg.REPO_ROOT))


def short(text: Any, limit: int = 160) -> str:
    """One-line preview."""
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 3] + "..."


INCIDENT_CODE = re.compile(r"\bINC-\d{6}\b", re.IGNORECASE)


def incident_codes(text: str) -> list[str]:
    """Incident codes mentioned in a question, upper-cased, in order, no duplicates."""
    seen: list[str] = []
    for m in INCIDENT_CODE.findall(text or ""):
        code = m.upper()
        if code not in seen:
            seen.append(code)
    return seen


# ---- embeddings ------------------------------------------------------------------------
class SentenceTransformerEmbedder:
    """BAAI/bge-small-en-v1.5 (384-d), L2-normalised, so cosine similarity = dot product."""

    def __init__(self, model_name: str = cfg.EMBED_MODEL) -> None:
        from sentence_transformers import SentenceTransformer
        self.name = model_name
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> np.ndarray:
        """One query -> float32 unit vector."""
        return np.asarray(self.model.encode([text], normalize_embeddings=True)[0], dtype=np.float32)


class HashEmbedder:
    """Offline-test stand-in: hashed bag of words (no model download)."""

    def __init__(self, dim: int = cfg.EMBED_DIM) -> None:
        self.name = f"hash-bow-{dim}"
        self.dim = dim

    def embed(self, text: str) -> np.ndarray:
        """Deterministic unit vector."""
        v = np.zeros(self.dim, dtype=np.float32)
        for word in re.findall(r"[a-z0-9-]+", text.lower()):
            d = hashlib.md5(word.encode()).digest()
            v[d[0] % self.dim] += 1.0 if d[1] % 2 else -1.0
        n = np.linalg.norm(v)
        return v / n if n else v


@lru_cache(maxsize=1)
def get_embedder():  # noqa: ANN201
    """The embedder selected by HW09_EMBED_BACKEND (one instance per process)."""
    return HashEmbedder() if cfg.EMBED_BACKEND == "hash" else SentenceTransformerEmbedder()
