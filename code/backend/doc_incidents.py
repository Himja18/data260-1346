"""HW6 Part 1: CRUD route handlers for the MongoDB document view (s1346_doc.incident_reports).

Status codes: 201 create, 200 read/update/delete, 400 malformed id or a write the
MongoDB validator rejected, 404 unknown id, 422 Pydantic validation failure,
503 MongoDB unreachable, 500 any other database error (handlers in main.py).
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import DESCENDING, ReturnDocument
from pymongo.database import Database

from doc_schemas import DocCategory, IncidentDocCreate, IncidentDocOut, IncidentDocUpdate, IncidentStatus
from hw06_config import INCIDENT_DOCS
from mongo_db import get_mongo_db

router = APIRouter(prefix="/api/doc/incidents", tags=["HW6 Part 1 - MongoDB incidents"])


def _now() -> datetime:
    """Current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def _object_id(incident_id: str) -> ObjectId:
    """Parse a path id or fail with 400 (malformed) - never 500."""
    try:
        return ObjectId(incident_id)
    except (InvalidId, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail=f"'{incident_id}' is not a valid id (24 hex characters expected)")


def _out(doc: dict) -> IncidentDocOut:
    """Convert a Mongo document (with _id) to the API shape."""
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return IncidentDocOut(**doc)


@router.post("", response_model=IncidentDocOut, status_code=status.HTTP_201_CREATED)
def create_incident_doc(payload: IncidentDocCreate, db: Database = Depends(get_mongo_db)) -> IncidentDocOut:
    """Create one incident document; created_at/updated_at are set by the server."""
    now = _now()
    doc = {**payload.model_dump(), "created_at": now, "updated_at": now}
    result = db[INCIDENT_DOCS].insert_one(doc)
    return _out({**doc, "_id": result.inserted_id})


@router.get("", response_model=list[IncidentDocOut])
def list_incident_docs(
    status_filter: Optional[IncidentStatus] = Query(None, alias="status"),
    category: Optional[DocCategory] = None,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db: Database = Depends(get_mongo_db),
) -> list[IncidentDocOut]:
    """Retrieve all incident documents (newest occurrence first), optionally filtered."""
    query: dict = {}
    if status_filter:
        query["status"] = status_filter
    if category:
        query["category"] = category
    cursor = (db[INCIDENT_DOCS].find(query).sort("occurred_at", DESCENDING)
              .skip(skip).limit(limit))
    return [_out(d) for d in cursor]


@router.get("/{incident_id}", response_model=IncidentDocOut)
def get_incident_doc(incident_id: str, db: Database = Depends(get_mongo_db)) -> IncidentDocOut:
    """Get a single incident document by id."""
    doc = db[INCIDENT_DOCS].find_one({"_id": _object_id(incident_id)})
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Incident document {incident_id} not found")
    return _out(doc)


@router.put("/{incident_id}", response_model=IncidentDocOut)
def update_incident_doc(incident_id: str, payload: IncidentDocUpdate,
                        db: Database = Depends(get_mongo_db)) -> IncidentDocOut:
    """Update the fields sent in the body; updated_at is refreshed automatically."""
    oid = _object_id(incident_id)
    changes = payload.model_dump(exclude_unset=True)
    changes["updated_at"] = _now()
    doc = db[INCIDENT_DOCS].find_one_and_update({"_id": oid}, {"$set": changes},
                                                 return_document=ReturnDocument.AFTER)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Incident document {incident_id} not found")
    return _out(doc)


@router.delete("/{incident_id}")
def delete_incident_doc(incident_id: str, db: Database = Depends(get_mongo_db)) -> dict:
    """Delete one incident document."""
    result = db[INCIDENT_DOCS].delete_one({"_id": _object_id(incident_id)})
    if result.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Incident document {incident_id} not found")
    return {"deleted_id": incident_id}
