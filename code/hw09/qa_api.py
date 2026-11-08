"""HW9 Part 2 - Q&A endpoint with the semantic cache at its ingress (port 8447).

    uvicorn qa_api:app --app-dir code/hw09 --port 8447
    curl -s -X POST localhost:8447/ask -H 'Content-Type: application/json' \
         -d '{"question": "What category is incident INC-000042?"}'

Every response carries is_cached, similarity and latency_ms next to the answer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import hw09_config as cfg  # noqa: E402
from hw09_common import setup_logging  # noqa: E402
from run_hw09_part2 import build_cache  # noqa: E402

app = FastAPI(title=f"{cfg.PREFIX} HW9 cached Q&A")
STATE: dict = {}


class AskIn(BaseModel):
    """Request body."""
    question: str = Field(min_length=3, max_length=500)
    threshold: float = Field(default=cfg.DEFAULT_THRESHOLD, ge=0.0, le=1.0)


@app.on_event("startup")
def startup() -> None:
    """One cache (Redis + embedder + Kafka pipeline client) per process."""
    STATE["cache"] = build_cache(setup_logging("qa-api"), cfg.DEFAULT_THRESHOLD)


@app.post("/ask")
async def ask(body: AskIn) -> dict:
    """Cache ingress -> (miss) HW8 Planner/Writer/Reviewer pipeline."""
    res = await run_in_threadpool(STATE["cache"].ask, body.question, body.threshold)
    return {"answer": res.answer, "is_cached": res.is_cached, "similarity": res.similarity,
            "latency_ms": res.latency_ms, "matched_query": res.matched_query, "reason": res.reason,
            "student": cfg.STUDENT_NAME, "prefix": cfg.PREFIX}
