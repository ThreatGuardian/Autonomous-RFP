from pathlib import Path

from pypdf import PdfReader

from app.agents.base import PipelineContext, StageLog
from app.agents.drafting_agent import ProposalDraftingAgent
from app.agents.localisation_agent import LocalisationAgent
from app.agents.parser_agent import RfpParserAgent
from app.agents.pricing_agent import InternalPricingAgent
from app.agents.strategy_agent import CompetitiveStrategyAgent
from app.db.seed import load_json
from app.services.pdf_renderer import render_memo, render_quotation

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def pipeline(name):
    ctx = PipelineContext(42, "T", (SAMPLES / name).read_text(), load_json("company.json"))
    for agent in (RfpParserAgent(), InternalPricingAgent(), CompetitiveStrategyAgent(), LocalisationAgent(), ProposalDraftingAgent()):
        ctx.messages[agent.produces] = agent.run(ctx, StageLog())
    return ctx


def test_proposal_is_grounded_and_complete():
    ctx = pipeline("02_kaveri_network_upgrade.txt")
    p = ctx.messages["proposal"]
    assert p.quote_number.endswith("-0042")
    assert p.salutation == "Dear Dr. Ravi Menon,"
    assert any("hospital" in para.lower() for para in p.cover_letter)  # retrieved case study
    iso = next(r for r in p.compliance if "27001" in r.requirement)
    assert iso.status == "Complies" and any("27001" in e.text for e in iso.evidence)
    assert all(q["passages"] is not None for q in p.retrieval_log) and len(p.retrieval_log) >= 4
    assert [m.label for m in p.milestones][:3] == ["Purchase order", "Staging complete", "Delivered to site"]


def test_pdfs_render_with_correct_totals(tmp_path):
    ctx = pipeline("03_harbourline_dubai.txt")
    m = ctx.messages
    q = render_quotation(tmp_path / "q.pdf", company=ctx.company, parsed=m["parsed"], strat=m["strategy"],
                         loc=m["localisation"], proposal=m["proposal"], approved=True)
    memo = render_memo(tmp_path / "m.pdf", company=ctx.company, parsed=m["parsed"], strat=m["strategy"],
                       loc=m["localisation"], proposal=m["proposal"], approval=None)
    text = "\n".join(page.extract_text() for page in PdfReader(q).pages)
    assert f"{m['localisation'].grand_total:,.2f}" in text
    assert "Requirement compliance" in text and "Harbourline Freight LLC" in text
    assert "Landed cost" not in text  # costs never leak into the client document
    memo_text = "\n".join(page.extract_text() for page in PdfReader(memo).pages)
    assert "CONFIDENTIAL" in memo_text and "Rationale by line" in memo_text
