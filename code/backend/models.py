"""ORM models for s1346_rel (HW5)."""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


def utcnow() -> datetime:
    # MySQL DATETIME is timezone-naive; store naive UTC consistently.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TransitLine(Base):
    """Related entity (the 'author' role): one line has many incidents."""
    __tablename__ = "transit_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), unique=True, nullable=False)   # unique field, e.g. "L-042"
    name = Column(String(100), nullable=False)               # primary text field
    mode = Column(String(20), nullable=False)                # secondary text field
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # passive_deletes: let the DB's ON DELETE RESTRICT decide; never null-out children.
    incidents = relationship("Incident", back_populates="line", passive_deletes="all")


class Incident(Base):
    """Primary domain entity: Municipal Transit Incident."""
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("passengers_affected >= 0", name="ck_passengers_nonneg"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_code = Column(String(10), unique=True, nullable=False)  # unique field
    route_title = Column(String(200), nullable=False)        # primary field
    category = Column(String(50), nullable=False)            # secondary field
    passengers_affected = Column(Integer, nullable=False, default=0, server_default="0")
    line_id = Column(Integer, ForeignKey("transit_lines.id", ondelete="RESTRICT"),
                     nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Default lazy="select" -> accessing .line fires one query per incident (N+1 in HW4 Part 3).
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
