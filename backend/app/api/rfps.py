"""RFP intake, pipeline status, review and approval endpoints."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agents.orchestrator import STAGES, document_path, get_orchestrator, record_event, source_path
from app.api.uploads import read_upload
from app.config import BACKEND_ROOT
from app.db.models import Rfp
from app.db.session import get_db, session_scope
from app.services.documents import SUPPORTED, UnsupportedDocument, extract_text

router = APIRouter(prefix="/api/rfps", tags=["rfps"])
SAMPLES_DIR = BACKEND_ROOT.parent / "samples"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FILES = 10


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


class ClientEdit(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=48)
    tax_id: str | None = Field(default=None, max_length=32)
    segment: str | None = Field(default=None, pattern=r"^(enterprise|smb|public|education|healthcare)$")


class AddedLine(BaseModel):
    sku: str = Field(min_length=3, max_length=32)
    quantity: int = Field(gt=0, le=100000)


class RepriceRequest(BaseModel):
    lines: dict[str, LineOverride] = Field(default_factory=dict)
    client: ClientEdit | None = None
    incoterm: str | None = Field(default=None, pattern=r"^(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP|)$")
    add_lines: list[AddedLine] = Field(default_factory=list)
    remove_added: list[int] = Field(default_factory=list)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fx_buffer_pct: float | None = Field(default=None, ge=0, le=10)
    reset: bool = False
    actor: str = "Reviewer"
    note: str | None = None


class ComplianceEdit(BaseModel):
    status: str = Field(pattern=r"^(Complies|Complies with note|Clarification required|Deviation|Noted)$")
    response: str | None = Field(default=None, max_length=1200)


class EligibilityEdit(BaseModel):
    status: str = Field(pattern=r"^(Meets|Documents required|Needs review|Does not meet)$")
    position: str | None = Field(default=None, max_length=1200)


class ComplianceRequest(BaseModel):
    items: dict[str, ComplianceEdit] = Field(default_factory=dict)
    eligibility: dict[str, EligibilityEdit] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list)
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
        "recommendation": (r.compliance or {}).get("recommendation"),
        "eligibility_verdict": (r.compliance or {}).get("eligibility_verdict"),
        "pages": ((r.parsed or {}).get("document") or {}).get("pages"),
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


def _ingest(filename: str, data: bytes) -> tuple[int | None, str | None]:
    """Create an RFP from an uploaded file, keeping the original next to its documents."""
    if len(data) > MAX_UPLOAD_BYTES:
        return None, f"{filename}: file exceeds 10 MB"
    try:
        text = extract_text(filename, data)
    except UnsupportedDocument as exc:
        return None, f"{filename}: {exc}"
    if len(text.strip()) < 40:
        return None, f"{filename}: not enough readable text"
    with session_scope() as db:
        rfp = _create(db, text, filename)
        rfp_id = rfp.id
        original = source_path(rfp.reference, filename)
    if original is not None:
        # Keep the original so the parser can use pages, fonts and tables, and reviewers can open it.
        original.write_bytes(data)
    return rfp_id, None


@router.post("/upload", status_code=201)
async def upload_rfps(files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=422, detail=f"Upload at most {MAX_FILES} files at a time")
    created: list[int] = []
    errors: list[str] = []
    for f in files:
        rfp_id, error = _ingest(f.filename or "upload.txt", await read_upload(f, MAX_UPLOAD_BYTES))
        if rfp_id is not None:
            created.append(rfp_id)
        if error:
            errors.append(error)
    if not created:
        raise HTTPException(status_code=422, detail="; ".join(errors) or "No files received")
    orch = get_orchestrator()
    for rfp_id in created:
        orch.submit(rfp_id)
    with session_scope() as db:
        return [_summary(db.get(Rfp, i), True) | {"upload_errors": errors} for i in created]


@lru_cache(maxsize=32)
def _file_sample(name: str, mtime: float) -> dict[str, Any]:
    path = SAMPLES_DIR / name
    text = extract_text(name, path.read_bytes())
    subject = re.search(r"^\s*(?:subject|title)\s*:\s*(.+)$", text, re.I | re.M)
    org = next((l.strip() for l in text.splitlines() if l.strip()), name)
    return {"filename": name, "title": f"{org} — {subject.group(1).strip()}" if subject else org, "text": "",
            "kind": "file", "format": path.suffix.lstrip(".").upper(), "pages": text.count("\f") + 1}


@router.get("/samples")
def samples() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    # Long tender documents first: they exercise layout analysis and the compliance review.
    for p in sorted(SAMPLES_DIR.glob("*")):
        if p.suffix.lower() in (".pdf", ".docx"):
            info = _file_sample(p.name, p.stat().st_mtime)
            if info["pages"] >= 4:
                out.append(info)
    for p in sorted(SAMPLES_DIR.glob("*.txt")):
        text = p.read_text(encoding="utf-8")
        first = next((l.strip() for l in text.splitlines() if l.strip()), p.stem)
        first = re.sub(r"^(from|to|issued by)\s*:\s*", "", first, flags=re.I)
        out.append({"filename": p.name, "title": first, "text": text, "kind": "text"})
    return out


@router.post("/samples/{filename}", status_code=201)
def process_sample(filename: str) -> list[dict[str, Any]]:
    path = (SAMPLES_DIR / filename).resolve()
    if path.parent != SAMPLES_DIR.resolve() or not path.is_file() or path.suffix.lower() not in (".pdf", ".docx", ".txt"):
        raise HTTPException(status_code=404, detail="Sample not found")
    rfp_id, error = _ingest(path.name, path.read_bytes())
    if rfp_id is None:
        raise HTTPException(status_code=422, detail=error)
    get_orchestrator().submit(rfp_id)
    with session_scope() as db:
        return [_summary(db.get(Rfp, rfp_id), True)]


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
        "raw_text": r.raw_text, "parsed": r.parsed, "pricing": r.pricing, "compliance": r.compliance, "proposal": r.proposal,
        "overrides": r.overrides,
        "has_original": bool((p := source_path(r.reference, r.source_filename)) and p.exists()),
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
        current = dict(rfp.overrides or {})
        # A pricing reset keeps the reviewer's compliance decisions.
        overrides: dict[str, Any] = {k: current[k] for k in ("compliance", "eligibility") if k in current} if body.reset else current
        lines = dict(overrides.get("lines", {}))
        for key, ov in body.lines.items():
            if ov.sku:
                from app.learning.loop import record_line_correction

                record_line_correction(db, rfp, key, ov.sku)  # a product swap teaches the category model
            entry = {**lines.get(key, {}), **ov.model_dump(exclude_none=True, exclude={"clear_bundle"})}
            if ov.clear_bundle:
                entry["bundle"] = None
            lines[key] = entry
        overrides["lines"] = lines
        if body.currency:
            overrides["currency"] = body.currency.upper()
        if body.fx_buffer_pct is not None:
            overrides["fx_buffer_pct"] = body.fx_buffer_pct
        if body.client is not None:
            overrides["client"] = {**overrides.get("client", {}), **body.client.model_dump(exclude_unset=True)}
            if "country" in overrides["client"]:
                overrides["client"]["country"] = (overrides["client"]["country"] or "").upper() or None
        if body.incoterm is not None:
            overrides["terms"] = {**overrides.get("terms", {}), "incoterm": body.incoterm or None}
        added = [a for a in overrides.get("added_lines", []) if a["line_no"] not in set(body.remove_added)]
        if body.add_lines:
            used = [i["line_no"] for i in (rfp.parsed or {}).get("line_items", [])] + [a["line_no"] for a in added]
            next_no = max(used, default=0) + 1
            for extra in body.add_lines:
                added.append({"sku": extra.sku, "quantity": extra.quantity, "line_no": next_no})
                next_no += 1
        overrides["added_lines"] = added
        rfp.overrides = overrides
        # Match changes affect costing; price and bundle changes only need re-pricing downstream.
        from_stage = "costing"
    record_event(rfp_id, "repriced", body.actor, body.note, body.model_dump(exclude={"actor", "note"}))
    get_orchestrator().submit(rfp_id, from_stage)
    return {"status": "queued", "from_stage": from_stage}


@router.post("/{rfp_id}/compliance")
def update_compliance(rfp_id: int, body: ComplianceRequest) -> dict[str, Any]:
    """Reviewer corrections to the compliance matrix and eligibility checks; re-runs compliance onwards."""
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        if rfp.status in ("processing", "queued"):
            raise HTTPException(status_code=409, detail="The request is still being processed")
        if not rfp.compliance:
            raise HTTPException(status_code=409, detail="The compliance review has not been prepared yet")
        overrides = dict(rfp.overrides or {})
        items = dict(overrides.get("compliance", {}))
        elig = dict(overrides.get("eligibility", {}))
        for key, edit in body.items.items():
            items[key] = edit.model_dump(exclude_none=True)
        for key, edit in body.eligibility.items():
            elig[key] = edit.model_dump(exclude_none=True)
        for key in body.clear:
            items.pop(key, None)
            elig.pop(key, None)
        overrides["compliance"], overrides["eligibility"] = items, elig
        rfp.overrides = overrides
    record_event(rfp_id, "compliance_updated", body.actor, body.note, body.model_dump(exclude={"actor", "note"}))
    get_orchestrator().submit(rfp_id, "compliance")
    return {"status": "queued", "from_stage": "compliance"}


@router.get("/{rfp_id}/original")
def original(rfp_id: int, db: Session = Depends(get_db)):
    r = _get(db, rfp_id)
    path = source_path(r.reference, r.source_filename)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Original document not kept for this request")
    media = "application/pdf" if path.suffix == ".pdf" else \
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=media, filename=r.source_filename or path.name, content_disposition_type="inline")


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
    if kind == "report" and (r.report_doc or {}).get("edited"):
        # The reviewer's edited report replaces the generated one.
        from app.api.report import export_report

        path = export_report(r, "pdf")
        return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")
    if kind not in ("quotation", "memo", "report", "compliance") or kind not in docs:
        raise HTTPException(status_code=404, detail="Document not available")
    try:
        path = document_path(r.reference, docs[kind])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found") from None
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document file missing")
    return FileResponse(path, media_type="application/pdf", filename=path.name,
                        content_disposition_type="inline")
