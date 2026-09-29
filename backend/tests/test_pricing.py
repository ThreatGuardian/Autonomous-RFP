from pathlib import Path

import httpx
import pytest

from app.agents.base import PipelineContext, StageLog
from app.agents.localisation_agent import LocalisationAgent
from app.agents.parser_agent import RfpParserAgent
from app.agents.pricing_agent import InternalPricingAgent
from app.agents.strategy_agent import CompetitiveStrategyAgent
from app.db.seed import load_json
from app.market.service import market_app, offers_for
from app.pricing.strategy import LIST_PRICE, MANUAL, VALUE_DIFFERENTIATION
from app.services.market_client import InProcessTransport, MarketClient, MarketUnavailable

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def run(name, overrides=None, market=None):
    ctx = PipelineContext(1, "T", (SAMPLES / name).read_text(), load_json("company.json"), overrides=overrides or {})
    for agent in (RfpParserAgent(), InternalPricingAgent(), CompetitiveStrategyAgent(market), LocalisationAgent()):
        ctx.messages[agent.produces] = agent.run(ctx, StageLog())
    return ctx


class DownMarket(MarketClient):
    def batch_offers(self, country, items, retries=2):
        raise MarketUnavailable("simulated outage")


def test_market_api_requires_key():
    client = httpx.Client(transport=InProcessTransport(market_app), base_url="http://m")
    assert client.get("/v1/competitors").status_code == 401
    assert client.get("/v1/competitors", headers={"X-Api-Key": "demo-market-key"}).status_code == 200


def test_market_prices_are_deterministic_and_regional():
    a = offers_for("DL-5450-I5-16-512", 10, "IN")
    b = offers_for("DL-5450-I5-16-512", 10, "IN")
    assert [o.unit_price for o in a] == [o.unit_price for o in b]
    assert all(o.competitor_id != "euronet" for o in a)
    assert any(o.competitor_id == "euronet" for o in offers_for("DL-P3680-I9-A2000", 1, "DE"))


def test_prices_never_breach_floor_and_below_cost_triggers_value_differentiation():
    ctx = run("03_harbourline_dubai.txt")
    lines = ctx.messages["strategy"].lines
    for line in lines:
        assert line.unit_price >= line.floor_price - 0.01
        assert line.margin > 0
    laptop = next(l for l in lines if l.sku == "MSS-LT-101")
    assert laptop.market.best.unit_price_base < laptop.unit_cost
    assert laptop.strategy == VALUE_DIFFERENTIATION and laptop.bundle is not None
    assert any("price matching was rejected" in r for r in laptop.rationale)
    match = next(s for s in laptop.scenarios if s.label == "Match best competitor")
    assert not match.feasible


def test_reviewer_override_is_respected_and_flagged():
    ctx = run("03_harbourline_dubai.txt", overrides={"lines": {"1": {"unit_price": 60000, "bundle": None}}})
    line = ctx.messages["strategy"].lines[0]
    assert line.strategy == MANUAL and line.unit_price == 60000 and line.bundle is None
    assert "Below margin floor" in line.flags and "Loss-making price" in line.flags


def test_market_outage_degrades_to_standard_pricing():
    ctx = run("02_kaveri_network_upgrade.txt", market=DownMarket())
    strategy = ctx.messages["strategy"]
    assert not strategy.market_available
    assert all(l.strategy == LIST_PRICE and l.unit_price == l.standard_price for l in strategy.lines)


def test_localisation_totals_reconcile():
    ctx = run("03_harbourline_dubai.txt")
    loc = ctx.messages["localisation"]
    assert loc.currency == "AED"
    assert loc.subtotal == pytest.approx(sum(l.net for l in loc.lines), abs=0.05)
    assert loc.grand_total == pytest.approx(loc.subtotal + loc.tax_total, abs=0.05)
    goods = next(l for l in loc.lines if l.sku == "MSS-LT-101")
    licence = next(l for l in loc.lines if l.sku == "MSS-SW-121")
    assert goods.tax_rate_pct == 5 and licence.tax_regime == "Reverse charge"
    assert loc.fx_buffer_pct == 1.5


def test_domestic_quote_uses_cgst_sgst():
    loc = run("01_sahyadri_campus_refresh.txt").messages["localisation"]
    assert {t.name for t in loc.tax_breakdown} == {"CGST", "SGST"}
    assert loc.fx_buffer_pct == 0 and loc.currency == "INR"
