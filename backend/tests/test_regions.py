"""Region selection: the user picks the client region; currency, tax and conventions follow."""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app import regions
from app.db.models import WorkspaceSetting
from app.db.session import session_scope
from app.finance.tax import TaxContext, assess
from app.main import app

SAMPLE = (Path(__file__).resolve().parents[2] / "samples" / "04_cedar_valley_school.txt").read_text()


def _done(client: TestClient, rfp_id: int) -> dict:
    for _ in range(240):
        d = client.get(f"/api/rfps/{rfp_id}").json()
        if d["status"] in ("review", "failed"):
            return d
        time.sleep(0.25)
    raise AssertionError("timeout")


def test_region_catalogue_lists_currency_tax_and_conventions():
    rows = {r["code"]: r for r in regions.catalogue()}
    assert rows["GB"]["currency"] == "GBP" and rows["GB"]["area"] == "Europe" and "VAT" in rows["GB"]["tax"]
    assert "Texas" in rows["US"]["regions"]
    assert any("MSE" in c for c in rows["IN"]["conventions"]) and rows["DE"]["conventions"] == []


def test_selected_client_region_sets_currency_and_tax():
    with TestClient(app) as client:
        assert client.post("/api/rfps", json={"text": SAMPLE, "client_region": {"country": "ZZ"}}).status_code == 422
        assert client.post("/api/rfps", json={"text": SAMPLE, "client_region": {"country": "US", "region": "Atlantis"}}).status_code == 422
        r = client.post("/api/rfps", json={"text": SAMPLE, "client_region": {"country": "US", "region": "Texas"}}).json()
        loc = _done(client, r["id"])["pricing"]["localisation"]
        assert loc["currency"] == "USD"
        assert [(t["name"], t["rate_pct"]) for t in loc["tax_breakdown"]] == [("State sales tax", 6.25)]


def test_operating_region_makes_a_supply_domestic():
    with TestClient(app) as client:
        try:
            assert client.put("/api/workspace", json={"country": "GB"}).json()["operating_region"]["country"] == "GB"
            r = client.post("/api/rfps", json={"text": SAMPLE, "client_region": {"country": "GB"}}).json()
            loc = _done(client, r["id"])["pricing"]["localisation"]
            assert loc["tax_summary"] == "Domestic supply — VAT" and loc["currency"] == "GBP"
        finally:
            with session_scope() as s:
                row = s.get(WorkspaceSetting, regions.SETTING_KEY)
                if row is not None:
                    s.delete(row)


def test_india_specific_rules_only_apply_inside_india():
    assert regions.same_market("IN", "IN", "IN") and not regions.same_market("IN", "AE", "IN")
    export = assess(TaxContext("GB", None, "DE", None, True, None, "DAP"), {"goods_standard"})
    assert export.summary == "Zero-rated export, DAP terms"
    assert export.treatments["goods_standard"].components[0]["name"] == "Zero-rated export"
    from_india = assess(TaxContext("IN", "Maharashtra", "DE", None, True, None, "DAP"), {"goods_standard"})
    assert "LUT" in from_india.summary
