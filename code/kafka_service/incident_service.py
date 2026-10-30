"""HW8 Part 1 - Incident domain logic used by the Kafka worker (no Kafka code in here, so it is unit-testable).

Operations: CREATE_INCIDENT and GET_INCIDENT. Incidents live in a plain Python dict inside the worker.
Every response echoes the request's correlation_id unchanged, including error responses.
Idempotency: a request whose correlation_id was already processed returns the cached response
and has no new side effect (no second incident is created).
"""
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError, field_validator

import hw08_config as cfg

CREATE_OP = "CREATE_INCIDENT"
GET_OP = "GET_INCIDENT"
OPERATIONS = (CREATE_OP, GET_OP)
REQUIRED_ENVELOPE = ("correlation_id", "reply_to", "operation", "data")


class IncidentData(BaseModel):
    """Required fields of a Municipal Transit Incident (the primary domain entity)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    route_title: StrictStr = Field(..., min_length=3, max_length=200)    # e.g. "Line 22 - Mission St"
    location: StrictStr = Field(..., min_length=2, max_length=200)       # stop / station / intersection
    category: StrictStr                                                  # Delay | Breakdown | Accident | Service Change
    passengers_affected: StrictInt = Field(..., ge=0, le=100000)
    description: Optional[StrictStr] = Field(None, max_length=1000)

    @field_validator("category")
    @classmethod
    def category_allowed(cls, value: str) -> str:
        """Only the four domain categories are accepted."""
        if value not in cfg.CATEGORIES:
            raise ValueError(f"must be one of {', '.join(cfg.CATEGORIES)}")
        return value


def clean_validation_error(exc: ValidationError) -> str:
    """Turn a Pydantic error into one short, readable message."""
    parts = []
    for err in exc.errors():
        field = ".".join(str(x) for x in err.get("loc", ())) or "data"
        kind = err.get("type", "")
        if kind == "missing":
            msg = "is required"
        elif kind == "extra_forbidden":
            msg = "is not an allowed field"
        elif kind == "string_too_short" and err.get("input", None) in ("", None):
            msg = "must not be empty"
        else:
            msg = str(err.get("msg", "is invalid")).replace("Value error, ", "")
        parts.append(f"{field} {msg}")
    return "Validation failed: " + "; ".join(parts)


class IncidentService:
    """Plain-dict incident store plus request handling with correlation-id idempotency."""

    def __init__(self, idempotent: bool = True, cache_size: int = 10000) -> None:
        self.incidents: dict[str, dict[str, Any]] = {}
        self.idempotent = idempotent
        self._processed: OrderedDict[str, dict] = OrderedDict()
        self._cache_size = cache_size

    # ---- envelope -------------------------------------------------------------------
    @staticmethod
    def check_envelope(request: Any) -> Optional[str]:
        """Return an error message if the request envelope is malformed, else None."""
        if not isinstance(request, dict):
            return "Request must be a JSON object"
        missing = [k for k in REQUIRED_ENVELOPE if k not in request]
        if missing:
            return f"Request is missing required field(s): {', '.join(missing)}"
        if not isinstance(request["correlation_id"], str) or not request["correlation_id"].strip():
            return "correlation_id must be a non-empty string"
        if not isinstance(request["data"], dict):
            return "data must be a JSON object"
        return None

    @staticmethod
    def safe_reply_topic(request: Any) -> str:
        """Reply to the topic named by reply_to, but only if it is one of our PREFIX topics."""
        reply_to = request.get("reply_to") if isinstance(request, dict) else None
        if isinstance(reply_to, str) and reply_to.startswith(f"{cfg.PREFIX}_"):
            return reply_to
        return cfg.RESPONSE_TOPIC

    # ---- operations -----------------------------------------------------------------
    def handle(self, request: Any) -> tuple[dict, bool]:
        """Process one request; returns (response, was_duplicate)."""
        corr = request.get("correlation_id") if isinstance(request, dict) else None
        if self.idempotent and isinstance(corr, str) and corr in self._processed:
            return dict(self._processed[corr]), True

        response = self._dispatch(request, corr)
        if self.idempotent and isinstance(corr, str) and corr:
            self._processed[corr] = response
            if len(self._processed) > self._cache_size:
                self._processed.popitem(last=False)
        return response, False

    def _dispatch(self, request: Any, corr: Optional[str]) -> dict:
        """Validate the envelope and route to the operation."""
        op = request.get("operation") if isinstance(request, dict) else None
        envelope_error = self.check_envelope(request)
        if envelope_error:
            return self.error(corr, op, envelope_error)
        if op == CREATE_OP:
            return self.create(corr, request["data"])
        if op == GET_OP:
            return self.get(corr, request["data"])
        return self.error(corr, op, "Unknown operation")

    def create(self, corr: str, data: dict) -> dict:
        """CREATE_INCIDENT: validate fields, store under a new UUID, return the id."""
        try:
            incident = IncidentData.model_validate(data)
        except ValidationError as exc:
            return self.error(corr, CREATE_OP, clean_validation_error(exc))
        incident_id = str(uuid.uuid4())
        self.incidents[incident_id] = {"incident_id": incident_id, **incident.model_dump(),
                                       "created_at": datetime.now(UTC).isoformat(timespec="seconds")}
        return {"correlation_id": corr, "operation": CREATE_OP, "success": True,
                "incident_id": incident_id, "message": "Incident created"}

    def get(self, corr: str, data: dict) -> dict:
        """GET_INCIDENT: look the id up in the dict."""
        extra = set(data) - {"incident_id"}
        if extra:
            return self.error(corr, GET_OP, f"Validation failed: {', '.join(sorted(extra))} is not an allowed field")
        incident_id = data.get("incident_id")
        if not isinstance(incident_id, str) or not incident_id.strip():
            return self.error(corr, GET_OP, "Validation failed: incident_id is required")
        try:
            uuid.UUID(incident_id.strip())
        except ValueError:
            return self.error(corr, GET_OP, "Validation failed: incident_id must be a valid UUID")
        incident = self.incidents.get(incident_id.strip())
        if incident is None:
            return self.error(corr, GET_OP, "Incident not found")
        return {"correlation_id": corr, "operation": GET_OP, "success": True, "incident": dict(incident)}

    @staticmethod
    def error(corr: Optional[str], op: Any, message: str) -> dict:
        """Clean error response that still carries the original correlation_id."""
        return {"correlation_id": corr, "operation": op if isinstance(op, str) else None,
                "success": False, "error": message}
