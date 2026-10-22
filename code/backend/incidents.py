"""CRUD for Municipal Transit Incidents (HW7: JWT bearer auth + roles).

  list / read      any authenticated role (reader, writer, moderator)
  create / update  writer or moderator
  delete           moderator only
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import DELETE_ROLES, READ_ROLES, WRITE_ROLES, require_roles
from database import get_db
from models import Incident, TransitLine
from schemas import IncidentIn, IncidentOut

router = APIRouter(
    prefix="/api/incidents",
    tags=["incidents"],
    dependencies=[Depends(require_roles(*READ_ROLES))],   # baseline: any valid token
)


def _get_or_404(db: Session, incident_id: int) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident


def _check_refs(db: Session, payload: IncidentIn, exclude_id: int | None = None):
    """Constraint checks with clear messages (the DB constraints are the backstop)."""
    if payload.line_id is not None and db.get(TransitLine, payload.line_id) is None:
        raise HTTPException(422, detail=f"line_id {payload.line_id} does not exist")
    if payload.incident_code:
        q = select(Incident.id).where(Incident.incident_code == payload.incident_code)
        if exclude_id is not None:
            q = q.where(Incident.id != exclude_id)
        if db.scalar(q) is not None:
            raise HTTPException(409, detail=f"Incident code '{payload.incident_code}' already exists")


def _commit_or_409(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="Constraint violation: duplicate incident_code "
                                        "or invalid line_id") from None


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """View all records (paged, newest first). Kept as a plain list so the HW4 client works."""
    return (db.query(Incident).order_by(Incident.id.desc())
              .offset(offset).limit(limit).all())


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, incident_id)


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_roles(*WRITE_ROLES))])
def create_incident(payload: IncidentIn, db: Session = Depends(get_db)):
    _check_refs(db, payload)
    data = payload.model_dump()
    auto_code = data["incident_code"] is None
    if auto_code:   # temporary unique placeholder, replaced with INC-<id> below
        data["incident_code"] = f"TMP-{uuid4().hex[:6]}"
    incident = Incident(**data)
    db.add(incident)
    try:
        db.flush()                                  # assigns incident.id
        if auto_code:
            incident.incident_code = f"INC-{incident.id:06d}"
            db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="Could not assign a unique incident_code; "
                                        "supply one explicitly") from None
    _commit_or_409(db)
    db.refresh(incident)
    return incident


@router.put("/{incident_id}", response_model=IncidentOut,
            dependencies=[Depends(require_roles(*WRITE_ROLES))])
def update_incident(incident_id: int, payload: IncidentIn, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    _check_refs(db, payload, exclude_id=incident_id)
    for field, value in payload.model_dump(exclude_none=False).items():
        if field == "incident_code" and value is None:
            continue                                # keep the existing code
        setattr(incident, field, value)
    _commit_or_409(db)
    db.refresh(incident)
    return incident


@router.delete("/{incident_id}", dependencies=[Depends(require_roles(*DELETE_ROLES))])
def delete_incident(incident_id: int, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    db.delete(incident)
    db.commit()
    return {"deleted_id": incident_id}
