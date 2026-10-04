"""HW5 Part 1: CRUD for the related entity (transit lines) + relationship query.
Every route requires a logged-in session, like /api/incidents."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Incident, TransitLine
from schemas import IncidentOut, Page, TransitLineIn, TransitLineOut

router = APIRouter(
    prefix="/api/lines",
    tags=["transit lines"],
    dependencies=[Depends(get_current_user)],
)


def get_line_or_404(db: Session, line_id: int) -> TransitLine:
    line = db.get(TransitLine, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail=f"Transit line {line_id} not found")
    return line


def _code_taken(db: Session, code: str, exclude_id: int | None = None) -> bool:
    q = select(TransitLine.id).where(TransitLine.code == code)
    if exclude_id is not None:
        q = q.where(TransitLine.id != exclude_id)
    return db.scalar(q) is not None


def _commit_or_409(db: Session, detail: str):
    try:
        db.commit()
    except IntegrityError:            # race-safe backstop for the UNIQUE / FK constraints
        db.rollback()
        raise HTTPException(status_code=409, detail=detail)


@router.post("", response_model=TransitLineOut, status_code=status.HTTP_201_CREATED)
def create_line(payload: TransitLineIn, db: Session = Depends(get_db)):
    if _code_taken(db, payload.code):
        raise HTTPException(409, detail=f"Line code '{payload.code}' already exists")
    line = TransitLine(**payload.model_dump())
    db.add(line)
    _commit_or_409(db, f"Line code '{payload.code}' already exists")
    db.refresh(line)
    return line


@router.get("", response_model=Page[TransitLineOut])
def list_lines(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """All transit lines, paginated (ordered by id)."""
    total = db.scalar(select(func.count()).select_from(TransitLine))
    items = db.scalars(select(TransitLine).order_by(TransitLine.id)
                       .offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/{line_id}", response_model=TransitLineOut)
def get_line(line_id: int, db: Session = Depends(get_db)):
    return get_line_or_404(db, line_id)


@router.put("/{line_id}", response_model=TransitLineOut)
def update_line(line_id: int, payload: TransitLineIn, db: Session = Depends(get_db)):
    line = get_line_or_404(db, line_id)
    if _code_taken(db, payload.code, exclude_id=line_id):
        raise HTTPException(409, detail=f"Line code '{payload.code}' already exists")
    for field, value in payload.model_dump().items():
        setattr(line, field, value)
    _commit_or_409(db, f"Line code '{payload.code}' already exists")
    db.refresh(line)
    return line


@router.delete("/{line_id}")
def delete_line(line_id: int, db: Session = Depends(get_db)):
    """Blocked (409) while incidents still reference the line; the DB's
    ON DELETE RESTRICT enforces the same rule if this check is bypassed."""
    line = get_line_or_404(db, line_id)
    n = db.scalar(select(func.count()).select_from(Incident)
                  .where(Incident.line_id == line_id))
    if n:
        raise HTTPException(
            409, detail=f"Cannot delete line {line.code}: {n} incident(s) still reference it. "
                        f"Delete or reassign them first.")
    db.delete(line)
    _commit_or_409(db, f"Cannot delete line {line.code}: incidents still reference it")
    return {"deleted_id": line_id}


@router.get("/{line_id}/incidents", response_model=Page[IncidentOut])
def incidents_for_line(
    line_id: int,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Relationship query: all incidents reported on one transit line."""
    get_line_or_404(db, line_id)
    base = select(Incident).where(Incident.line_id == line_id)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    items = db.scalars(base.order_by(Incident.id.desc()).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": items}
