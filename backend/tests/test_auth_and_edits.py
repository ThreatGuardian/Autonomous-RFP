import os
import time
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.config import get_settings
from app.main import app

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _wait(client, rfp_id, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/rfps/{rfp_id}").json()
        if r["status"] in ("review", "failed") and not r["running"]:
            return r
        time.sleep(0.2)
    raise AssertionError("timeout")


def test_session_required_and_sign_in_methods():
    os.environ["TD_REQUIRE_AUTH"] = "1"
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            assert client.get("/api/rfps").status_code == 401
            assert client.get("/api/health").status_code == 200
            assert client.post("/api/auth/login", json={"username": "priya", "password": "wrong"}).status_code == 401
            ok = client.post("/api/auth/login", json={"username": "priya", "password": "tenderdesk"})
            assert ok.status_code == 200 and ok.json()["name"] == "Priya Shah"
            assert client.get("/api/rfps").status_code == 200
            assert client.get("/api/auth/me").json()["username"] == "priya"
            client.post("/api/auth/logout")
            client.cookies.clear()
            assert client.get("/api/rfps").status_code == 401
            g = client.post("/api/auth/federated", json={"provider": "google", "email": "arjun.mehta@gmail.com"})
            assert g.status_code == 200 and g.json()["provider"] == "google" and g.json()["name"] == "Arjun Mehta"
            reg = client.post("/api/auth/register", json={"name": "Neha Rao", "username": "neha", "password": "s3cure-pass"})
            assert reg.status_code in (201, 409)
    finally:
        os.environ["TD_REQUIRE_AUTH"] = "0"
        get_settings.cache_clear()


def test_reviewer_edits_client_terms_and_added_lines():
    with TestClient(app) as client:
        created = client.post("/api/rfps", json={"text": (SAMPLES / "05_rheinland_engineering.txt").read_text()}).json()
        rfp = _wait(client, created["id"])
        assert rfp["pricing"]["localisation"]["tax_summary"].startswith("Zero-rated")  # DAP export
        n = len(rfp["pricing"]["strategy"]["lines"])
        body = {"incoterm": "DDP", "client": {"segment": "public"}, "add_lines": [{"sku": "MSS-PR-111", "quantity": 16}],
                "note": "Client confirmed DDP; add keyboards"}
        assert client.post(f"/api/rfps/{rfp['id']}/reprice", json=body).status_code == 200
        rfp2 = _wait(client, rfp["id"])
        loc = rfp2["pricing"]["localisation"]
        assert loc["tax_summary"] == "Destination taxes charged under DDP"
        assert any(t["name"] == "MwSt" and t["rate_pct"] == 19 for t in loc["tax_breakdown"])
        lines = rfp2["pricing"]["strategy"]["lines"]
        assert len(lines) == n + 1 and lines[-1]["sku"] == "MSS-PR-111" and lines[-1]["quantity"] == 16
        assert rfp2["parsed"]["client"]["segment"] == "public"
        added_no = lines[-1]["line_no"]
        # Removing the added line and resetting brings the original back.
        client.post(f"/api/rfps/{rfp['id']}/reprice", json={"remove_added": [added_no]})
        rfp3 = _wait(client, rfp["id"])
        assert len(rfp3["pricing"]["strategy"]["lines"]) == n
        report = client.get(f"/api/rfps/{rfp['id']}/documents/report")
        assert report.status_code == 200 and report.content[:4] == b"%PDF"


def test_bid_report_content(tmp_path):
    with TestClient(app) as client:
        created = client.post("/api/rfps", json={"text": (SAMPLES / "03_harbourline_dubai.txt").read_text()}).json()
        rfp = _wait(client, created["id"])
        from app.agents.orchestrator import document_path

        path = document_path(rfp["reference"], rfp["proposal"]["documents"]["report"])
        text = "\n".join(p.extract_text() for p in PdfReader(path).pages)
        for section in ("WIN PROBABILITY BY LINE", "MARGIN STRUCTURE", "KEY PRICING DECISIONS", "DELIVERY ROADMAP", "RISKS TO WEIGH"):
            assert section.replace(" ", "") in text.replace(" ", "").replace("\xa0", "")
        assert "Harbourline Freight LLC" in text
