"""ORM models for s1346_rel (HW5; HW7 adds username + role to users)."""
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


def utcnow() -> datetime:
    # MySQL DATETIME is timezone-naive; store naive UTC consistently.
    return datetime.now(UTC).replace(tzinfo=None)


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


ROLES = ("reader", "writer", "moderator")


class User(Base):
    """Login account. HW7: JWT login by username; role drives authorization."""
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('reader', 'writer', 'moderator')", name="ck_users_role"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)        # PBKDF2-SHA256, never plain text
    role = Column(String(20), nullable=False, default="reader", server_default="reader")
    # Kept from HW4/HW5 for the existing account; optional for new users.
    name = Column(String(100), nullable=True)
    email = Column(String(255), unique=True, nullable=True)
