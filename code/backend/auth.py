"""HW7 Part 1 - JWT bearer authentication and role-based authorization.

Replaces the HW4/HW5 server-side session cookie (that version is kept only as
history at the `hw4` tag). Every graded domain route now expects

    Authorization: Bearer <access token>

  POST /auth/login   username + password -> {access_token, token_type, expires_in, role}
                     401 for an unknown user or a wrong password
  GET  /auth/me      the authenticated user's id, username and role (401 without a valid token)

Passwords are stored only as PBKDF2-SHA256 hashes in MySQL (users.password_hash);
the token is signed with HS256 using JWT_SECRET from the environment (rule N1).
Roles: reader < writer < moderator. `require_roles(...)` is the per-route guard:
401 = missing / malformed / expired / forged token, 403 = valid token, wrong role.
"""
import logging
import os
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import ROLES, User
from schemas import LoginIn, TokenOut, UserOut
from security import verify_password

log = logging.getLogger("s1346.auth")

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "s1346"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    # No secret configured: use a random one so nothing is hard-coded (AGENT.md N1).
    # Tokens then stop working when the server restarts - set JWT_SECRET for real runs.
    JWT_SECRET = secrets.token_urlsafe(48)
    log.warning("JWT_SECRET not set; using a random per-process secret")

router = APIRouter(prefix="/auth", tags=["auth (HW7 JWT)"])
bearer_scheme = HTTPBearer(auto_error=False)        # we raise our own 401s

READ_ROLES = ROLES                                  # reader, writer, moderator
WRITE_ROLES = ("writer", "moderator")
DELETE_ROLES = ("moderator",)


def _unauthorized(detail: str) -> HTTPException:
    """401 with the standard Bearer challenge header."""
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})


def create_access_token(user: User, expires_delta: timedelta | None = None) -> str:
    """Sign a short-lived HS256 access token for this user."""
    now = datetime.now(UTC)
    delta = expires_delta if expires_delta is not None else timedelta(minutes=ACCESS_TOKEN_MINUTES)
    claims = {
        "sub": user.username,
        "uid": user.id,
        "role": user.role,
        "iss": JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + delta).timestamp()),
    }
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Verify signature, issuer and expiry; raise a 401 HTTPException on any problem."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], issuer=JWT_ISSUER,
                          options={"require": ["exp", "iat", "sub", "uid"]})
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired") from None
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token") from None


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token to a user row (401 if missing, invalid, expired or unknown)."""
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise _unauthorized("Not authenticated: missing bearer token")
    claims = decode_access_token(creds.credentials)
    user = db.get(User, claims["uid"])
    if user is None or user.username != claims["sub"]:
        raise _unauthorized("Invalid token: user no longer exists")
    return user


def require_roles(*allowed: str) -> Callable[..., User]:
    """Route dependency: allow only users whose role (read from MySQL) is in `allowed`."""
    unknown = set(allowed) - set(ROLES)
    if unknown:
        raise ValueError(f"unknown role(s): {sorted(unknown)}")

    def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{user.role}' cannot do this (needs {' or '.join(allowed)})")
        return user

    return guard


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> dict:
    """Check the password hash stored in MySQL; issue a JWT only after it verifies."""
    user = db.query(User).filter(User.username == payload.username.strip().lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise _unauthorized("Invalid username or password")
    return {"access_token": create_access_token(user), "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_MINUTES * 60, "role": user.role}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    """Identity and role of the token's owner."""
    return user
