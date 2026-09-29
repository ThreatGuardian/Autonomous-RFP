import pytest

from app.finance.currency import UnknownCurrency, fx
from app.finance.tax import TaxContext, assess

CATS = {"goods_standard", "software", "services"}


def ctx(country, region=None, eu=False, tax_id=None, incoterm=None):
    return TaxContext("IN", "Maharashtra", country, region, eu, tax_id, incoterm)


def test_fx_cross_rates_are_consistent():
    usd_aed = fx.quote("USD", "AED").rate
    assert fx.convert(100, "USD", "AED") == pytest.approx(100 * usd_aed)
    assert fx.quote("INR", "USD").rate * fx.quote("USD", "INR").rate == pytest.approx(1.0)
    with pytest.raises(UnknownCurrency):
        fx.quote("INR", "XYZ")


def test_india_intra_vs_inter_state():
    intra = assess(ctx("IN", "Maharashtra"), CATS).treatments["goods_standard"]
    inter = assess(ctx("IN", "Karnataka"), CATS).treatments["goods_standard"]
    assert [c["name"] for c in intra.components] == ["CGST", "SGST"] and intra.rate_pct == 18
    assert [c["name"] for c in inter.components] == ["IGST"] and inter.rate_pct == 18


def test_us_state_brackets_by_category():
    a = assess(ctx("US", "California", incoterm="DDP"), CATS)
    assert a.treatments["goods_standard"].rate_pct == 7.25
    assert a.treatments["software"].rate_pct == 0 and a.treatments["services"].rate_pct == 0


def test_export_zero_rated_unless_ddp():
    a = assess(ctx("DE", eu=True, tax_id="DE1", incoterm="DAP"), CATS)
    assert all(t.rate_pct == 0 for t in a.treatments.values())
    assert "19" in a.treatments["goods_standard"].note


def test_reverse_charge_for_b2b_services():
    a = assess(ctx("AE", tax_id="100384729100003", incoterm="DDP"), CATS)
    assert a.treatments["goods_standard"].rate_pct == 5
    assert a.treatments["software"].regime == "Reverse charge"


def test_multi_component_provincial_tax():
    a = assess(ctx("CA", "Quebec", incoterm="DDP"), CATS)
    assert a.treatments["goods_standard"].rate_pct == pytest.approx(14.975)
    assert len(a.treatments["goods_standard"].components) == 2
