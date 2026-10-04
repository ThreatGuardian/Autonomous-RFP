"""Security behaviour: token sign-in, account linking, brute force, CSRF, headers and hostile uploads."""

import io
import os
import zipfile

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.config import get_settings
from app.main import app


@pytest.fixture
def secured():
    os.environ["TD_REQUIRE_AUTH"] = "1"
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        os.environ["TD_REQUIRE_AUTH"] = "0"
        os.environ.pop("TD_FIREBASE_PROJECT_ID", None)
        get_settings.cache_clear()


def test_forged_firebase_tokens_are_rejected(secured):
    os.environ["TD_FIREBASE_PROJECT_ID"] = "tenderdesk-test"
    get_settings.cache_clear()
    unsigned = jwt.encode({"email": "priya.shah@example.com", "sub": "x", "aud": "tenderdesk-test"}, key=None, algorithm="none")
    hs256 = jwt.encode({"email": "priya.shah@example.com", "sub": "x"}, key="guess" * 8, algorithm="HS256")
    for token in (unsigned, hs256, "not-a-token-at-all-but-long-enough"):
        r = secured.post("/api/auth/firebase", json={"token": token})
        assert r.status_code == 401, r.text
    assert secured.get("/api/rfps").status_code == 401


def test_unverified_email_cannot_claim_an_existing_account(secured, monkeypatch):
    claims = {"sub": "attacker-uid", "email": "priya.shah@meridiansystems.in", "email_verified": False}
    monkeypatch.setattr(auth_api, "verify_firebase_token", lambda token: claims)
    from app.db.session import session_scope
    from app.db.models import User

    with session_scope() as s:
        email = s.query(User).filter(User.username == "priya").one().email
    claims["email"] = email
    assert secured.post("/api/auth/firebase", json={"token": "t" * 40}).status_code == 403
    claims["email_verified"] = True
    ok = secured.post("/api/auth/firebase", json={"token": "t" * 40})
    assert ok.status_code == 200 and ok.json()["username"] == "priya"


def test_login_is_throttled_after_repeated_failures(secured):
    auth_api.throttle.clear("user:throttle-me", "ip:testclient")
    codes = [secured.post("/api/auth/login", json={"username": "throttle-me", "password": "wrong"}).status_code
             for _ in range(auth_api.throttle.limit + 1)]
    assert codes[:auth_api.throttle.limit] == [401] * auth_api.throttle.limit
    assert codes[-1] == 429
    auth_api.throttle.clear("user:throttle-me", "ip:testclient")


def test_cross_origin_writes_are_refused_and_headers_set(secured):
    r = secured.post("/api/auth/login", json={"username": "priya", "password": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    h = secured.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["cache-control"] == "no-store"


def test_sign_up_can_be_disabled(secured):
    os.environ["TD_ALLOW_SIGNUP"] = "0"
    get_settings.cache_clear()
    try:
        r = secured.post("/api/auth/register", json={"name": "Mal Lory", "username": "mallory", "password": "long-enough-1"})
        assert r.status_code == 403
        assert secured.get("/api/auth/config").json()["signup"] is False
    finally:
        os.environ.pop("TD_ALLOW_SIGNUP", None)
        get_settings.cache_clear()


def test_production_refuses_insecure_defaults():
    os.environ["TD_ENV"] = "production"
    get_settings.cache_clear()
    try:
        problems = get_settings().check_production()
        assert any("TD_SECRET_KEY" in p for p in problems) and any("MARKET_API_KEY" in p for p in problems)
        assert get_settings().demo_user is False and get_settings().cookie_secure is True
    finally:
        os.environ.pop("TD_ENV")
        get_settings.cache_clear()


def test_hostile_uploads_are_rejected():
    from app.imports.catalogue import tally_to_table
    from app.services.documents import UnsupportedDocument, extract_text

    bomb = b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><ENVELOPE>&lol;</ENVELOPE>'
    with pytest.raises(ValueError):
        tally_to_table(bomb)
    with pytest.raises(UnsupportedDocument):
        extract_text("tender.pdf", b"MZ\x90\x00 not a pdf")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"\0" * (90 * 1024 * 1024))
    with pytest.raises(UnsupportedDocument):
        extract_text("tender.docx", buf.getvalue())


def test_upload_size_is_enforced_while_reading():
    with TestClient(app) as client:
        big = b"a" * (10 * 1024 * 1024 + 1)
        r = client.post("/api/rfps/upload", files={"files": ("big.txt", big, "text/plain")})
        assert r.status_code == 413
