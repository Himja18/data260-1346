"""HW4 Part 3: N+1 demonstration - two list endpoints that return the SAME data.

  GET /api/incidents/naive?limit=N   1 query for the page + 1 query PER incident
                                     to fetch its transit line  ->  N+1 statements
  GET /api/incidents/fixed?limit=N   1 query total: incidents LEFT JOIN transit_lines
                                     via joinedload             ->  1 statement

Both need a logged-in session (same as the rest of /api/incidents), accept an
optional ?category= filter, and report their own SQL statement count in the
body ("sql_statements") and in the X-SQL-Count response header.
"""
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session, joinedload

from auth import get_current_user
from database import get_db
from models import Incident, TransitLine
from sql_counter import count_sql

router = APIRouter(
    prefix="/api/incidents",
    tags=["incidents: N+1 (Part 3)"],
    dependencies=[Depends(get_current_user)],
)


def _line_dict(line: Optional[TransitLine]):
    if line is None:
        return None
    return {"id": line.id, "code": line.code, "name": line.name, "mode": line.mode}


def _item(inc: Incident, line: Optional[TransitLine]):
    return {
        "id": inc.id,
        "route_title": inc.route_title,
        "category": inc.category,
        "created_at": inc.created_at.isoformat(),
        "line_id": inc.line_id,
        "line": _line_dict(line),          # related data included in the list response
    }


def _page_query(db: Session, category: Optional[str]):
    q = db.query(Incident)
    if category:
        q = q.filter(Incident.category == category)
    return q.order_by(Incident.id.desc())


def _envelope(version, limit, category, items, stmts, started, response: Response):
    server_ms = (time.perf_counter() - started) * 1000
    response.headers["X-SQL-Count"] = str(len(stmts))
    response.headers["X-Server-Ms"] = f"{server_ms:.2f}"
    return {
        "version": version,
        "limit": limit,
        "category": category,
        "returned": len(items),
        "sql_statements": len(stmts),
        "server_ms": round(server_ms, 2),
        "sql_sample": stmts[:2],           # first statements, to show the query shape
        "items": items,
    }


@router.get("/naive")
def list_incidents_naive(
    response: Response,
    limit: int = Query(10, ge=1, le=500),
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Intentionally naive: one extra SELECT per incident for its transit line."""
    started = time.perf_counter()
    with count_sql() as stmts:
        incidents = _page_query(db, category).limit(limit).all()          # 1 query
        items = []
        for inc in incidents:                                             # + N queries
            line = (
                db.query(TransitLine).filter(TransitLine.id == inc.line_id).first()
                if inc.line_id is not None else None
            )
            items.append(_item(inc, line))
    return _envelope("naive", limit, category, items, stmts, started, response)


@router.get("/fixed")
def list_incidents_fixed(
    response: Response,
    limit: int = Query(10, ge=1, le=500),
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Fixed: eager-load the line with a LEFT OUTER JOIN in the same query."""
    started = time.perf_counter()
    with count_sql() as stmts:
        incidents = (_page_query(db, category)
                     .options(joinedload(Incident.line))                  # 1 query total
                     .limit(limit).all())
        items = [_item(inc, inc.line) for inc in incidents]               # no extra queries
    return _envelope("fixed", limit, category, items, stmts, started, response)
