"""
code/backend/main.py — DATA-260 HW2 Part 2: FastAPI backend

Serves the transit-incident entity list/form (code/web_application/) and
exposes a small JSON API on PORT_BASE (8446) for the domain entity
"Municipal Transit Incident" (Domain 2):

  GET    /                      -> the HTML app (list + form)
  GET    /script.js             -> the frontend JS
  GET    /api/incidents?q=...   -> list incidents, optionally filtered by
                                    primary field (routeId) or secondary
                                    field (category), case-insensitive
  POST   /api/incidents         -> add a new incident record
  PUT    /api/incidents/1       -> update record ID 1 to fixed,
                                    domain-appropriate values (HW2 Part 2.2)
  DELETE /api/incidents/highest -> delete the record with the highest ID
                                    (HW2 Part 2.3)

Storage is an in-memory list seeded with a couple of example records —
sufficient for a homework smoke test / demo. Restarting the server resets
the data.

Run:
    uvicorn code.backend.main:app --host 0.0.0.0 --port 8446 --reload
or, from inside code/backend/:
    uvicorn main:app --host 0.0.0.0 --port 8446 --reload
"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PORT_BASE = 8446  
APP_DIR = Path(__file__).resolve().parent
WEB_DIR = (APP_DIR / ".." / "web_application").resolve()

app = FastAPI(title="DATA-260 HW2 — Municipal Transit Incidents API")

class IncidentIn(BaseModel):
    """Shape of the JSON body the frontend POSTs when adding an incident."""
    routeId: str  # primary field
    location: str
    reporterEmail: str
    description: str
    category: str  # secondary field
    agreeToTerms: Optional[bool] = True


class Incident(IncidentIn):
    id: int

INCIDENTS: list[Incident] = [
    Incident(
        id=1,
        routeId="Line 22 - Bus stalled on Main St",
        location="Main St & 5th Ave stop",
        reporterEmail="jane.doe@email.com",
        description="The 8:15 AM bus on Route 22 broke down near Main St and 5th Ave.",
        category="Breakdown",
    ),
    Incident(
        id=2,
        routeId="Line 8 - Signal delay downtown",
        location="4th St & Market",
        reporterEmail="rider2@email.com",
        description="Riders reported a 15 minute signal delay near the downtown loop.",
        category="Delay",
    ),
]

@app.get("/")
def serve_index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/script.js")
def serve_script():
    return FileResponse(WEB_DIR / "script.js", media_type="application/javascript")


@app.get("/api/incidents", response_model=list[Incident])
def list_incidents(q: Optional[str] = None):
    """Return all incidents, or those matching q against the primary field
    (routeId) or secondary field (category), case-insensitive substring."""
    if not q:
        return INCIDENTS

    needle = q.lower()
    return [
        incident
        for incident in INCIDENTS
        if needle in incident.routeId.lower() or needle in incident.category.lower()
    ]

@app.post("/api/incidents", response_model=Incident, status_code=201)
def add_incident(payload: IncidentIn):
    global _next_id
    incident = Incident(id=_next_id, **payload.model_dump())
    INCIDENTS.append(incident)
    _next_id += 1
    return incident


@app.put("/api/incidents/1", response_model=Incident)
def update_record_one():
    for i, incident in enumerate(INCIDENTS):
        if incident.id == 1:
            updated = incident.model_copy(update={
                "routeId": "Line 22 - Bus back in service on Main St",
                "location": "Main St & 5th Ave stop",
                "description": "Replacement vehicle arrived; Route 22 service has resumed on schedule.",
                "category": "Service Change",
            })
            INCIDENTS[i] = updated
            return updated
    raise HTTPException(status_code=404, detail="Record with ID 1 not found")

@app.delete("/api/incidents/highest", status_code=200)
def delete_highest():
    if not INCIDENTS:
        raise HTTPException(status_code=404, detail="No incidents to delete")

    highest = max(INCIDENTS, key=lambda incident: incident.id)
    INCIDENTS.remove(highest)
    return {"deleted_id": highest.id}

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")