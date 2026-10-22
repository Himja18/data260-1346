"""Pydantic schemas for the HW6 Part 1 MongoDB document API (incident_reports)."""
from datetime import UTC, datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IncidentStatus = Literal["Reported", "Investigating", "Resolved", "Closed"]
DocCategory = Literal["Delay", "Breakdown", "Accident", "Service Change"]

FUTURE_TOLERANCE = timedelta(minutes=5)


def _as_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC so every stored date is comparable."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _check_not_future(value: Optional[datetime]) -> Optional[datetime]:
    """An incident cannot have occurred in the future."""
    if value is None:
        return value
    value = _as_utc(value)
    if value > datetime.now(UTC) + FUTURE_TOLERANCE:
        raise ValueError("occurred_at cannot be in the future")
    return value


class IncidentDocCreate(BaseModel):
    """Body for POST /api/doc/incidents."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=100,
                       examples=["Line 22 - bus stalled on Main St"])
    description: Optional[str] = Field(None, max_length=2000)
    location: Optional[str] = Field(None, max_length=100, examples=["Main St & 5th Ave"])
    status: IncidentStatus = "Reported"
    category: DocCategory
    occurred_at: datetime = Field(..., examples=["2026-10-16T08:15:00Z"])

    @field_validator("occurred_at")
    @classmethod
    def occurred_not_in_future(cls, value: Optional[datetime]) -> Optional[datetime]:
        """Reject incident times in the future."""
        return _check_not_future(value)


class IncidentDocUpdate(BaseModel):
    """Body for PUT /api/doc/incidents/{id}: any subset of fields, at least one."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    location: Optional[str] = Field(None, max_length=100)
    status: Optional[IncidentStatus] = None
    category: Optional[DocCategory] = None
    occurred_at: Optional[datetime] = None

    @field_validator("occurred_at")
    @classmethod
    def occurred_not_in_future(cls, value: Optional[datetime]) -> Optional[datetime]:
        """Reject incident times in the future."""
        return _check_not_future(value)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "IncidentDocUpdate":
        """Reject an empty update and nulls on required fields."""
        sent = self.model_fields_set
        if not sent:
            raise ValueError("update body must contain at least one field")
        for required in ("title", "status", "category", "occurred_at"):
            if required in sent and getattr(self, required) is None:
                raise ValueError(f"{required} cannot be null")
        return self


class IncidentDocOut(BaseModel):
    """One incident document as returned by the API."""
    id: str
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    status: IncidentStatus
    category: DocCategory
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime
