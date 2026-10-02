"""Company data import, competitor intelligence, learning loop and submission pack endpoints."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.orchestrator import _load_messages, document_dir, document_path
from app.db.models import BidOutcome, ImportBatch, PriceObservation, PriceVersion, Product, Rfp
from app.db.seed import load_json
from app.db.session import get_db, session_scope
from app.imports import catalogue as cat_import
from app.intel import sources
from app.learning import loop
from app.rag.stores import invalidate_catalogue

router = APIRouter(prefix="/api", tags=["data"])
MAX_BYTES = 8 * 1024 * 1024

# Import plans wait here between preview and commit (per process, 30 minutes).
_plans: dict[str, tuple[float, cat_import.ImportPlan]] = {}
_plans_lock = threading.Lock()


async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 8 MB")
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty")
    return data


# --------------------------------------------------------------------------- phase 12: company data import


@router.post("/catalog/import/preview")
async def import_preview(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    data = await _read(file)
    try:
        plan = cat_import.preview(db, file.filename or "upload.csv", data)
    except Exception as exc:  # malformed spreadsheet or XML
        raise HTTPException(status_code=422, detail=f"Could not read the file: {exc}") from exc
    token = uuid.uuid4().hex
    with _plans_lock:
        now = time.time()
        for k in [k for k, (t, _) in _plans.items() if now - t > 1800]:
            _plans.pop(k, None)
        _plans[token] = (now, plan)
    return {"token": token, **plan.as_dict()}


class CommitBody(BaseModel):
    token: str
    actor: str = Field(default="Reviewer", max_length=80)


@router.post("/catalog/import/commit")
def import_commit(body: CommitBody) -> dict[str, Any]:
    with _plans_lock:
        entry = _plans.pop(body.token, None)
    if entry is None:
        raise HTTPException(status_code=410, detail="The preview has expired; upload the file again")
    with session_scope() as db:
        batch = cat_import.commit(db, entry[1], body.actor)
        db.flush()
        out = _batch(batch)
    invalidate_catalogue()
    return out


def _batch(b: ImportBatch) -> dict[str, Any]:
    return {"id": b.id, "filename": b.filename, "format": b.format, "rows": b.rows, "created": b.created,
            "updated": b.updated, "unchanged": b.unchanged, "skipped": b.skipped, "issues": len(b.issues or []),
            "actor": b.actor, "created_at": b.created_at.isoformat()}


@router.get("/catalog/imports")
def import_history(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [_batch(b) for b in db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(50))]


@router.get("/catalog/import/template", response_class=PlainTextResponse)
def import_template() -> str:
    return ("SKU,Part Number,Item Name,Brand,Category,HSN Code,GST Rate,Purchase Rate,Selling Price,Closing Stock,"
            "Lead Time Days,Warranty\n"
            "DCC-PR-599,EX-KB-100,Example USB Keyboard,Logitech,Keyboard,8471,18%,\"₹ 520\",\"₹ 690\",250,3,3 years\n")


@router.get("/catalog/products/{sku}/history")
def price_history(sku: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(PriceVersion).where(PriceVersion.sku == sku).order_by(PriceVersion.effective_from))
    return [{"unit_cost": v.unit_cost, "list_price": v.list_price, "stock_qty": v.stock_qty,
             "effective_from": v.effective_from.isoformat(), "source": v.source} for v in rows]


# --------------------------------------------------------------------------- phase 13: competitor intelligence


@router.get("/market/sources")
def market_sources(db: Session = Depends(get_db)) -> dict[str, Any]:
    stats = {a: {"label": label, "observations": 0, "latest": None, "competitors": 0} for a, label in sources.ADAPTERS.items()}
    for adapter, n, latest, comps in db.execute(
            select(PriceObservation.adapter, func.count(), func.max(PriceObservation.observed_on),
                   func.count(func.distinct(PriceObservation.competitor_id))).group_by(PriceObservation.adapter)):
        stats[adapter].update(observations=n, latest=latest.date().isoformat() if latest else None, competitors=comps)
    from app.market.service import market

    stats["feed"].update(observations=None, latest=date.today().isoformat(), competitors=len(market()["competitors"]))
    return {"adapters": stats}


@router.get("/market/observations")
def observations(mpn: str | None = None, sku: str | None = None, competitor: str | None = None,
                 adapter: str | None = None, limit: int = Query(default=200, le=1000),
                 db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(PriceObservation).order_by(PriceObservation.observed_on.desc())
    if sku:
        p = db.scalar(select(Product).where(Product.sku == sku))
        mpn = p.mpn if p else "-"
    if mpn:
        stmt = stmt.where(PriceObservation.mpn == mpn)
    if competitor:
        stmt = stmt.where(PriceObservation.competitor_id == competitor)
    if adapter:
        stmt = stmt.where(PriceObservation.adapter == adapter)
    return [sources.observation_dict(o) for o in db.scalars(stmt.limit(limit))]


@router.post("/market/observations/upload")
async def upload_observations(adapter: str = Form(..., pattern="^(quotes|awards)$"), file: UploadFile = File(...),
                              replace: bool = Form(default=False)) -> dict[str, Any]:
    data = await _read(file)
    with session_scope() as db:
        try:
            return sources.ingest_table(db, adapter, file.filename or "upload.csv", data, replace=replace)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not read the file: {exc}") from exc


class WebPageBody(BaseModel):
    competitor: str = Field(min_length=2, max_length=120)
    html: str = Field(min_length=20, max_length=3_000_000)
    url: str | None = Field(default=None, max_length=240)
    mpn: str | None = Field(default=None, max_length=48)
    observed_on: date | None = None


@router.post("/market/observations/web")
def web_observation(body: WebPageBody) -> dict[str, Any]:
    with session_scope() as db:
        return sources.ingest_web_page(db, body.competitor, body.html, body.url, body.observed_on, body.mpn)


@router.delete("/market/observations/{obs_id}", status_code=204)
def delete_observation(obs_id: int) -> None:
    with session_scope() as db:
        o = db.get(PriceObservation, obs_id)
        if o is None:
            raise HTTPException(status_code=404, detail="Observation not found")
        db.delete(o)


@router.get("/market/observations/template", response_class=PlainTextResponse)
def observation_template(adapter: str = Query(pattern="^(quotes|awards)$")) -> str:
    return sources.csv_template(adapter)


# --------------------------------------------------------------------------- phase 14: learning loop


class OutcomeBody(BaseModel):
    result: str = Field(pattern="^(won|lost|cancelled)$")
    winning_total: float | None = Field(default=None, gt=0)
    winner: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=1000)
    actor: str = Field(default="Reviewer", max_length=80)


def _outcome(o: BidOutcome | None) -> dict[str, Any] | None:
    if o is None:
        return None
    return {"result": o.result, "our_total": o.our_total, "winning_total": o.winning_total, "winner": o.winner,
            "note": o.note, "recorded_at": o.recorded_at.isoformat()}


@router.get("/rfps/{rfp_id}/outcome")
def get_outcome(rfp_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"outcome": _outcome(db.scalar(select(BidOutcome).where(BidOutcome.rfp_id == rfp_id)))}


@router.post("/rfps/{rfp_id}/outcome")
def set_outcome(rfp_id: int, body: OutcomeBody) -> dict[str, Any]:
    from app.agents.orchestrator import record_event

    with session_scope() as db:
        rfp = db.get(Rfp, rfp_id)
        if rfp is None:
            raise HTTPException(status_code=404, detail="Request not found")
        if not rfp.pricing:
            raise HTTPException(status_code=409, detail="The request has not been priced yet")
        out = _outcome(loop.record_outcome(db, rfp, body.result, body.winning_total, body.winner, body.note))
    record_event(rfp_id, f"outcome_{body.result}", body.actor, body.note, body.model_dump(exclude={"actor", "note"}))
    return {"outcome": out}


class LabelBody(BaseModel):
    requirement_id: str
    type: str = Field(min_length=2, max_length=32)


@router.post("/rfps/{rfp_id}/labels")
def label_requirement(rfp_id: int, body: LabelBody) -> dict[str, Any]:
    """A reviewer corrects the type of a requirement; the sentence becomes a training label."""
    from app.ml.registry import registry

    allowed = {str(label) for label in registry.clause_classifier().labels}
    if body.type not in allowed:
        raise HTTPException(status_code=422, detail=f"Type must be one of {', '.join(sorted(allowed))}")
    with session_scope() as db:
        rfp = db.get(Rfp, rfp_id)
        if rfp is None or not rfp.parsed:
            raise HTTPException(status_code=404, detail="Request not found")
        reqs = rfp.parsed.get("requirements", [])
        req = next((r for r in reqs if r.get("id") == body.requirement_id), None)
        if req is None:
            raise HTTPException(status_code=404, detail="Requirement not found")
        loop.record_label(db, "clause", req["text"], body.type, req.get("type"), rfp_id)
        parsed = dict(rfp.parsed)
        parsed["requirements"] = [{**r, "type": body.type, "confidence": 1.0, "reviewed": True}
                                  if r.get("id") == body.requirement_id else r for r in reqs]
        rfp.parsed = parsed
    return {"requirement_id": body.requirement_id, "type": body.type}


@router.get("/learning/status")
def learning_status() -> dict[str, Any]:
    return loop.status()


@router.get("/learning/evaluate")
def learning_evaluate() -> dict[str, Any]:
    return loop.evaluate()


# --------------------------------------------------------------------------- phase 15: submission pack


@router.get("/rfps/{rfp_id}/pack")
def submission_pack(rfp_id: int):
    from app.pack.builder import build_pack

    with session_scope() as db:
        rfp = db.get(Rfp, rfp_id)
        if rfp is None:
            raise HTTPException(status_code=404, detail="Request not found")
        m = _load_messages(rfp)
        if not all(k in m for k in ("parsed", "costing", "strategy", "proposal")):
            raise HTTPException(status_code=409, detail="The pack is available once the quotation has been drafted")
        existing = {}
        for kind, name in ((rfp.proposal or {}).get("documents") or {}).items():
            try:
                path = document_path(rfp.reference, name)
            except FileNotFoundError:
                continue
            if path.exists():
                existing[kind] = path
        out_dir = document_dir(rfp.reference) / "pack"
        zpath = build_pack(out_dir, company=load_json("company.json"), parsed=m["parsed"], costing=m["costing"],
                           strategy=m["strategy"], compliance=m.get("compliance"), proposal=m["proposal"],
                           existing=existing)
    return FileResponse(zpath, media_type="application/zip", filename=zpath.name)
