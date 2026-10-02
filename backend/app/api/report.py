"""Editable bid report: document, assistant, undo/redo and export."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import _load_messages, document_dir
from app.db.models import Rfp
from app.db.seed import load_json
from app.db.session import session_scope
from app.rag.stores import knowledge_store
from app.report.assistant import HISTORY_LIMIT, ReportAssistant, ensure_ids
from app.report.builder import build_document, build_sections, figures
from app.report.export import render_docx, render_pdf

router = APIRouter(prefix="/api/rfps", tags=["report"])
CHAT_LIMIT = 80


class SaveBody(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    sections: list[dict[str, Any]]


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _context(rfp: Rfp):
    m = _load_messages(rfp)
    if not all(k in m for k in ("parsed", "strategy", "localisation", "proposal")):
        raise HTTPException(status_code=409, detail="The report is available once the quotation has been drafted")
    return m


def _fresh(rfp: Rfp) -> dict[str, Any]:
    m = _context(rfp)
    return build_document(load_json("company.json"), m["parsed"], m["strategy"], m["localisation"], m["proposal"],
                          m.get("compliance"))


def _load(rfp: Rfp) -> dict[str, Any]:
    """Current document; untouched reports follow the latest pipeline run, edited ones are flagged when stale."""
    doc = rfp.report_doc
    version = (rfp.proposal or {}).get("version")
    if doc is None or (not doc.get("edited") and doc.get("proposal_version") != version):
        chat = (doc or {}).get("chat", [])
        doc = _fresh(rfp)
        doc["chat"] = chat
        rfp.report_doc = doc
    elif doc.get("edited") and doc.get("proposal_version") != version and not doc.get("stale"):
        doc = copy.deepcopy(doc)
        doc["stale"] = True
        rfp.report_doc = doc
    return doc


def _public(doc: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in doc.items() if k not in ("history", "redo")}
    out["can_undo"], out["can_redo"] = bool(doc.get("history")), bool(doc.get("redo"))
    return out


def _get(db, rfp_id: int) -> Rfp:
    rfp = db.get(Rfp, rfp_id)
    if rfp is None:
        raise HTTPException(status_code=404, detail="RFP not found")
    return rfp


@router.get("/{rfp_id}/report")
def get_report(rfp_id: int) -> dict[str, Any]:
    with session_scope() as db:
        return _public(_load(_get(db, rfp_id)))


@router.put("/{rfp_id}/report")
def save_report(rfp_id: int, body: SaveBody) -> dict[str, Any]:
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        doc = copy.deepcopy(_load(rfp))
        doc.setdefault("history", []).append({"title": doc["title"], "sections": doc["sections"]})
        doc["history"] = doc["history"][-HISTORY_LIMIT:]
        doc["redo"] = []
        doc["title"], doc["sections"] = body.title, body.sections
        ensure_ids(doc)
        doc["edited"], doc["updated_at"] = True, _now()
        rfp.report_doc = doc
        return _public(doc)


@router.post("/{rfp_id}/report/assistant")
def assistant(rfp_id: int, body: ChatBody) -> dict[str, Any]:
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        doc = copy.deepcopy(_load(rfp))
        m = _context(rfp)
        company = load_json("company.json")
        kb = knowledge_store()
        helper = ReportAssistant(
            figures=figures(m["parsed"], m["strategy"], m["localisation"], m.get("compliance")),
            regenerate=lambda key: build_sections(company, m["parsed"], m["strategy"], m["localisation"], m["proposal"],
                                                  m.get("compliance"), only=key),
            retrieve=lambda q: kb.evidence(q, k=1),
        )
        result = helper.handle(doc, body.message)
        if result.changed:
            doc["updated_at"] = _now()
            doc["proposal_version"] = (rfp.proposal or {}).get("version")
        chat = doc.setdefault("chat", [])
        chat.append({"role": "user", "text": body.message, "at": _now()})
        chat.append({"role": "assistant", "text": result.reply, "at": _now(), "intent": result.intent,
                     "confidence": result.confidence, "changes": result.changes})
        doc["chat"] = chat[-CHAT_LIMIT:]
        rfp.report_doc = doc
        return {"reply": result.reply, "changed": result.changed, "changes": result.changes, "intent": result.intent,
                "confidence": result.confidence, "suggestions": result.suggestions, "document": _public(doc)}


def _step(rfp_id: int, source: str, target: str) -> dict[str, Any]:
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        doc = copy.deepcopy(_load(rfp))
        if not doc.get(source):
            raise HTTPException(status_code=409, detail=f"Nothing to {'undo' if source == 'history' else 'redo'}")
        doc.setdefault(target, []).append({"title": doc["title"], "sections": doc["sections"]})
        snap = doc[source].pop()
        doc["title"], doc["sections"], doc["updated_at"] = snap["title"], snap["sections"], _now()
        rfp.report_doc = doc
        return _public(doc)


@router.post("/{rfp_id}/report/undo")
def undo(rfp_id: int) -> dict[str, Any]:
    return _step(rfp_id, "history", "redo")


@router.post("/{rfp_id}/report/redo")
def redo(rfp_id: int) -> dict[str, Any]:
    return _step(rfp_id, "redo", "history")


@router.post("/{rfp_id}/report/reset")
def reset(rfp_id: int) -> dict[str, Any]:
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        old = rfp.report_doc or {}
        doc = _fresh(rfp)
        doc["history"] = (old.get("history", []) + [{"title": old["title"], "sections": old["sections"]}])[-HISTORY_LIMIT:] if old else []
        doc["chat"] = old.get("chat", [])
        rfp.report_doc = doc
        return _public(doc)


def export_report(rfp: Rfp, fmt: str) -> Path:
    doc = _load(rfp)
    company = load_json("company.json")
    folder = document_dir(rfp.reference)
    stem = f"{(rfp.proposal or {}).get('quote_number', rfp.reference)}-bid-report{'-edited' if doc.get('edited') else ''}"
    if fmt == "docx":
        return render_docx(doc, folder / f"{stem}.docx", company)
    return render_pdf(doc, folder / f"{stem}.pdf", company, approved=rfp.status == "approved")


@router.get("/{rfp_id}/report/export")
def export(rfp_id: int, format: str = "pdf"):
    if format not in ("pdf", "docx"):
        raise HTTPException(status_code=422, detail="format must be pdf or docx")
    with session_scope() as db:
        rfp = _get(db, rfp_id)
        path = export_report(rfp, format)
    media = "application/pdf" if format == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=media, filename=path.name,
                        content_disposition_type="inline" if format == "pdf" else "attachment")

