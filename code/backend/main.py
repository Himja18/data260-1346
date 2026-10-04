"""DATA-260 HW5 backend - Municipal Transit Incidents (s1346).

Extends the HW2/HW3 FastAPI service: data now lives in MySQL (s1346_rel),
and auth uses server-side sessions referenced by an HTTP-only cookie.
Run:  uvicorn main:app --host 0.0.0.0 --port 8446 --reload
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from fastapi.middleware.cors import CORSMiddleware

import auth
import incidents
import incidents_n1
import lines
from database import Base, engine

PORT_BASE = 8446

app = FastAPI(title="DATA-260 HW5 - s1346 Municipal Transit Incidents API")

# React (Vite) dev server; allow_credentials so the session cookie is sent.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Safety net: creates any missing tables. schema.sql is the canonical migration.
Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
# Part 3 routes first: /api/incidents/naive and /fixed must match before /{incident_id}
app.include_router(incidents_n1.router)
app.include_router(incidents.router)
app.include_router(lines.router)          # HW5: related-entity CRUD + relationship query


@app.exception_handler(IntegrityError)
def integrity_error_handler(request: Request, exc: IntegrityError):
    """Last-resort mapping of any unhandled DB constraint violation to 409."""
    return JSONResponse(status_code=409,
                        content={"detail": "Constraint violation: " + str(exc.orig).split("\n")[0]})


@app.get("/health")
def health():
    return {"status": "ok", "service": "s1346", "port": PORT_BASE}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT_BASE, reload=True)
