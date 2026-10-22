"""HW6 Part 2/3: POST /api/chat, GET /api/memory/{user_id}, GET /api/aggregate/{user_id}.

Per /api/chat request (server steps from the brief):
  1. save the user message                    6. call the model (HW1 ModelClient, Ollama)
  2. load the short-term window (last N)      7. save the assistant reply
  3. load session + lifetime summaries        8. extract <=3 episodic facts, embed, store
  4. retrieve top-k episodes (cosine)         9. every M user messages: session summary,
  5. compose the prompt                          occasionally condense into the lifetime summary
Every request also appends one usage row (tokens per component, latency) to
reports/hw06/raw/chat_usage.jsonl (Part 3).
"""
import json
import logging
import sys
import time
import uuid
from functools import lru_cache
from typing import Literal, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from pymongo.database import Database

import memory_logic as ml
import token_counter
from embeddings import get_embedder
from hw06_config import (
    CHAT_TEMPERATURE,
    EPISODIC_MIN_SCORE,
    EPISODIC_TOP_K,
    LIFETIME_EVERY_SESSION_SUMMARIES,
    MEMORY_POLICY,
    REPLY_MAX_TOKENS,
    REPO_ROOT,
    SEED,
    SHORT_TERM_N,
    SUMMARIZE_EVERY_USER_MSGS,
    USAGE_LOG,
)
from memory_store import MemoryStore, utc_now
from mongo_db import get_mongo_db

sys.path.insert(0, str(REPO_ROOT / "src"))
from model_client import ModelClient  # noqa: E402  (HW1 adapter)

log = logging.getLogger("s1346.chat")
router = APIRouter(tags=["HW6 Part 2 - memory chat"])

ID_PATTERN = r"^[A-Za-z0-9_.:-]+$"


class ChatRequest(BaseModel):
    """Body of POST /api/chat. short_term_n / memory_policy are optional experiment overrides."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1, max_length=64, pattern=ID_PATTERN)
    session_id: Optional[str] = Field(None, min_length=1, max_length=64, pattern=ID_PATTERN)
    message: str = Field(..., min_length=1, max_length=4000)
    short_term_n: Optional[int] = Field(None, ge=0, le=100)
    memory_policy: Optional[Literal["none", "compress_assistant"]] = None


@lru_cache(maxsize=1)
def get_model_client() -> ModelClient:
    """One shared model adapter (temperature 0 + seed 1346 so runs are repeatable)."""
    return ModelClient(temperature=CHAT_TEMPERATURE, seed=SEED, num_predict=REPLY_MAX_TOKENS)


def get_store(db: Database = Depends(get_mongo_db)) -> MemoryStore:
    """FastAPI dependency: memory repository over s1346_doc."""
    return MemoryStore(db)


def _iso(value):
    """datetime -> ISO string (other values unchanged)."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _write_usage(row: dict) -> None:
    """Append one usage row to the JSONL log (Part 3 raw data)."""
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE_LOG, "a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except OSError as exc:
        log.warning("could not write usage log: %s", exc)


def handle_chat(req: ChatRequest, store: MemoryStore, client, embedder) -> dict:
    """Run one memory-augmented chat turn (all 9 server steps). Returns the response body."""
    started = time.perf_counter()
    n = SHORT_TERM_N if req.short_term_n is None else req.short_term_n
    policy = req.memory_policy or MEMORY_POLICY
    session_id = req.session_id or f"sess-{uuid.uuid4().hex[:12]}"
    aux_in = aux_out = 0

    # 1. save the user message
    user_doc = store.save_message(req.user_id, session_id, "user", req.message)

    # 2. short-term window (excluding the message just saved)
    raw_window = store.session_window(req.user_id, session_id, n, exclude_id=user_doc["_id"])
    window = ml.apply_window_policy(raw_window, policy)

    # 3. long-term summaries
    session_summary = store.latest_summary(req.user_id, "session", session_id)
    lifetime_summary = store.latest_summary(req.user_id, "user")

    # 4. episodic retrieval (cosine similarity of the current message vs stored facts)
    query_vec = embedder.embed([req.message])[0]
    stored = store.user_episodes(req.user_id)
    facts = ml.retrieve_episodes(query_vec, stored, EPISODIC_TOP_K, EPISODIC_MIN_SCORE)

    # 5. prompt assembly
    messages, parts = ml.build_prompt(session_summary and session_summary["text"],
                                      lifetime_summary and lifetime_summary["text"],
                                      window, req.message, facts)

    # 6. model call through the HW1 adapter
    result = client.complete(messages)
    reply = result.content.strip()

    # 7. save the assistant reply
    store.save_message(req.user_id, session_id, "assistant", reply)

    # 8. episodic extraction: up to 3 facts per user message, embedded and stored
    new_facts, ext = ml.extract_episodes(client, req.message)
    aux_in, aux_out = aux_in + ext.input_tokens, aux_out + ext.output_tokens
    if new_facts:
        vecs = embedder.embed([f["fact"] for f in new_facts])
        for f, v in zip(new_facts, vecs, strict=True):
            f["embedding"] = v
        new_facts = ml.dedup_facts(new_facts, stored)
    stored_facts = store.add_episodes(req.user_id, session_id, new_facts)

    # 9. summarisation trigger (every M user messages) + occasional lifetime condensation
    session_updated = lifetime_updated = False
    user_count = store.count_user_messages(req.user_id, session_id)
    if ml.should_summarize(user_count, SUMMARIZE_EVERY_USER_MSGS):
        recent = store.session_window(req.user_id, session_id, 2 * SUMMARIZE_EVERY_USER_MSGS)
        text, res = ml.summarize_session(client, session_summary and session_summary["text"], recent)
        aux_in, aux_out = aux_in + res.input_tokens, aux_out + res.output_tokens
        store.add_summary(req.user_id, session_id, "session", text)
        session_updated = True
        if ml.should_condense_lifetime(store.count_session_summaries(req.user_id),
                                       LIFETIME_EVERY_SESSION_SUMMARIES):
            text, res = ml.condense_lifetime(client, lifetime_summary and lifetime_summary["text"],
                                             store.latest_summary_per_session(req.user_id))
            aux_in, aux_out = aux_in + res.input_tokens, aux_out + res.output_tokens
            store.add_summary(req.user_id, None, "user", text)
            lifetime_updated = True

    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    usage = {
        "ts": utc_now().isoformat(), "user_id": req.user_id, "session_id": session_id,
        "turn": user_count, "short_term_n": n, "memory_policy": policy,
        "prompt_tokens": result.input_tokens,                 # Ollama prompt_eval_count
        "completion_tokens": result.output_tokens,            # Ollama eval_count
        "prompt_tokens_full": token_counter.count_chat_tokens(messages),
        "tokens_system_primer": token_counter.count_tokens(parts["system_primer"]),
        "tokens_long_term_summary": token_counter.count_tokens(parts["long_term_summary"]),
        "tokens_short_term_window": sum(token_counter.count_tokens(m["content"]) for m in window),
        "tokens_episodic_facts": token_counter.count_tokens(parts["episodic_facts"]),
        "tokens_current_message": token_counter.count_tokens(parts["current_message"]),
        "aux_prompt_tokens": aux_in, "aux_completion_tokens": aux_out,
        "short_term_count": len(window), "episodes_retrieved": len(facts),
        "episodes_stored": len(stored_facts), "session_summary_updated": session_updated,
        "lifetime_summary_updated": lifetime_updated,
        "model_latency_ms": result.latency_ms, "latency_ms": latency_ms,
        "token_count_method": token_counter.method(),
    }
    _write_usage(usage)

    return {
        "user_id": req.user_id,
        "session_id": session_id,
        "reply": reply,
        "memory_used": {
            "short_term": {"n": n, "policy": policy, "count": len(window),
                           "messages": window},
            "long_term": {
                "session_summary": session_summary and session_summary["text"],
                "lifetime_summary": lifetime_summary and lifetime_summary["text"],
            },
            "episodic": [{**f, "created_at": _iso(f["created_at"])} for f in facts],
        },
        "memory_updates": {
            "episodes_stored": [{"fact": f["fact"], "importance": f["importance"]} for f in stored_facts],
            "session_summary_updated": session_updated,
            "lifetime_summary_updated": lifetime_updated,
        },
        "usage": usage,
    }


@router.post("/api/chat")
def chat(req: ChatRequest, store: MemoryStore = Depends(get_store)) -> dict:
    """Memory-augmented chat turn (503 if the local Ollama model is not reachable)."""
    try:
        return handle_chat(req, store, get_model_client(), get_embedder())
    except requests.RequestException as exc:
        raise HTTPException(503, detail=f"Local model (Ollama) unavailable: {exc.__class__.__name__}") from exc


@router.get("/api/memory/{user_id}")
def get_memory(user_id: str, store: MemoryStore = Depends(get_store),
               messages: int = Query(16, ge=1, le=100),
               episodes: int = Query(20, ge=1, le=100)) -> dict:
    """Last ~16 messages, latest session summary, latest lifetime summary, last ~20 facts."""
    return {
        "user_id": user_id,
        "recent_messages": store.recent_user_messages(user_id, messages),
        "latest_session_summary": store.latest_session_summary_any(user_id),
        "latest_lifetime_summary": store.latest_summary(user_id, "user"),
        "recent_episodes": store.recent_episodes(user_id, episodes),
    }


@router.delete("/api/memory/{user_id}")
def delete_memory(user_id: str, store: MemoryStore = Depends(get_store)) -> dict:
    """Forget a user (messages, summaries, episodes) - used to start fresh experiment runs."""
    return {"user_id": user_id, "deleted": store.delete_user(user_id)}


@router.get("/api/aggregate/{user_id}")
def get_aggregate(user_id: str, store: MemoryStore = Depends(get_store),
                  summaries: int = Query(5, ge=1, le=50)) -> dict:
    """Daily message counts (aggregation pipeline) and the most recent summaries."""
    daily = store.daily_message_counts(user_id)
    return {
        "user_id": user_id,
        "total_messages": sum(d["messages"] for d in daily),
        "daily_message_counts": daily,
        "recent_summaries": store.recent_summaries(user_id, summaries),
    }
