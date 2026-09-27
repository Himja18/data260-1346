"""CRUD for Municipal Transit Incidents. Every route requires a logged-in session."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Incident
from schemas import IncidentIn, IncidentOut

router = APIRouter(
    prefix="/api/incidents",
    tags=["incidents"],
    dependencies=[Depends(get_current_user)],
)


def _get_or_404(db: Session, incident_id: int) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """View all records (paged, newest first)."""
    return (db.query(Incident).order_by(Incident.id.desc())
              .offset(offset).limit(limit).all())


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, incident_id)


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
def create_incident(payload: IncidentIn, db: Session = Depends(get_db)):
    incident = Incident(**payload.model_dump())   # id auto-incremented by MySQL
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.put("/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: int, payload: IncidentIn, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    for field, value in payload.model_dump().items():
        setattr(incident, field, value)
    db.commit()
    db.refresh(incident)
    return incident


@router.delete("/{incident_id}")
def delete_incident(incident_id: int, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    db.delete(incident)
    db.commit()
    return {"deleted_id": incident_id}
