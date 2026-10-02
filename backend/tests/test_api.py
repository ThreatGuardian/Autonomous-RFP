import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def wait_for(client, rfp_id, statuses=("review", "failed"), timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/rfps/{rfp_id}").json()
        if r["status"] in statuses and not r["running"]:
            return r
        time.sleep(0.2)
    raise AssertionError(f"RFP {rfp_id} did not finish: {r['status']}")


def test_full_workflow():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        # Two RFPs submitted together are processed in parallel.
        a = client.post("/api/rfps", json={"text": (SAMPLES / "03_harbourline_dubai.txt").read_text(), "filename": "dubai.txt"})
        files = [("files", ("kaveri.txt", (SAMPLES / "02_kaveri_network_upgrade.txt").read_bytes(), "text/plain"))]
        b = client.post("/api/rfps/upload", files=files)
        assert a.status_code == 201 and b.status_code == 201
        rfp = wait_for(client, a.json()["id"])
        other = wait_for(client, b.json()[0]["id"])
        assert rfp["status"] == "review" and other["status"] == "review"
        assert [s["stage"] for s in rfp["stages"]] == ["intake", "costing", "compliance", "strategy", "localisation", "drafting"]
        assert all(s["status"] == "completed" and s["log"] for s in rfp["stages"])
        assert rfp["currency"] == "AED" and rfp["proposal"]["documents"]["quotation"].endswith(".pdf")

        pdf = client.get(f"/api/rfps/{rfp['id']}/documents/quotation")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

        # Reviewer override triggers a re-price from costing and a new version.
        r = client.post(f"/api/rfps/{rfp['id']}/reprice",
                        json={"lines": {"1": {"unit_price": 80000, "clear_bundle": True}}, "note": "Hold at 80k"})
        assert r.status_code == 200
        rfp2 = wait_for(client, rfp["id"])
        line = rfp2["pricing"]["strategy"]["lines"][0]
        assert line["unit_price"] == 80000 and line["bundle"] is None and line["strategy"] == "Reviewer override"
        assert rfp2["proposal"]["version"] == 2
        assert [s["stage"] for s in rfp2["stages"]].count("intake") == 1

        ok = client.post(f"/api/rfps/{rfp['id']}/approve", json={"actor": "Priya Shah", "note": "Approved for sending"})
        assert ok.status_code == 200
        final = client.get(f"/api/rfps/{rfp['id']}").json()
        assert final["status"] == "approved" and [e["action"] for e in final["events"]] == ["repriced", "approved"]
        assert client.post(f"/api/rfps/{rfp['id']}/approve", json={}).status_code == 409

        dash = client.get("/api/dashboard").json()
        assert dash["counts"]["approved"] >= 1 and dash["strategy_mix"]


def test_reference_endpoints():
    with TestClient(app) as client:
        assert len(client.get("/api/catalog/products").json()) == 52
        hits = client.get("/api/catalog/products", params={"q": "poe switch"}).json()
        assert hits[0]["category"] == "network_switch"
        offers = client.get("/api/market/offers", params={"sku": "MSS-LT-101", "country": "IN", "quantity": 10}).json()
        assert offers["offers"] and "vs_cost_pct" in offers["offers"][0]
        tax = client.post("/api/finance/tax-preview", json={"country": "US", "region": "Texas", "incoterm": "DDP"}).json()
        assert tax["treatments"]["goods_standard"]["rate_pct"] == 6.25
        assert client.get("/api/models").json()["win_model"]["metrics"]["holdout_auc"] > 0.7
        assert client.get("/api/knowledge/search", params={"q": "ISO 27001"}).json()["evidence"]
        samples = client.get("/api/rfps/samples").json()
        assert sum(s["kind"] == "text" for s in samples) == 5
        assert [s["filename"] for s in samples if s["kind"] == "file"] == ["08_godavari_smart_city_tender.pdf",
                                                                           "09_konkan_university_rfp.docx",
                                                                               "10_des_pune_university_rfp.pdf"]
        assert client.get("/market-api/v1/competitors").status_code == 401
