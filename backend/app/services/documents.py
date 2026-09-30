"""Text extraction from uploaded RFP documents (PDF, DOCX, plain text)."""

from __future__ import annotations

import io
from pathlib import Path


class UnsupportedDocument(ValueError):
    pass


SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".text"}


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _pdf(data)
    if suffix == ".docx":
        return _docx(data)
    if suffix in {".txt", ".md", ".text", ""}:
        for enc in ("utf-8", "utf-16", "cp1252", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
    raise UnsupportedDocument(f"Unsupported file type '{suffix or filename}'. Upload PDF, DOCX or TXT.")


def _pdf(data: bytes) -> str:
    from app.nlp.layout import analyse_pdf

    layout = analyse_pdf(data)
    text = layout.to_text().strip()
    if not text.replace("\f", "").strip():
        raise UnsupportedDocument("The PDF contains no extractable text (it may be a scanned image without OCR).")
    return text


def _pdf_plain(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text(extraction_mode="layout") or "")
        except TypeError:  # older pypdf without layout mode
            pages.append(page.extract_text() or "")
    text = "\n\n".join(pages).strip()
    if not text:
        raise UnsupportedDocument("The PDF contains no extractable text (it may be a scanned image).")
    return text


def _docx(data: bytes) -> str:
    from app.nlp.layout import analyse_docx

    return analyse_docx(data).to_text()


def _docx_plain(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    parts: list[str] = []
    # Preserve body order of paragraphs and tables.
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = "".join(node.text or "" for node in child.iter() if node.tag.endswith("}t"))
            if text.strip():
                parts.append(text)
        elif tag == "tbl":
            table = docx.table.Table(child, document)
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                parts.append("| " + " | ".join(cells) + " |")
            parts.append("")
    return "\n".join(parts)
