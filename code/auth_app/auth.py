"""
DATA 260 HW3 - Part 1: auth.py
Router for the Municipal Transit Incident Portal auth demo (Domain 2, s1346).
"""
import time
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

IDLE_TIMEOUT_SECONDS = 60  # short on purpose, to make the demo/proof easy

USERS = {
    "dispatcher1346": "TransitLine22!",
}


def _session_is_live(request: Request) -> bool:
    username = request.session.get("username")
    last_active = request.session.get("last_active")
    if not username or not last_active:
        return False
    if time.time() - last_active > IDLE_TIMEOUT_SECONDS:
        request.session.clear()
        return False
    return True


def _touch(request: Request) -> None:
    request.session["last_active"] = time.time()


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    logged_in = _session_is_live(request)
    if logged_in:
        _touch(request)
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "logged_in": logged_in,
            "username": request.session.get("username"),
        },
    )

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if _session_is_live(request):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(
        request, "login.html", {"error": None, "logged_in": False}
    )

@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    expected = USERS.get(username)
    if expected is not None and expected == password:
        request.session["username"] = username
        request.session["last_active"] = time.time()
        return RedirectResponse(url="/dashboard", status_code=302)

    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid username or password.", "logged_in": False},
        status_code=401,
    )

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    if not _session_is_live(request):
        return RedirectResponse(url="/login", status_code=302)
    _touch(request)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"username": request.session.get("username"), "logged_in": True},
    )

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)
