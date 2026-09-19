"""
DATA 260 HW3 - Part 1
FastAPI auth demo for Domain 2 (Municipal Transit Incidents).
SID4=1346, PORT_BASE=8446, PREFIX=s1346
"""
import os
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from auth import router as auth_router

PORT_BASE = 8446

app = FastAPI(title="s1346 Municipal Transit Incident Portal - HW3 Auth Demo")

SESSION_SECRET = os.environ.get("SESSION_SECRET", "s1346-hw3-dev-secret-change-me")
HTTPS_ONLY = os.environ.get("HTTPS_ONLY", "1") != "0"

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="s1346_session",
    max_age=None,
    same_site="lax",
    https_only=HTTPS_ONLY,
)

app.include_router(auth_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT_BASE)