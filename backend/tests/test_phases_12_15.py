"""Company data import, competitor intelligence, learning loop, response pack and the Data Care Corp trial."""

import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import DealHistory, PriceObservation, PriceVersion, Product, TrainingLabel
from app.db.session import session_scope
from app.imports import catalogue as cat_import
from app.imports.tabular import parse_months, parse_number
from app.intel import sources
from app.nlp.attributes import check
from app.pricing.warranty import months_by_category

BACKEND = Path(__file__).resolve().parents[1]
SAMPLES = BACKEND.parent / "samples"


# --------------------------------------------------------------------------- parsing helpers


def test_indian_number_and_duration_parsing():
    assert parse_number("₹1,23,456.50") == 123456.5
    assert parse_number("Rs. 45,000/Nos") == 45000
    assert parse_number("2.5 lakh") == 250000
    assert parse_number("1.2 crore") == 12000000
    assert parse_number("-") is None
    assert parse_months("3 years") == 36 and parse_months("18 months") == 18 and parse_months("24") == 24


def test_warranty_months_by_category():
    per = months_by_category("Graphics cards shall carry a warranty of three years and UPS units two years including "
                             "batteries. Keyboards, mice, headsets and webcams shall carry a warranty of one year.")
    assert per == {"component": 36, "power": 24, "peripheral": 12, "audio": 12}


def test_attribute_check_measures_and_words():
    class P:
        name, brand, description, keywords = "Mouse", "Dell", "Wired optical mouse", ["mouse"]
        specs = {"dpi": 800, "buttons": "3 buttons with scroll wheel", "design": "ambidextrous", "connectivity": "USB wired"}

    met, why = check("Resolution", "Minimum 1000 DPI", P)
    assert met is False and "800" in why
    assert check("Design", "Ambidextrous", P)[0] is True
    assert check("Type", "Wired USB optical mouse, 3 buttons with scroll wheel", P)[0] is True
    assert check("Colour", "Black with RGB lighting", P)[0] is None


# --------------------------------------------------------------------------- phase 12


CSV = (
    "Item Code,Part No.,Item Name,Make,Stock Group,HSN/SAC,GST %,Purchase Rate,Sales Rate,Closing Qty,Warranty\n"
    "MSS-PR-111,LG-MK540,Logitech MK540 Keyboard and Mouse Combo,Logitech,Accessories,8471,18%,\"₹2,500\",\"₹3,350\",210,1 year\n"
    ",ZB-HS-99,Zebronics Zeb-Rush USB Gaming Headset,Zebronics,Headphones,85183000,18,\"1,150\",\"1,590\",75,12 months\n"
    ",,,,,,,,,,\n"
    ",AB-99,Mystery Widget,Acme,,12,7,900,850,4,\n"
)


def test_catalogue_import_preview_and_commit():
    with session_scope() as db:
        plan = cat_import.preview(db, "stock.csv", CSV.encode())
        assert plan.mapping.fields["unit_cost"] == "Purchase Rate" and plan.mapping.fields["list_price"] == "Sales Rate"
        rows = {r.name: r for r in plan.rows}
        upd = rows["Logitech MK540 Keyboard and Mouse Combo"]
        assert upd.action == "update" and upd.changes["unit_cost"] == [2650.0, 2500.0] and upd.changes["stock_qty"][1] == 210
        new = rows["Zebronics Zeb-Rush USB Gaming Headset"]
        assert new.action == "create" and new.values["category"] == "audio" and new.values["hsn"] == "85183000"
        odd = rows["Mystery Widget"]
        messages = " ".join(i["message"] for i in odd.issues)
        assert "below cost" in messages and "HSN" in messages and "standard slab" in messages
        batch = cat_import.commit(db, plan)
        assert batch.updated == 1 and batch.created >= 1
    with session_scope() as db:
        p = db.scalar(select(Product).where(Product.sku == "MSS-PR-111"))
        assert p.unit_cost == 2500 and p.hsn == "8471"
        versions = list(db.scalars(select(PriceVersion).where(PriceVersion.sku == "MSS-PR-111")))
        assert versions and versions[-1].unit_cost == 2500 and versions[-1].batch_id == batch.id
        assert db.scalar(select(Product).where(Product.mpn == "ZB-HS-99")).category == "audio"


TALLY = """<ENVELOPE><BODY><IMPORTDATA><REQUESTDATA><TALLYMESSAGE>
<STOCKITEM NAME="HP 150 Wired Mouse" RESERVEDNAME="">
 <PARENT>Computer Accessories</PARENT><BASEUNITS>Nos</BASEUNITS><OPENINGBALANCE>120 Nos</OPENINGBALANCE>
 <OPENINGRATE>310/Nos</OPENINGRATE><GSTDETAILS.LIST><HSNCODE>84716060</HSNCODE>
 <STATEWISEDETAILS.LIST><RATEDETAILS.LIST><GSTRATEDUTYHEAD>Integrated Tax</GSTRATEDUTYHEAD><GSTRATE>18</GSTRATE>
 </RATEDETAILS.LIST></STATEWISEDETAILS.LIST></GSTDETAILS.LIST>
 <STANDARDPRICELIST.LIST><RATE>449/Nos</RATE></STANDARDPRICELIST.LIST>
</STOCKITEM></TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"""


def test_tally_stock_item_import():
    with session_scope() as db:
        plan = cat_import.preview(db, "Master.xml", TALLY.encode())
        assert plan.format == "tally"
        row = plan.rows[0]
        assert row.action == "create" and row.values["unit_cost"] == 310 and row.values["list_price"] == 449
        assert row.values["stock_qty"] == 120 and row.values["gst_rate_pct"] == 18 and row.values["category"] == "peripheral"


def test_import_api_round_trip():
    from app.main import app

    with TestClient(app) as client:
        prev = client.post("/api/catalog/import/preview",
                           files={"file": ("prices.csv", b"SKU,Cost,List Price\nMSS-PR-112,5700,7300\n", "text/csv")}).json()
        assert prev["counts"]["update"] == 1
        done = client.post("/api/catalog/import/commit", json={"token": prev["token"]}).json()
        assert done["updated"] == 1
        assert client.post("/api/catalog/import/commit", json={"token": prev["token"]}).status_code == 410
        hist = client.get("/api/catalog/products/MSS-PR-112/history").json()
        assert hist[-1]["unit_cost"] == 5700 and "Import" in hist[-1]["source"]
        assert client.get("/api/catalog/imports").json()[0]["filename"] == "prices.csv"


# --------------------------------------------------------------------------- phase 13


def test_quote_and_award_adapters_merge_into_market_view():
    today = date.today()
    quotes = ("Date,Seller,Part Number,Product,Qty,Unit Price,Source,URL\n"
              f"{(today - timedelta(days=5)).isoformat()},Apex Distributors,DL-P2425H,Dell Pro 24,50,\"11,200\",Distributor quote,q-1\n"
              f"{(today - timedelta(days=40)).isoformat()},Lamington Traders,DL-P2425H,Dell Pro 24,20,11900,Phone quote,\n"
              f"{(today - timedelta(days=400)).isoformat()},Old Seller,DL-P2425H,Dell Pro 24,20,9000,Phone quote,\n")
    awards = ("Award Date,Awarded To,Item Description,Qty,L1 Unit Price,Portal,Buyer\n"
              f"{(today - timedelta(days=30)).strftime('%d/%m/%Y')},Meridian Systems,Dell Pro 24 Monitor P2425H,40,11000,GeM,College\n"
              f"{(today - timedelta(days=20)).strftime('%d/%m/%Y')},Shree Computers,Dell Pro 24 Monitor P2425H,40,11350,GeM,College\n")
    with session_scope() as db:
        q = sources.ingest_table(db, "quotes", "quotes.csv", quotes.encode())
        a = sources.ingest_table(db, "awards", "awards.csv", awards.encode())
        assert q["added"] == 3 and a["added"] == 1 and a["skipped"] == 1  # our own award is not a competitor price
    feed = {"DL-P2425H": [{"competitor_id": "apex", "competitor": "Apex Distributors", "positioning": "x", "mpn": "DL-P2425H",
                            "unit_price": 12000.0, "currency": "INR", "warranty_months": 12, "lead_time_days": 7,
                            "in_stock": True, "reliability": 0.82, "observed_at": (today - timedelta(days=10)).isoformat()}]}
    policy = {"observation_max_age_days": 180, "observation_source_reliability": {"quotes": 0.9, "awards": 0.88}}
    with session_scope() as db:
        view, used = sources.market_view(db, [("DL-P2425H", 50)], feed, policy)
    offers = {o["competitor"]: o for o in view["DL-P2425H"]}
    assert offers["Apex Distributors"]["unit_price"] == 11200 and offers["Apex Distributors"]["source"] == "Distributor quote"
    assert "Lamington Traders" in offers and "Old Seller" not in offers  # older than the freshness window
    assert offers["Shree Computers"]["source"].startswith("GeM award")
    assert used["quotes"] >= 2 and used["awards"] == 1


def test_web_page_price_extraction():
    jsonld = ('<html><head><title>x</title><script type="application/ld+json">{"@type":"Product","name":"Dell Pro 24 '
              'Monitor P2425H","offers":{"@type":"Offer","price":"12499.00","priceCurrency":"INR"}}</script></head></html>')
    assert sources.extract_web_price(jsonld) == {"name": "Dell Pro 24 Monitor P2425H", "price": 12499.0, "currency": "INR",
                                                 "method": "schema.org offer"}
    meta = '<meta property="og:title" content="HP ProBook 440"><meta property="product:price:amount" content="71,900">'
    assert sources.extract_web_price(meta)["price"] == 71900
    text = "<html><body><h1>Logitech C920</h1><span>Deal price: ₹ 6,495</span></body></html>"
    assert sources.extract_web_price(text)["price"] == 6495


# --------------------------------------------------------------------------- phase 14


def test_labels_retrain_and_outcomes():
    from app.main import app
    from app.ml.registry import RETRAIN_EVERY, registry
    from tests.test_api import wait_for

    with TestClient(app) as client:
        text = (SAMPLES / "02_kaveri_network_upgrade.txt").read_text()
        rid = client.post("/api/rfps", json={"text": text}).json()["id"]
        wait_for(client, rid)
        detail = client.get(f"/api/rfps/{rid}").json()
        reqs = detail["parsed"]["requirements"]
        before = registry.clause_classifier().metrics.get("real_labels", 0)
        labelled = 0
        for r in reqs:
            new_type = "warranty_support" if r["type"] != "warranty_support" else "delivery"
            resp = client.post(f"/api/rfps/{rid}/labels", json={"requirement_id": r["id"], "type": new_type})
            assert resp.status_code == 200
            labelled += 1
            if labelled >= RETRAIN_EVERY:
                break
        assert client.post(f"/api/rfps/{rid}/labels", json={"requirement_id": reqs[0]["id"], "type": "nonsense"}).status_code == 422
        with session_scope() as db:
            assert len(list(db.scalars(select(TrainingLabel).where(TrainingLabel.rfp_id == rid)))) == labelled
        # Enough new labels arrived: the next use retrains with them.
        assert registry.clause_classifier().metrics["real_labels"] >= before + labelled

        out = client.post(f"/api/rfps/{rid}/outcome", json={"result": "lost", "winning_total": 1000000, "winner": "Apex"}).json()
        assert out["outcome"]["result"] == "lost"
        client.post(f"/api/rfps/{rid}/outcome", json={"result": "won"})
        with session_scope() as db:
            rows = list(db.scalars(select(DealHistory).where(DealHistory.rfp_id == rid)))
            assert len(rows) == 1 and rows[0].won and rows[0].source == "outcome"
        status = client.get("/api/learning/status").json()
        assert status["labels"]["clause"] >= labelled and status["outcomes"]["won"] >= 1
        ev = client.get("/api/learning/evaluate").json()
        assert ev["win"]["outcomes"] >= 1 and "status" in ev["clause"]
    # These labels were deliberately wrong; remove them so later tests use the clean model.
    with session_scope() as db:
        for t in db.scalars(select(TrainingLabel).where(TrainingLabel.rfp_id == rid)):
            db.delete(t)
        for d in db.scalars(select(DealHistory).where(DealHistory.rfp_id == rid)):
            db.delete(d)
    registry.forget("clause-classifier")
    registry.forget("win-probability")


# --------------------------------------------------------------------------- phase 15


def test_submission_pack_api():
    from app.main import app
    from tests.test_api import wait_for

    with TestClient(app) as client:
        path = SAMPLES / "08_godavari_smart_city_tender.pdf"
        rid = client.post("/api/rfps/upload", files=[("files", (path.name, path.read_bytes(), "application/pdf"))]).json()[0]["id"]
        wait_for(client, rid, timeout=240)
        resp = client.get(f"/api/rfps/{rid}/pack")
        assert resp.status_code == 200 and resp.headers["content-type"] == "application/zip"
        names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
        for expected in ("00_Submission_index.pdf", "01_Technical_proposal.pdf", "01_Technical_proposal.docx",
                         "02_Compliance_statement.pdf", "03_Financial_bid.pdf", "04_OEM_authorisation_requests.docx"):
            assert expected in names


# --------------------------------------------------------------------------- Data Care Corp trial

TRIAL = r"""
import json, sys, zipfile
from pathlib import Path
from app.db.seed import seed_all, load_json
seed_all()
from app.agents.base import PipelineContext, StageLog
from app.agents.orchestrator import build_agents
from app.services.documents import extract_text
from app.pack.builder import build_pack
p = Path(sys.argv[1])
ctx = PipelineContext(1, "T-1", extract_text(p.name, p.read_bytes()), load_json("company.json"), source_filename=p.name, source_path=p)
for a in build_agents():
    ctx.messages[a.produces] = a.run(ctx, StageLog())
m = ctx.messages
z = build_pack(Path(sys.argv[2]), company=ctx.company, parsed=m["parsed"], costing=m["costing"], strategy=m["strategy"],
               compliance=m["compliance"], proposal=m["proposal"], existing={})
print(json.dumps({
    "company": ctx.company["short_name"], "client": m["parsed"].client.name, "pages": m["parsed"].document.pages,
    "lines": [[l.quantity, l.category, l.selected_sku, l.status] for l in m["parsed"].line_items],
    "rule": m["strategy"].award.rule, "rank": m["strategy"].award.rank, "margin": m["strategy"].margin_pct,
    "sources": sorted({o.source for l in m["strategy"].lines for o in l.market.offers}),
    "recommendation": m["compliance"].recommendation, "met": [m["compliance"].mandatory_met, m["compliance"].mandatory_total],
    "quote": m["proposal"].quote_number, "pack": zipfile.ZipFile(z).namelist(),
}))
"""


def test_data_care_corp_answers_des_pune_university_rfp():
    with tempfile.TemporaryDirectory() as var:
        env = {**os.environ, "TD_COMPANY": "datacare", "TD_VAR_DIR": var, "TD_FX_MODE": "offline", "PYTHONPATH": str(BACKEND)}
        out = subprocess.run([sys.executable, "-c", TRIAL, str(SAMPLES / "10_des_pune_university_rfp.pdf"), f"{var}/pack"],
                             env=env, cwd=BACKEND, capture_output=True, text=True, timeout=600)
        assert out.returncode == 0, out.stderr[-3000:]
        r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["company"] == "Data Care Corp" and r["client"] == "DES Pune University" and r["pages"] >= 10
    assert len(r["lines"]) == 10 and all(q == 50 and s == "matched" for q, _, _, s in r["lines"])
    cats = [c for _, c, _, _ in r["lines"]]
    assert cats == ["desktop", "monitor", "peripheral", "peripheral", "audio", "audio", "peripheral", "laptop", "component", "power"]
    assert r["lines"][3][2] == "DCC-PR-512"  # the 1000 DPI requirement rules out the 800 DPI mouse
    assert r["rule"] == "L1" and r["rank"] == 1 and r["margin"] > 5
    assert "Market feed" in r["sources"] and any("award" in s for s in r["sources"])
    assert r["recommendation"] == "Bid" and r["met"][0] == r["met"][1]
    assert r["quote"].startswith("DCC-Q-")
    assert "01_Technical_proposal.pdf" in r["pack"] and "04_OEM_authorisation_requests.docx" in r["pack"]
