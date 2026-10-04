"""Sign-in endpoints.

Two ways to sign in:

* **Username and password** — accounts stored here, passwords hashed with PBKDF2-SHA256.
* **Google or SSO through Firebase Authentication** — the browser signs in with Firebase and
  sends the resulting ID token. The token's signature, audience, issuer and expiry are verified
  against Google's public keys. Unverifiable tokens are rejected; there is no fallback.

Either way the server then issues its own signed, HTTP-only session cookie.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.seed import load_json
from app.db.session import get_db, session_scope
from app.services.auth import COOKIE_NAME, hash_password, issue_token, read_token, verify_password

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

DEMO_USERNAME = "priya"
DEMO_PASSWORD = "tenderdesk"


# --------------------------------------------------------------------------- request bodies


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=200)


class RegisterBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    email: str | None = Field(default=None, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)


class FirebaseBody(BaseModel):
    token: str = Field(min_length=20, max_length=8192)


# --------------------------------------------------------------------------- brute-force protection


class LoginThrottle:
    """Refuse further attempts after repeated failures for one client address or account."""

    def __init__(self, limit: int = 8, window_s: int = 900) -> None:
        self.limit, self.window = limit, window_s
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return any(len(self._recent(k, now)) >= self.limit for k in keys)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                self._recent(k, now).append(now)

    def clear(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._failures.pop(k, None)


throttle = LoginThrottle()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# --------------------------------------------------------------------------- helpers


def user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "name": u.name, "email": u.email, "title": u.title, "provider": u.provider}


def _start_session(response: Response, user: User) -> dict:
    settings = get_settings()
    user.last_login_at = datetime.now(timezone.utc)
    response.set_cookie(COOKIE_NAME, issue_token(user.id), max_age=settings.session_hours * 3600,
                        httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")
    return user_dict(user)


def current_user_id(request: Request) -> int | None:
    return read_token(request.cookies.get(COOKIE_NAME))


def _unique_username(db: Session, email: str) -> str:
    local = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0].lower()) or "user"
    username, n = local, 1
    while db.scalar(select(User).where(User.username == username)):
        n += 1
        username = f"{local}{n}"
    return username


def seed_demo_user() -> None:
    """Create the demo account when enabled (development only)."""
    if not get_settings().demo_user:
        return
    with session_scope() as s:
        if s.scalar(select(User).where(User.username == DEMO_USERNAME)) is None:
            domain = load_json("company.json").get("email", "tenders@example.com").split("@")[-1]
            s.add(User(username=DEMO_USERNAME, name="Priya Shah", email=f"priya.shah@{domain}", title="Commercial lead",
                       provider="password", password_hash=hash_password(DEMO_PASSWORD)))


# --------------------------------------------------------------------------- Firebase


def verify_firebase_token(token: str) -> dict:
    """Verify a Firebase ID token and return its claims, or raise ``HTTPException``.

    Checks the RS256 signature against Google's published keys, the expiry, the audience
    (this project) and the issuer, as Firebase documents for third-party verification.
    """
    project = get_settings().firebase_project_id
    if not project:
        raise HTTPException(status_code=503, detail="Google and SSO sign-in are not configured on this server")
    from google.auth import exceptions as google_errors
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_firebase_token(token, google_requests.Request(), audience=project,
                                                clock_skew_in_seconds=10)
    except google_errors.TransportError as exc:
        log.warning("Could not fetch Google signing keys: %s", exc)
        raise HTTPException(status_code=503, detail="Sign-in could not be verified right now; try again") from exc
    except (ValueError, google_errors.GoogleAuthError) as exc:
        log.info("Rejected Firebase token: %s", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Sign-in could not be verified") from exc
    if claims.get("iss") != f"https://securetoken.google.com/{project}" or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Sign-in could not be verified")
    return dict(claims)


# --------------------------------------------------------------------------- endpoints


@router.get("/config")
def auth_config() -> dict:
    """Sign-in methods available on this server (public)."""
    s = get_settings()
    return {"signup": s.allow_signup, "firebase": bool(s.firebase_project_id), "demo": s.demo_user}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ident = body.username.strip().lower()
    keys = (f"ip:{_client_ip(request)}", f"user:{ident}")
    if throttle.blocked(*keys):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in a few minutes.")
    user = db.scalar(select(User).where((User.username == ident) | (User.email == ident)))
    if user is None or not verify_password(body.password, user.password_hash):
        throttle.fail(*keys)
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    throttle.clear(f"user:{ident}")
    return _start_session(response, user)


@router.post("/register", status_code=201)
def register(body: RegisterBody, response: Response, db: Session = Depends(get_db)) -> dict:
    if not get_settings().allow_signup:
        raise HTTPException(status_code=403, detail="New accounts are created by an administrator on this server")
    username = body.username.lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail="That username is already taken")
    email = body.email.strip().lower() if body.email else None
    if email and db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(username=username, name=body.name.strip(), email=email, provider="password",
                password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    return _start_session(response, user)


@router.post("/firebase")
def firebase_login(body: FirebaseBody, response: Response, db: Session = Depends(get_db)) -> dict:
    claims = verify_firebase_token(body.token)
    uid = str(claims["sub"])
    email = str(claims.get("email") or "").strip().lower()
    if not uid or not email:
        raise HTTPException(status_code=401, detail="The identity provider did not return an email address")
    verified = bool(claims.get("email_verified"))

    user = db.scalar(select(User).where(User.external_id == uid))
    if user is None:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            # Only a verified email may claim an existing account; otherwise anyone could
            # register the address with the provider and take the account over.
            if not verified:
                raise HTTPException(status_code=403, detail="Verify your email address with the provider before signing in")
            existing.external_id = uid
            user = existing
        else:
            if not get_settings().allow_signup:
                raise HTTPException(status_code=403, detail="No account exists for this email on this server")
            name = str(claims.get("name") or "").strip()[:120] or " ".join(
                p.capitalize() for p in re.split(r"[._-]", email.split("@")[0]) if p)
            user = User(username=_unique_username(db, email), name=name or email, email=email,
                        provider="firebase", external_id=uid)
            db.add(user)
            db.flush()
    return _start_session(response, user)


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)) -> dict | None:
    """The signed-in user, or ``null`` when there is no valid session."""
    uid = current_user_id(request)
    user = db.get(User, uid) if uid else None
    return user_dict(user) if user else None


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax")
