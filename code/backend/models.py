"""ORM models for s1346_rel."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


def utcnow() -> datetime:
    # MySQL DATETIME is timezone-naive; store naive UTC consistently.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TransitLine(Base):
    """Related entity (Part 3 seeds 200 of these). Full CRUD comes in a later HW."""
    __tablename__ = "transit_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), unique=True, nullable=False)   # e.g. "L-042"
    name = Column(String(100), nullable=False)               # e.g. "Line 42 - Crosstown"
    mode = Column(String(20), nullable=False)                # Bus / Light Rail / Subway ...

    incidents = relationship("Incident", back_populates="line")


class Incident(Base):
    """Primary domain entity: Municipal Transit Incident."""
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_title = Column(String(200), nullable=False)        # primary field
    category = Column(String(50), nullable=False)            # secondary field
    line_id = Column(Integer, ForeignKey("transit_lines.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    # Default lazy="select" -> accessing .line fires one query per incident (N+1 in Part 3).
    line = relationship("TransitLine", back_populates="incidents")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    """Server-side session. The browser cookie holds ONLY this row's opaque id."""
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)                # session token
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="sessions")
