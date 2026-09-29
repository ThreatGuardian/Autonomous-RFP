"""Typed messages exchanged between agents."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- parser output


class ClientInfo(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    country_name: str | None = None
    region: str | None = None
    is_eu: bool = False
    segment: str = "smb"
    segment_source: str = "default"
    tax_id: str | None = None
    customer_id: int | None = None
    repeat_customer: bool = False


class CurrencyInfo(BaseModel):
    code: str
    source: Literal["explicit", "country_default", "company_default"]
    evidence: str | None = None


class ProductMatch(BaseModel):
    sku: str
    name: str
    category: str
    score: float
    retrieval_score: float
    spec_fit: float | None = None
    reasons: list[str] = Field(default_factory=list)


class RequestedItem(BaseModel):
    line_no: int
    text: str
    description: str
    quantity: int
    quantity_source: str
    unit: str | None = None
    category: str | None = None
    category_confidence: float = 0.0
    specs: dict[str, Any] = Field(default_factory=dict)
    brand: str | None = None
    candidates: list[ProductMatch] = Field(default_factory=list)
    selected_sku: str | None = None
    match_confidence: float = 0.0
    status: Literal["matched", "ambiguous", "unmatched"] = "unmatched"


class Requirement(BaseModel):
    id: str
    text: str
    type: str
    confidence: float


class CommercialTerms(BaseModel):
    incoterm: str | None = None
    incoterm_source: str = "default"
    delivery_location: str | None = None
    delivery_days: int | None = None
    payment_days: int | None = None
    advance_pct: float | None = None
    warranty_months_required: int | None = None
    price_weight_pct: float | None = None
    lowest_price_award: bool = False


class ParsedRfp(BaseModel):
    title: str
    client_reference: str | None = None
    client: ClientInfo
    currency: CurrencyInfo
    issued_on: str | None = None
    due_date: str | None = None
    delivery_by: str | None = None
    terms: CommercialTerms
    line_items: list[RequestedItem]
    requirements: list[Requirement]
    requirement_counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
