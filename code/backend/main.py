"""DATA-260 HW7 backend - Municipal Transit Incidents (s1346).

Server configuration. Extends the HW2-HW5 FastAPI service:
  * MySQL (s1346_rel): incidents, transit lines, users with roles (HW4/HW5; HW7 JWT auth)
  * MongoDB (s1346_doc): document view of incidents (HW6 Part 1) and the
    messages / summaries / episodes memory collections (HW6 Part 2)
Run:  uvicorn main:app --host 0.0.0.0 --port 8446 --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pymongo.errors import ConnectionFailure, PyMongoError, ServerSelectionTimeoutError, WriteError
from sqlalchemy.exc import IntegrityError

import auth
import bike
import chat
import doc_incidents
import incidents
import incidents_n1
import lines
from database import Base, engine
from hw06_config import PORT_BASE
from mongo_db import get_mongo_db, init_mongo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("s1346")

WEB_DIR = Path(__file__).resolve().parent.parent / "web_application"
HW6_PREFIXES = ("/api/doc", "/api/chat", "/api/memory", "/api/aggregate")

app = FastAPI(title="DATA-260 HW7 - s1346 Municipal Transit Incidents API")

# CORS middleware: React (Vite) dev server + the HW6 chat page served on PORT_BASE.
# HW7: auth is a bearer token header (no cookies needed).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   f"http://localhost:{PORT_BASE}", f"http://127.0.0.1:{PORT_BASE}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_json_body(request: Request, call_next):
    """JSON body middleware for the HW6 routes: write requests must send application/json.

    FastAPI then parses the body into the Pydantic model; malformed JSON is
    reported by the validation handler below (422, type json_invalid).
    """
    if (request.method in ("POST", "PUT", "PATCH") and request.url.path.startswith(HW6_PREFIXES)
            and "application/json" not in request.headers.get("content-type", "")):
        return JSONResponse(status_code=415, content={
            "error": "unsupported_media_type",
            "detail": "Request body must be JSON (Content-Type: application/json)"})
    return await call_next(request)

# Safety net: creates any missing tables. schema.sql is the canonical migration.
Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
# Part 3 routes first: /api/incidents/naive and /fixed must match before /{incident_id}
app.include_router(incidents_n1.router)
app.include_router(incidents.router)
app.include_router(lines.router)          # HW5: related-entity CRUD + relationship query
app.include_router(doc_incidents.router)  # HW6 Part 1: MongoDB document CRUD
app.include_router(chat.router)           # HW6 Part 2: memory chat, memory view, aggregate
app.include_router(bike.router)           # HW7 Part 4: Bay Wheels ReAct/MRKL advisor


@app.on_event("startup")
def startup_mongo() -> None:
    """Create the s1346_doc collections, validators and indexes (idempotent)."""
    try:
        init_mongo()
    except PyMongoError as exc:   # MySQL routes keep working; Mongo routes answer 503
        log.error("MongoDB not available at startup: %s", exc)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Clear 422 messages for the HW6 routes; the HW4/HW5 routes keep FastAPI's default shape."""
    if not request.url.path.startswith(HW6_PREFIXES):
        return await request_validation_exception_handler(request, exc)
    errors = []
    for err in exc.errors():
        if err.get("type") == "json_invalid":       # loc is (body, char position)
            pos = err.get("loc", ("body", "?"))[-1]
            errors.append({"field": "body", "msg": f"Malformed JSON near character {pos}",
                           "type": "json_invalid"})
            continue
        loc = [str(p) for p in err.get("loc", ()) if p != "body"]
        errors.append({"field": ".".join(loc) or "body", "msg": err.get("msg"),
                       "type": err.get("type")})
    summary = "; ".join(f"{e['field']}: {e['msg']}" for e in errors)
    return JSONResponse(status_code=422, content={
        "error": "validation_error",
        "message": f"Request validation failed - {summary}",
        "detail": errors,          # list of {field, msg, type}; React client reads detail[].msg
    })


@app.exception_handler(WriteError)
def mongo_write_error_handler(request: Request, exc: WriteError):
    """A write the MongoDB $jsonSchema validator rejected (code 121) -> 400."""
    code = 400 if exc.code == 121 else 500
    return JSONResponse(status_code=code, content={
        "error": "document_validation_failed" if code == 400 else "database_error",
        "detail": "MongoDB rejected the document" if code == 400 else "Database write failed"})


@app.exception_handler(PyMongoError)
def mongo_error_handler(request: Request, exc: PyMongoError):
    """MongoDB unreachable -> 503; any other database error -> 500 (no stack trace leaked)."""
    if isinstance(exc, (ServerSelectionTimeoutError, ConnectionFailure)):
        return JSONResponse(status_code=503, content={
            "error": "database_unavailable", "detail": "MongoDB is not reachable; try again later"})
    log.exception("MongoDB error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "database_error",
                                                  "detail": "Unexpected database error"})


@app.exception_handler(Exception)
def unhandled_error_handler(request: Request, exc: Exception):
    """Last resort: 500 with a generic message (details go to the server log)."""
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "server_error",
                                                  "detail": "Internal server error"})


@app.get("/chat", include_in_schema=False)
def chat_page():
    """HW6 mini chat UI (one input box calling POST /api/chat)."""
    return FileResponse(WEB_DIR / "chat.html")


@app.exception_handler(IntegrityError)
def integrity_error_handler(request: Request, exc: IntegrityError):
    """Last-resort mapping of any unhandled DB constraint violation to 409."""
    return JSONResponse(status_code=409,
                        content={"detail": "Constraint violation: " + str(exc.orig).split("\n")[0]})


@app.get("/health")
def health():
    """Liveness + MongoDB ping (HW6)."""
    try:
        get_mongo_db().command("ping")
        mongo = "ok"
    except PyMongoError:
        mongo = "unavailable"
    return {"status": "ok", "service": "s1346", "port": PORT_BASE, "mongo": mongo}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT_BASE, reload=True)
