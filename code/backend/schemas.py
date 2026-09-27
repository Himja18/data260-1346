"""Request/response shapes for the HW4 API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Plain string + simple pattern instead of EmailStr: EmailStr rejects reserved
# test domains such as ".test", which we use for local demo accounts.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class IncidentIn(BaseModel):
    route_title: str = Field(..., min_length=3, max_length=200)
    category: str = Field(..., min_length=2, max_length=50)
    line_id: Optional[int] = None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_title: str
    category: str
    line_id: Optional[int]
    created_at: datetime


class LoginIn(BaseModel):
    email: str = Field(..., max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(..., min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
