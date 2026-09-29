"""Pipeline orchestrator.

Runs the five agents in dependency order for each RFP on a worker pool, so
several RFPs are processed in parallel. Every agent execution is persisted as a
:class:`StageRun` (status, timing, summary, decision log) and every produced
message is persisted on the RFP, which lets a reviewer's change re-run only
the downstream stages.

Status lifecycle::

    queued → processing → review → approved | rejected
                   ↘ failed        ↖ (reprice / reopen)
"""

from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select

from app.agents.base import Agent, PipelineContext, StageLog
from app.agents.drafting_agent import ProposalDraftingAgent
from app.agents.localisation_agent import LocalisationAgent
from app.agents.messages import CompetitiveAnalysis, InternalPricing, Localisation, ParsedRfp, Proposal
from app.agents.parser_agent import RfpParserAgent
from app.agents.pricing_agent import InternalPricingAgent
from app.agents.strategy_agent import CompetitiveStrategyAgent
from app.config import get_settings
from app.db.models import ApprovalEvent, Rfp, StageRun
from app.db.seed import load_json
from app.db.session import session_scope
from app.services.pdf_renderer import document_dir, render_memo, render_quotation

log = logging.getLogger("tenderdesk.pipeline")

STAGES = ["intake", "costing", "strategy", "localisation", "drafting"]
MESSAGE_TYPES: dict[str, type[BaseModel]] = {
    "parsed": ParsedRfp, "costing": InternalPricing, "strategy": CompetitiveAnalysis,
    "localisation": Localisation, "proposal": Proposal,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_agents() -> list[Agent]:
    return [RfpParserAgent(), InternalPricingAgent(), CompetitiveStrategyAgent(), LocalisationAgent(),
            ProposalDraftingAgent(renderer=render_documents)]


def render_documents(ctx: PipelineContext, proposal: Proposal, approved: bool = False,
                     approval: dict | None = None) -> dict[str, str]:
    folder = document_dir(ctx.reference)
    stem = f"{proposal.quote_number}-v{proposal.version}"
    m = ctx.messages
    q = render_quotation(folder / f"{stem}-quotation.pdf", company=ctx.company, parsed=m["parsed"], strat=m["strategy"],
                         loc=m["localisation"], proposal=proposal, approved=approved)
    memo = render_memo(folder / f"{stem}-pricing-memo.pdf", company=ctx.company, parsed=m["parsed"], strat=m["strategy"],
                       loc=m["localisation"], proposal=proposal, approval=approval)
    return {"quotation": q.name, "memo": memo.name}


# --------------------------------------------------------------------------- persistence helpers


def _load_messages(rfp: Rfp) -> dict[str, BaseModel]:
    out: dict[str, BaseModel] = {}
    if rfp.parsed:
        out["parsed"] = ParsedRfp.model_validate(rfp.parsed)
    pricing = rfp.pricing or {}
    for key in ("costing", "strategy", "localisation"):
        if pricing.get(key):
            out[key] = MESSAGE_TYPES[key].model_validate(pricing[key])
    if rfp.proposal:
        out["proposal"] = Proposal.model_validate(rfp.proposal)
    return out


def _store_message(rfp: Rfp, key: str, message: BaseModel) -> None:
    data = message.model_dump(mode="json")
    if key == "parsed":
        rfp.parsed = data
        rfp.title = message.title[:240]  # type: ignore[attr-defined]
        rfp.client_name = message.client.name  # type: ignore[attr-defined]
        rfp.client_country = message.client.country  # type: ignore[attr-defined]
        rfp.currency = message.currency.code  # type: ignore[attr-defined]
        rfp.due_date = message.due_date  # type: ignore[attr-defined]
    elif key in ("costing", "strategy", "localisation"):
        rfp.pricing = {**(rfp.pricing or {}), key: data}
        if key == "strategy":
            rfp.margin_pct = message.margin_pct  # type: ignore[attr-defined]
            rfp.total_base = message.revenue  # type: ignore[attr-defined]
            counts = message.strategy_counts  # type: ignore[attr-defined]
            rfp.strategy_summary = max(counts, key=counts.get) if counts else None
        if key == "localisation":
            rfp.total_client = message.grand_total  # type: ignore[attr-defined]
    elif key == "proposal":
        rfp.proposal = data


def _clear_from(rfp: Rfp, stage: str) -> None:
    idx = STAGES.index(stage)
    if idx <= 0:
        rfp.parsed = None
    keep = {k: v for k, v in (rfp.pricing or {}).items() if STAGES.index(k) < idx}
    rfp.pricing = keep or None
    rfp.proposal = None


# --------------------------------------------------------------------------- orchestrator


class Orchestrator:
    def __init__(self, workers: int | None = None) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers or get_settings().pipeline_workers, thread_name_prefix="pipeline")
        self._active: dict[int, Future] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public

    def submit(self, rfp_id: int, from_stage: str = "intake") -> Future:
        with self._lock:
            running = self._active.get(rfp_id)
            if running and not running.done():
                return running
            with session_scope() as s:
                rfp = s.get(Rfp, rfp_id)
                if rfp is None:
                    raise KeyError(rfp_id)
                rfp.status = "queued"
                rfp.error = None
            fut = self._pool.submit(self._run_safe, rfp_id, from_stage)
            self._active[rfp_id] = fut
            return fut

    def is_running(self, rfp_id: int) -> bool:
        fut = self._active.get(rfp_id)
        return bool(fut and not fut.done())

    def recover(self) -> int:
        """Re-queue RFPs interrupted by a restart."""
        with session_scope() as s:
            ids = list(s.scalars(select(Rfp.id).where(Rfp.status.in_(["queued", "processing"]))))
        for rfp_id in ids:
            self.submit(rfp_id)
        return len(ids)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ execution

    def _run_safe(self, rfp_id: int, from_stage: str) -> None:
        try:
            self.run(rfp_id, from_stage)
        except Exception:  # already recorded on the RFP; keep the worker alive
            log.exception("Pipeline failed for RFP %s", rfp_id)

    def run(self, rfp_id: int, from_stage: str = "intake") -> None:
        company = load_json("company.json")
        with session_scope() as s:
            rfp = s.get(Rfp, rfp_id)
            assert rfp is not None
            rfp.status = "processing"
            _clear_from(rfp, from_stage)
            ctx = PipelineContext(rfp.id, rfp.reference, rfp.raw_text, company, overrides=dict(rfp.overrides or {}),
                                  messages=_load_messages(rfp))
        # Proposal version increments on every completed re-draft.
        with session_scope() as s:
            drafts = len(list(s.scalars(select(StageRun.id).where(
                StageRun.rfp_id == rfp_id, StageRun.stage == "drafting", StageRun.status == "completed"))))
        ctx.overrides["_version"] = drafts + 1

        agents = [a for a in build_agents() if STAGES.index(a.stage) >= STAGES.index(from_stage)]
        for agent in agents:
            with session_scope() as s:
                run = StageRun(rfp_id=rfp_id, stage=agent.stage, agent=agent.name, status="running")
                s.add(run)
                s.flush()
                run_id = run.id
            stage_log = StageLog()
            started = _now()
            try:
                message = agent.run(ctx, stage_log)
            except Exception as exc:
                stage_log.warn("Stage failed", error=str(exc), trace=traceback.format_exc(limit=4))
                with session_scope() as s:
                    run = s.get(StageRun, run_id)
                    run.status, run.finished_at = "failed", _now()
                    run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
                    run.summary, run.log = f"{type(exc).__name__}: {exc}", stage_log.entries
                    rfp = s.get(Rfp, rfp_id)
                    rfp.status, rfp.error = "failed", f"{agent.name} failed: {exc}"
                raise
            ctx.messages[agent.produces] = message
            with session_scope() as s:
                run = s.get(StageRun, run_id)
                run.status, run.finished_at = "completed", _now()
                run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
                run.summary, run.log = agent.summarize(message), stage_log.entries
                rfp = s.get(Rfp, rfp_id)
                _store_message(rfp, agent.produces, message)
        with session_scope() as s:
            rfp = s.get(Rfp, rfp_id)
            rfp.status = "review"

    # ------------------------------------------------------------------ approval workflow

    def finalize(self, rfp_id: int, actor: str, note: str | None) -> dict[str, str]:
        """Re-render documents without the draft watermark and with the approval record."""
        company = load_json("company.json")
        with session_scope() as s:
            rfp = s.get(Rfp, rfp_id)
            assert rfp is not None
            messages = _load_messages(rfp)
            ctx = PipelineContext(rfp.id, rfp.reference, rfp.raw_text, company, messages=messages)
            approval = {"status": "Approved", "actor": actor, "note": note, "at": _now().strftime("%d %b %Y %H:%M UTC")}
            proposal: Proposal = messages["proposal"]  # type: ignore[assignment]
            docs = render_documents(ctx, proposal, approved=True, approval=approval)
            proposal.documents = docs
            rfp.proposal = proposal.model_dump(mode="json")
            return docs


def document_path(reference: str, filename: str) -> Path:
    path = (document_dir(reference) / filename).resolve()
    if document_dir(reference).resolve() not in path.parents:
        raise FileNotFoundError(filename)
    return path


def record_event(rfp_id: int, action: str, actor: str, note: str | None, payload: dict[str, Any] | None = None) -> None:
    with session_scope() as s:
        s.add(ApprovalEvent(rfp_id=rfp_id, action=action, actor=actor or "Reviewer", note=note, payload=payload or {}))


orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global orchestrator
    if orchestrator is None:
        orchestrator = Orchestrator()
    return orchestrator
