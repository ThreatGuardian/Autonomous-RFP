"""Long-tender understanding: layout, sections, key data, eligibility and the compliance review."""

from pathlib import Path

import pytest
from pypdf import PdfReader

from app.agents.base import PipelineContext, StageLog
from app.agents.orchestrator import build_agents
from app.db.seed import load_json
from app.nlp.layout import analyse_docx, analyse_pdf
from app.nlp.sections import build_sections
from app.nlp.tender import modality, parse_inr
from app.services.documents import extract_text

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
MUNICIPAL = SAMPLES / "08_godavari_smart_city_tender.pdf"
UNIVERSITY = SAMPLES / "09_konkan_university_rfp.docx"


@pytest.fixture(scope="module")
def municipal():
    return run_pipeline(MUNICIPAL)


@pytest.fixture(scope="module")
def university():
    return run_pipeline(UNIVERSITY)


def run_pipeline(path: Path) -> PipelineContext:
    ctx = PipelineContext(90, f"T-{path.stem[:2]}", extract_text(path.name, path.read_bytes()), load_json("company.json"),
                          source_filename=path.name, source_path=path)
    for agent in build_agents():
        ctx.messages[agent.produces] = agent.run(ctx, StageLog())
    return ctx


# --------------------------------------------------------------------------- layout and structure


def test_pdf_layout_keeps_pages_tables_and_drops_running_headers():
    layout = analyse_pdf(MUNICIPAL.read_bytes())
    assert layout.pages >= 10 and layout.removed_lines >= layout.pages * 2
    assert not any("Signature of bidder" in b.text or "Page 3 of" in b.text for b in layout.blocks)
    # The eligibility table continues across a page break and is stitched back into one table.
    rows = [b for b in layout.blocks if b.kind == "row" and b.cells and "blacklisted" in " ".join(b.cells)]
    first = next(b for b in layout.blocks if b.kind == "row" and b.cells and "Companies Act" in " ".join(b.cells))
    assert rows[0].table == first.table and rows[0].page > first.page


def test_section_tree_types_the_tender():
    layout = analyse_pdf(MUNICIPAL.read_bytes())
    sections, _ = build_sections(layout.blocks)
    kinds = {s.title: s.kind for s in sections}
    assert kinds["NOTICE INVITING TENDER"] == "notice"
    assert kinds["ELIGIBILITY AND PRE-QUALIFICATION CRITERIA"] == "eligibility"
    assert kinds["SCHEDULE OF REQUIREMENTS (BILL OF QUANTITIES)"] == "boq"
    assert kinds["Laptop"] == "technical"  # inherits from Section V
    assert kinds["Annexure-3: MANUFACTURER'S AUTHORISATION FORM"] == "forms"
    assert not any("GSTIN" in s.title or "Godavari" in s.title for s in sections)  # cover page is not a section

    docx_sections, _ = build_sections(analyse_docx(UNIVERSITY.read_bytes()).blocks)
    assert [s.title for s in docx_sections if s.level == 1][:3] == ["Invitation for Proposals", "Background and Objectives",
                                                                     "Pre-Qualification Criteria"]


def test_modality_and_amounts():
    assert modality("The bidder must hold a valid ISO 9001:2015 certificate.") == ("mandatory", "bidder")
    assert modality("Consortium bids are not permitted.")[0] == "mandatory"
    assert modality("The Purchaser reserves the right to reject any bid.") == ("information", "buyer")
    assert modality("Preference will be given to ENERGY STAR devices.")[0] == "desirable"
    assert parse_inr("Rs. 4,50,000 (Rupees four lakh fifty thousand only)") == 450000
    assert parse_inr("Rs. 2.25 crore") == 22_500_000
    assert parse_inr("at least Rs. 1.5 crore each") == 15_000_000


# --------------------------------------------------------------------------- parsing a 11-page municipal tender


def test_municipal_tender_key_data(municipal):
    p = municipal.messages["parsed"]
    d = p.document
    assert d.long_form and d.pages >= 10
    assert p.client_reference == "GVSCDCL/IT/2026-27/07" and p.client.city == "Nashik" and p.client.segment == "public"
    dates = {k.key: (k.date, k.time) for k in d.key_dates}
    assert dates["submission"] == ("2026-10-20", "15:00") and dates["prebid"] == ("2026-10-01", "11:00")
    assert p.due_date == "2026-10-20"
    facts = {f.key: f for f in d.facts}
    assert facts["emd"].amount == 450000 and "exempt" in facts["emd"].value
    assert facts["estimated_value"].amount == 22_500_000
    assert facts["performance_security"].amount == 5 and "10%" in facts["ld"].value
    assert d.evaluation.method == "L1" and p.terms.lowest_price_award
    assert p.terms.delivery_days == 45 and p.terms.payment_days == 30


def test_items_come_only_from_the_schedule_and_pick_up_linked_specs(municipal):
    p = municipal.messages["parsed"]
    assert len(p.line_items) == 11 and all(i.status == "matched" for i in p.line_items)
    by_line = {i.line_no: i for i in p.line_items}
    assert by_line[1].specs["form_factor"] == "tower" and by_line[1].quantity == 85
    assert by_line[7].selected_sku == "MSS-NW-507"  # 20 Gbps throughput from spec 5.7 rules out the 60F
    assert by_line[4].specs["uplink_gbps"] == 10
    specs = [r for r in p.requirements if r.source == "table" and r.category == "technical"]
    assert len(specs) >= 40 and all(r.line_no for r in specs)
    assert all(r.page for r in p.requirements if r.clause)


def test_eligibility_criteria_are_parsed(municipal):
    crit = {c.kind: c for c in municipal.messages["parsed"].document.eligibility}
    assert crit["turnover"].params["amount"] == 30_000_000 and crit["turnover"].params["financial_years"][0] == "2022-23"
    assert [o["pct_of_estimate"] for o in crit["similar_works"].params["options"]] == [40, 50, 80]
    assert crit["experience_years"].params["years"] == 5
    assert crit["certification"].params["standards"] == ["ISO 9001"]
    assert crit["local_presence"].params["places"] == ["Maharashtra"]


# --------------------------------------------------------------------------- compliance review


def test_municipal_compliance_review(municipal):
    report = municipal.messages["compliance"]
    costing = {l.line_no: l for l in municipal.messages["costing"].lines}
    # A 5-year warranty requirement is priced in, not given away.
    assert costing[1].warranty_months == 60 and costing[1].included_addons[0].code == "WTY-EXT24"
    assert costing[1].unit_cost > 56000
    checks = {c.kind: c for c in report.eligibility}
    assert checks["turnover"].status == "Meets" and checks["similar_works"].status == "Meets"
    assert checks["oem_authorisation"].status == "Documents required"
    assert checks["local_content"].status == "Needs review"
    uplink = next(i for i in report.items if i.text.startswith("Uplinks"))
    assert uplink.status == "Deviation" and "10G" in uplink.response
    assert report.recommendation == "Bid with clarifications"
    assert any("EMD" in b for b in report.benefits)
    assert any(r.title == "24x7 helpdesk commitment" for r in report.risks)
    assert any("Manufacturer's authorisation form – Cisco" == c.name for c in report.checklist)
    # Evidence shown to the client must be on topic.
    grounded = [i for i in report.items if i.evidence and i.category not in ("standards",)]
    assert all(len(i.evidence[0].text) > 20 for i in grounded)


def test_university_rfp_is_a_no_bid(university):
    p = university.messages["parsed"]
    assert p.document.evaluation.method == "QCBS" and p.terms.price_weight_pct == 30
    assert p.document.evaluation.min_technical_score == 70 and len(p.document.evaluation.criteria) == 6
    assert len(p.line_items) == 13  # "supplied at least 500 laptops" is an eligibility clause, not an item
    report = university.messages["compliance"]
    checks = {c.kind: c for c in report.eligibility}
    assert checks["supplied_quantity"].status == "Meets"  # 140 + 380 laptops to education clients
    assert checks["turnover"].status == "Meets" and "64%" in checks["turnover"].position
    assert checks["certification"].status == "Does not meet" and "20000" in checks["certification"].position
    assert report.recommendation == "Do not bid"


def test_compliance_statement_pdf(municipal, tmp_path):
    from app.services.compliance_renderer import render_compliance

    m = municipal.messages
    out = render_compliance(tmp_path / "c.pdf", company=municipal.company, parsed=m["parsed"], report=m["compliance"],
                            proposal=m["proposal"], approved=True)
    text = "\n".join(page.extract_text() for page in PdfReader(out).pages)
    assert "Statement of compliance" in text and "Statement of deviations" in text
    assert "Uplinks" in text and "GVSCDCL/IT/2026-27/07" in text
    assert "landed cost" not in text.lower()


def test_compliance_override_api():
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.test_api import wait_for

    with TestClient(app) as client:
        created = client.post("/api/rfps/samples/08_godavari_smart_city_tender.pdf")
        assert created.status_code == 201
        rfp = wait_for(client, created.json()[0]["id"])
        assert rfp["has_original"] and rfp["compliance"]["recommendation"] == "Bid with clarifications"
        item = next(i for i in rfp["compliance"]["items"] if i["text"].startswith("Uplinks"))
        r = client.post(f"/api/rfps/{rfp['id']}/compliance", json={
            "items": {item["id"]: {"status": "Complies with note", "response": "10G module offered."}}, "actor": "Tester"})
        assert r.status_code == 200
        rfp = wait_for(client, rfp["id"])
        edited = next(i for i in rfp["compliance"]["items"] if i["id"] == item["id"])
        assert edited["overridden"] and edited["status"] == "Complies with note"
        assert [s["stage"] for s in rfp["stages"]][-4:] == ["compliance", "strategy", "localisation", "drafting"]
        assert client.get(f"/api/rfps/{rfp['id']}/documents/compliance").status_code == 200
        assert client.get(f"/api/rfps/{rfp['id']}/original").headers["content-type"] == "application/pdf"
