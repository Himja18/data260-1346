"""Request/response shapes for the HW5 API."""
from datetime import datetime
from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Plain string + simple pattern instead of EmailStr: EmailStr rejects reserved
# test domains such as ".test", which we use for local demo accounts.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

# Unique-field formats (validated by Pydantic -> 422 on mismatch).
LINE_CODE_PATTERN = r"^L-\d{3}$"          # L-001 ... L-999 (matches seeded lines)
INCIDENT_CODE_PATTERN = r"^INC-\d{6}$"    # INC-000001

Category = Literal["Delay", "Breakdown", "Accident", "Service Change"]
Mode = Literal["Bus", "Light Rail", "Subway", "Commuter Rail"]

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Paginated list envelope."""
    total: int
    limit: int
    offset: int
    items: list[T]


# ---- Related entity: TransitLine -------------------------------------------
class TransitLineIn(BaseModel):
    code: str = Field(..., pattern=LINE_CODE_PATTERN, examples=["L-201"])
    name: str = Field(..., min_length=3, max_length=100)     # primary text field
    mode: Mode                                               # secondary text field


class TransitLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    mode: str
    created_at: datetime
    updated_at: datetime


# ---- Primary entity: Incident ------------------------------------------------
class IncidentIn(BaseModel):
    # Optional on create: the server assigns INC-<id> if omitted, so the
    # existing React forms keep working. If supplied, the format is enforced.
    incident_code: Optional[str] = Field(None, pattern=INCIDENT_CODE_PATTERN,
                                         examples=["INC-900001"])
    route_title: str = Field(..., min_length=3, max_length=200)
    category: Category
    passengers_affected: int = Field(0, ge=0, le=100000)
    line_id: Optional[int] = Field(None, ge=1)


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_code: str
    route_title: str
    category: str
    passengers_affected: int
    line_id: Optional[int]
    created_at: datetime
    updated_at: datetime


# ---- Auth (HW7: JWT, username + role) ---------------------------------------
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]{3,50}$"
Role = Literal["reader", "writer", "moderator"]


class LoginIn(BaseModel):
    username: str = Field(..., pattern=USERNAME_PATTERN, examples=["writer1346"])
    password: str = Field(..., min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int            # seconds
    role: Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    name: Optional[str] = None
