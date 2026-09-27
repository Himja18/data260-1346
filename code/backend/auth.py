"""Login / logout / me, backed by the MySQL `sessions` table."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from database import get_db
from models import User, UserSession, utcnow
from schemas import LoginIn, UserOut
from security import new_session_token, verify_password

COOKIE_NAME = "s1346_sid"
SESSION_TTL = timedelta(hours=2)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the cookie's opaque token to a user via the sessions table."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Login required")

    sess = db.get(UserSession, token)
    if sess is None:
        raise HTTPException(status_code=401, detail="Login required")
    if sess.expires_at <= utcnow():
        db.delete(sess)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired")
    return sess.user


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid email or password")

    now = utcnow()
    sess = UserSession(id=new_session_token(), user_id=user.id,
                       created_at=now, expires_at=now + SESSION_TTL)
    db.add(sess)
    db.commit()

    response.set_cookie(
        key=COOKIE_NAME,
        value=sess.id,                 # opaque token only - no user data
        httponly=True,
        samesite="lax",
        secure=False,                  # plain http on localhost; True behind HTTPS
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )
    return user


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        sess = db.get(UserSession, token)
        if sess:
            db.delete(sess)
            db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
