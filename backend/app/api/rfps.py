"""RFP intake, pipeline status, review and approval endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agents.orchestrator import STAGES, document_path, get_orchestrator, record_event
from app.config import BACKEND_ROOT
from app.db.models import Rfp
from app.db.session import get_db, session_scope
from app.services.documents import SUPPORTED, UnsupportedDocument, extract_text

router = APIRouter(prefix="/api/rfps", tags=["rfps"])
SAMPLES_DIR = BACKEND_ROOT.parent / "samples"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class CreateRfp(BaseModel):
    text: str = Field(min_length=40, max_length=400_000)
    filename: str | None = None


class LineOverride(BaseModel):
    unit_price: float | None = Field(default=None, gt=0)
    bundle: str | None = None
    clear_bundle: bool = False
    sku: str | None = None
    quantity: int | None = Field(default=None, gt=0)
    exclude: bool | None = None


class RepriceRequest(BaseModel):
    lines: dict[str, LineOverride] = Field(default_factory=dict)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fx_buffer_pct: float | None = Field(default=None, ge=0, le=10)
    reset: bool = False
    actor: str = "Reviewer"
    note: str | None = None


class Decision(BaseModel):
    actor: str = Field(default="Reviewer", max_length=80)
    note: str | None = Field(default=None, max_length=2000)


def _summary(r: Rfp, running: bool = False) -> dict[str, Any]:
    strategy = (r.pricing or {}).get("strategy") or {}
    return {
        "id": r.id, "reference": r.reference, "title": r.title, "status": r.status, "running": running,
        "client_name": r.client_name, "client_country": r.client_country, "currency": r.currency, "due_date": r.due_date,
        "total_base": r.total_base, "total_client": r.total_client, "margin_pct": r.margin_pct,
        "win_probability": strategy.get("win_probability"), "strategy_summary": r.strategy_summary,
        "line_count": len(strategy.get("lines", [])) or len((r.parsed or {}).get("line_items", [])),
        "below_cost_competitors": strategy.get("below_cost_competitors"),
        "source_filename": r.source_filename, "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat(),
        "error": r.error,
    }


def _stage_dict(st) -> dict[str, Any]:
    return {"id": st.id, "stage": st.stage, "agent": st.agent, "status": st.status,
            "started_at": st.started_at.isoformat(), "finished_at": st.finished_at.isoformat() if st.finished_at else None,
            "duration_ms": st.duration_ms, "summary": st.summary, "log": st.log}


def _create(db: Session, text: str, filename: str | None) -> Rfp:
    year = datetime.now(timezone.utc).year
    next_id = (db.scalar(select(func.max(Rfp.id))) or 0) + 1
    rfp = Rfp(reference=f"RFP-{year}-{next_id:04d}", raw_text=text, source_filename=filename, status="queued",
              title=(filename or "Pasted request").rsplit(".", 1)[0][:240])
    db.add(rfp)
    db.flush()
    return rfp


@router.get("")
def list_rfps(status: str | None = None, q: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Rfp).order_by(Rfp.created_at.desc())
    if status:
        stmt = stmt.where(Rfp.status.in_(status.split(",")))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Rfp.title.ilike(like), Rfp.client_name.ilike(like), Rfp.reference.ilike(like)))
    orch = get_orchestrator()
    return [_summary(r, orch.is_running(r.id)) for r in db.scalars(stmt)]


@router.post("", status_code=201)
def create_rfp(body: CreateRfp) -> dict[str, Any]:
    with session_scope() as db:
        rfp = _create(db, body.text, body.filename)
        rfp_id = rfp.id
    get_orchestrator().submit(rfp_id)
    with session_scope() as db:
        return _summary(db.get(Rfp, rfp_id), True)


@router.post("/upload", status_code=201)
async def upload_rfps(files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
    created: list[int] = []
    errors: list[str] = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            errors.append(f"{f.filename}: file exceeds 10 MB")
            continue
        try:
            text = extract_text(f.filename or "upload.txt", data)
        except UnsupportedDocument as exc:
            errors.append(f"{f.filename}: {exc}")
            continue
        if len(text.strip()) < 40:
            errors.append(f"{f.filename}: not enough readable text")
            continue
        with session_scope() as db:
            created.append(_create(db, text, f.filename).id)
    if not created:
        raise HTTPException(status_code=422, detail="; ".join(errors) or "No files received")
    orch = get_orchestrator()
    for rfp_id in created:
        orch.submit(rfp_id)
    with session_scope() as db:
        return [_summary(db.get(Rfp, i), True) | {"upload_errors": errors} for i in created]


@router.get("/samples")
def samples() -> list[dict[str, str]]:
    out = []
    for p in sorted(SAMPLES_DIR.glob("*.txt")):
        text = p.read_text(encoding="utf-8")
        first = next((l.strip() for l in text.splitlines() if l.strip()), p.stem)
        out.append({"filename": p.name, "title": first, "text": text})
    return out


def _get(db: Session, rfp_id: int) -> Rfp:
    rfp = db.get(Rfp, rfp_id)
    if rfp is None:
        raise HTTPException(status_code=404, detail="RFP not found")
    return rfp


@router.get("/{rfp_id}")
def get_rfp(rfp_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = _get(db, rfp_id)
    return {
        **_summary(r, get_orchestrator().is_running(r.id)),
        "raw_text": r.raw_text, "parsed": r.parsed, "pricing": r.pricing, "proposal": r.proposal, "overrides": r.overrides,
        "stages": [_stage_dict(s) for s in r.stages], "stage_order": STAGES,
        "events": [{"id": e.id, "action": e.action, "actor": e.actor, "note": e.note, "payload": e.payload,
                    "created_at": e.created_at.isoformat()} for e in r.events],
    }


@router.post("/{rfp_id}/reprice")
def reprice(rfp_id: int, body: RepriceRequest) -> dict[str, Any]:
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        if rfp.status in ("processing", "queued"):
            raise HTTPException(status_code=409, detail="The request is still being processed")
        if not rfp.parsed:
            raise HTTPException(status_code=409, detail="The request has not been parsed yet")
        overrides: dict[str, Any] = {} if body.reset else dict(rfp.overrides or {})
        lines = dict(overrides.get("lines", {}))
        for key, ov in body.lines.items():
            entry = {**lines.get(key, {}), **ov.model_dump(exclude_none=True, exclude={"clear_bundle"})}
            if ov.clear_bundle:
                entry["bundle"] = None
            lines[key] = entry
        overrides["lines"] = lines
        if body.currency:
            overrides["currency"] = body.currency.upper()
        if body.fx_buffer_pct is not None:
            overrides["fx_buffer_pct"] = body.fx_buffer_pct
        rfp.overrides = overrides
        # Match changes affect costing; price and bundle changes only need re-pricing downstream.
        from_stage = "costing"
    record_event(rfp_id, "repriced", body.actor, body.note, body.model_dump(exclude={"actor", "note"}))
    get_orchestrator().submit(rfp_id, from_stage)
    return {"status": "queued", "from_stage": from_stage}


@router.post("/{rfp_id}/approve")
def approve(rfp_id: int, body: Decision) -> dict[str, Any]:
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        if rfp.status != "review":
            raise HTTPException(status_code=409, detail=f"Only requests in review can be approved (current: {rfp.status})")
    docs = get_orchestrator().finalize(rfp_id, body.actor, body.note)
    with session_scope() as db:
        _get(db, rfp_id).status = "approved"
    record_event(rfp_id, "approved", body.actor, body.note, {"documents": docs})
    return {"status": "approved", "documents": docs}


@router.post("/{rfp_id}/reject")
def reject(rfp_id: int, body: Decision) -> dict[str, Any]:
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        if rfp.status not in ("review", "approved"):
            raise HTTPException(status_code=409, detail=f"Cannot reject a request in status {rfp.status}")
        rfp.status = "rejected"
    record_event(rfp_id, "rejected", body.actor, body.note)
    return {"status": "rejected"}


@router.post("/{rfp_id}/reopen")
def reopen(rfp_id: int, body: Decision) -> dict[str, Any]:
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        if rfp.status not in ("approved", "rejected"):
            raise HTTPException(status_code=409, detail="Only approved or rejected requests can be reopened")
        rfp.status = "review"
    record_event(rfp_id, "reopened", body.actor, body.note)
    return {"status": "review"}


@router.post("/{rfp_id}/retry")
def retry(rfp_id: int) -> dict[str, Any]:
    with session_scope() as db:
        _get(db, rfp_id)
    get_orchestrator().submit(rfp_id, "intake")
    return {"status": "queued"}


@router.delete("/{rfp_id}", status_code=204)
def delete(rfp_id: int) -> None:
    if get_orchestrator().is_running(rfp_id):
        raise HTTPException(status_code=409, detail="Cannot delete while processing")
    with session_scope() as db:
        db.delete(_get(db, rfp_id))


@router.get("/{rfp_id}/documents/{kind}")
def document(rfp_id: int, kind: str, db: Session = Depends(get_db)):
    r = _get(db, rfp_id)
    docs = (r.proposal or {}).get("documents") or {}
    if kind not in ("quotation", "memo") or kind not in docs:
        raise HTTPException(status_code=404, detail="Document not available")
    try:
        path = document_path(r.reference, docs[kind])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found") from None
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document file missing")
    return FileResponse(path, media_type="application/pdf", filename=path.name,
                        content_disposition_type="inline")
