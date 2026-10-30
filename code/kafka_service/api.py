"""HW8 Part 1 - FastAPI wrapper: HTTP in, Kafka request/response behind it.

    uvicorn api:app --host 0.0.0.0 --port 8446        (inside code/kafka_service, or via docker compose)

POST /incidents            -> CREATE_INCIDENT over Kafka
GET  /incidents/{id}       -> GET_INCIDENT over Kafka
POST /kafka/request        -> any operation (lets the demo show the "Unknown operation" error)
The API never touches the incident dict; only the worker does. The correlation_id is created
here once (or taken from the X-Correlation-ID header) and returned in the body and header.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1])]

import hw08_config as cfg  # noqa: E402
from incident_service import CREATE_OP, GET_OP  # noqa: E402
from kafka_client import IncidentKafkaClient, KafkaRequestTimeout  # noqa: E402
from kafka_common import require_topics, setup_logging, wait_for_broker  # noqa: E402

log = setup_logging("api")
STATE: dict[str, Optional[IncidentKafkaClient]] = {"client": None}


class KafkaRequestIn(BaseModel):
    """Body of POST /kafka/request."""
    operation: str
    data: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):  # noqa: ANN201
    """Connect the Kafka client on startup, close it on shutdown."""
    wait_for_broker(log)
    require_topics([cfg.REQUEST_TOPIC, cfg.RESPONSE_TOPIC], log, wait_s=600)
    STATE["client"] = IncidentKafkaClient(component="api")
    log.info("FastAPI server started at http://127.0.0.1:%d (Kafka %s, requests=%s, responses=%s)",
             cfg.PORT_BASE, cfg.KAFKA_BOOTSTRAP, cfg.REQUEST_TOPIC, cfg.RESPONSE_TOPIC)
    yield
    if STATE["client"]:
        STATE["client"].close()


app = FastAPI(title=f"{cfg.PREFIX} Incident service (Kafka)", lifespan=lifespan)


def _status_for(response: dict) -> int:
    """Map a worker response to an HTTP status code."""
    if response.get("success"):
        return 200
    err = str(response.get("error", ""))
    if err == "Incident not found":
        return 404
    if err == "Unknown operation":
        return 400
    return 422


async def _call(operation: str, data: dict, correlation_id: Optional[str]) -> JSONResponse:
    """Send over Kafka in a worker thread and turn the reply into an HTTP response."""
    client = STATE["client"]
    try:
        response = await run_in_threadpool(client.request, operation, data, correlation_id)
    except KafkaRequestTimeout as exc:
        log.error("timeout: %s", exc)
        return JSONResponse({"success": False, "error": str(exc), "correlation_id": correlation_id}, 504)
    return JSONResponse(response, status_code=_status_for(response),
                        headers={"X-Correlation-ID": str(response.get("correlation_id"))})


@app.get("/health")
def health() -> dict:
    """Liveness + configuration."""
    return {"status": "ok", "port": cfg.PORT_BASE, "prefix": cfg.PREFIX, "kafka": cfg.KAFKA_BOOTSTRAP,
            "request_topic": cfg.REQUEST_TOPIC, "response_topic": cfg.RESPONSE_TOPIC}


@app.post("/incidents")
async def create_incident(body: dict[str, Any], x_correlation_id: Optional[str] = Header(None)) -> JSONResponse:
    """CREATE_INCIDENT (validation happens in the worker, so errors come back over Kafka)."""
    return await _call(CREATE_OP, body, x_correlation_id)


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, x_correlation_id: Optional[str] = Header(None)) -> JSONResponse:
    """GET_INCIDENT."""
    return await _call(GET_OP, {"incident_id": incident_id}, x_correlation_id)


@app.post("/kafka/request")
async def raw_request(body: KafkaRequestIn, x_correlation_id: Optional[str] = Header(None)) -> JSONResponse:
    """Forward any operation to the worker."""
    return await _call(body.operation, body.data, x_correlation_id)
