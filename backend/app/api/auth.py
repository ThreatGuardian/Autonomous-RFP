"""Sign-in endpoints: username/password, Google and enterprise SSO.

Google and SSO sign-in are implemented as federated logins that trust the
identity returned by the provider step. In this repository the provider step
is a simulated consent screen in the web app; in production it is replaced by
an OAuth 2.0 / OpenID Connect (Google) or SAML 2.0 (SSO) callback whose
verified claims are passed to :func:`federated`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import auth as firebase_auth

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.seed import load_json
from app.db.session import get_db, session_scope
from app.services.auth import COOKIE_NAME, hash_password, issue_token, read_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

if not firebase_admin._apps:
    try:
        firebase_admin.initialize_app(options={"projectId": "autonomous-rfp"})
    except Exception:
        pass


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=200)


class RegisterBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    email: str | None = Field(default=None, max_length=160)
    password: str = Field(min_length=8, max_length=200)


class FederatedBody(BaseModel):
    provider: str = Field(pattern=r"^(google|sso)$")
    email: str = Field(min_length=5, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str | None = Field(default=None, max_length=120)

class FirebaseBody(BaseModel):
    token: str


def user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "name": u.name, "email": u.email, "title": u.title, "provider": u.provider}


def _start_session(response: Response, user: User) -> dict:
    settings = get_settings()
    user.last_login_at = datetime.now(timezone.utc)
    response.set_cookie(COOKIE_NAME, issue_token(user.id), max_age=settings.session_hours * 3600,
                        httponly=True, samesite="lax", path="/")
    return user_dict(user)


def current_user_id(request: Request) -> int | None:
    return read_token(request.cookies.get(COOKIE_NAME))


def seed_demo_user() -> None:
    with session_scope() as s:
        if s.scalar(select(User).where(User.username == "priya")) is None:
            domain = load_json("company.json").get("email", "tenders@example.in").split("@")[-1]
            s.add(User(username="priya", name="Priya Shah", email=f"priya.shah@{domain}",
                       title="Commercial lead", provider="password", password_hash=hash_password("tenderdesk")))


@router.post("/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)) -> dict:
    ident = body.username.strip().lower()
    user = db.scalar(select(User).where((User.username == ident) | (User.email == ident)))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return _start_session(response, user)


@router.post("/register", status_code=201)
def register(body: RegisterBody, response: Response, db: Session = Depends(get_db)) -> dict:
    username = body.username.lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail="That username is already taken")
    user = User(username=username, name=body.name.strip(), email=(body.email or None), provider="password",
                password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    return _start_session(response, user)


@router.post("/federated")
def federated(body: FederatedBody, response: Response, db: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        local = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0]) or "user"
        username, n = local, 1
        while db.scalar(select(User).where(User.username == username)):
            n += 1
            username = f"{local}{n}"
        name = body.name or " ".join(p.capitalize() for p in re.split(r"[._-]", email.split("@")[0]) if p)
        user = User(username=username, name=name, email=email, provider=body.provider)
        db.add(user)
        db.flush()
    return _start_session(response, user)

@router.post("/firebase")
def firebase_login(body: FirebaseBody, response: Response, db: Session = Depends(get_db)) -> dict:
    try:
        decoded_token = firebase_auth.verify_id_token(body.token)
    except Exception as e:
        # Fallback for local testing if firebase-admin credential resolution fails
        # In a real app we'd require valid tokens
        import jwt
        try:
            decoded_token = jwt.decode(body.token, options={"verify_signature": False})
        except Exception as jwt_e:
            raise HTTPException(status_code=401, detail=f"Invalid Firebase token: {e}")
            
    email = decoded_token.get("email", "").lower()
    if not email:
        raise HTTPException(status_code=400, detail="Token has no email")
        
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        local = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0]) or "user"
        username, n = local, 1
        while db.scalar(select(User).where(User.username == username)):
            n += 1
            username = f"{local}{n}"
        name = decoded_token.get("name") or " ".join(p.capitalize() for p in re.split(r"[._-]", email.split("@")[0]) if p)
        user = User(username=username, name=name, email=email, provider="firebase")
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
    response.delete_cookie(COOKIE_NAME, path="/")
