"""Relational schema for the internal pricing database and the RFP workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- users


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    title: Mapped[str] = mapped_column(String(80), default="Bid manager")
    provider: Mapped[str] = mapped_column(String(16), default="password")  # password | firebase
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Identity-provider subject (the Firebase user id) for accounts that sign in with Google or SSO.
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --------------------------------------------------------------------------- catalogue


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    mpn: Mapped[str] = mapped_column(String(48), index=True)  # manufacturer part number
    name: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(48), index=True)
    description: Mapped[str] = mapped_column(Text)
    specs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    unit: Mapped[str] = mapped_column(String(16), default="unit")
    unit_cost: Mapped[float] = mapped_column(Float)  # landed cost, base currency
    list_price: Mapped[float] = mapped_column(Float)
    min_margin_pct: Mapped[float] = mapped_column(Float, default=8.0)
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    warranty_months: Mapped[int] = mapped_column(Integer, default=12)
    tax_category: Mapped[str] = mapped_column(String(32), default="goods_standard")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    hsn: Mapped[str | None] = mapped_column(String(12), nullable=True)  # HSN / SAC code
    gst_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # when it differs from the tax category
    price_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def floor_price(self) -> float:
        return round(self.unit_cost * (1 + self.min_margin_pct / 100), 2)


class PriceTier(Base):
    """Volume discount schedule per category."""

    __tablename__ = "price_tiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(48), index=True)
    min_qty: Mapped[int] = mapped_column(Integer)
    discount_pct: Mapped[float] = mapped_column(Float)


class ValueAdd(Base):
    """Bundle-able warranty and service offerings used for value differentiation."""

    __tablename__ = "value_adds"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(24))  # warranty | service | support | training
    description: Mapped[str] = mapped_column(Text)
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    basis: Mapped[str] = mapped_column(String(8))  # "percent" of the product, or "flat" per unit
    cost_rate: Mapped[float] = mapped_column(Float)  # our cost
    value_rate: Mapped[float] = mapped_column(Float)  # what the client would pay on the open market
    warranty_extension_months: Mapped[int] = mapped_column(Integer, default=0)

    def unit_cost_for(self, product: Product) -> float:
        """Our cost of providing this value-add for one unit of ``product``."""
        if self.basis == "percent":
            return round(product.unit_cost * self.cost_rate / 100, 2)
        return self.cost_rate

    def unit_value_for(self, product: Product) -> float:
        """Market value of this value-add for one unit of ``product``."""
        if self.basis == "percent":
            return round(product.list_price * self.value_rate / 100, 2)
        return self.value_rate


# --------------------------------------------------------------------------- customers & history


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    country: Mapped[str] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(48), nullable=True)
    segment: Mapped[str] = mapped_column(String(32))  # enterprise | smb | public | education | healthcare
    tax_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deals_won: Mapped[int] = mapped_column(Integer, default=0)


class DealHistory(Base):
    """Historical bid outcomes; training data for the win-probability model."""

    __tablename__ = "deal_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    closed_on: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    customer_segment: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(48))
    quantity: Mapped[int] = mapped_column(Integer)
    price_ratio: Mapped[float] = mapped_column(Float)  # our price / best competitor price
    margin_pct: Mapped[float] = mapped_column(Float)
    warranty_delta_months: Mapped[int] = mapped_column(Integer)
    lead_time_delta_days: Mapped[int] = mapped_column(Integer)
    bundled_value_add: Mapped[bool] = mapped_column(Boolean)
    repeat_customer: Mapped[bool] = mapped_column(Boolean)
    won: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)  # None/synthetic | outcome
    rfp_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


# --------------------------------------------------------------------------- finance


class TaxRule(Base):
    __tablename__ = "tax_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    region: Mapped[str | None] = mapped_column(String(48), nullable=True)
    tax_category: Mapped[str] = mapped_column(String(32), default="*")
    name: Mapped[str] = mapped_column(String(48))
    rate_pct: Mapped[float] = mapped_column(Float)
    components: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    base: Mapped[str] = mapped_column(String(3), index=True)
    quote: Mapped[str] = mapped_column(String(3), index=True)
    rate: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(48))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------- workflow


class Rfp(Base):
    __tablename__ = "rfps"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240), default="Untitled request")
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    source_filename: Mapped[str | None] = mapped_column(String(240), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)

    client_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    client_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(16), nullable=True)

    parsed: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    pricing: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    compliance: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    report_doc: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    total_base: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_client: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy_summary: Mapped[str | None] = mapped_column(String(48), nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    stages: Mapped[list["StageRun"]] = relationship(
        back_populates="rfp", cascade="all, delete-orphan", order_by="StageRun.id"
    )
    events: Mapped[list["ApprovalEvent"]] = relationship(
        back_populates="rfp", cascade="all, delete-orphan", order_by="ApprovalEvent.id"
    )


class StageRun(Base):
    """One execution of one agent against one RFP."""

    __tablename__ = "stage_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rfp_id: Mapped[int] = mapped_column(ForeignKey("rfps.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    agent: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    rfp: Mapped[Rfp] = relationship(back_populates="stages")


class ApprovalEvent(Base):
    __tablename__ = "approval_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    rfp_id: Mapped[int] = mapped_column(ForeignKey("rfps.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(80), default="Reviewer")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    rfp: Mapped[Rfp] = relationship(back_populates="events")


# --------------------------------------------------------------------------- company data import (phase 12)


class ImportBatch(Base):
    """One upload of company data (catalogue, prices, stock) from CSV, Excel or Tally."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(240))
    format: Mapped[str] = mapped_column(String(16))  # csv | xlsx | tally
    rows: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    actor: Mapped[str] = mapped_column(String(80), default="Reviewer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceVersion(Base):
    """Price and stock history for a product; one row each time a value changes."""

    __tablename__ = "price_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), index=True)
    unit_cost: Mapped[float] = mapped_column(Float)
    list_price: Mapped[float] = mapped_column(Float)
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(80), default="seed")
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)


# --------------------------------------------------------------------------- competitor intelligence (phase 13)


class PriceObservation(Base):
    """A dated, sourced competitor price for one product."""

    __tablename__ = "price_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[str] = mapped_column(String(48), index=True)
    competitor: Mapped[str] = mapped_column(String(120))
    mpn: Mapped[str] = mapped_column(String(48), index=True)
    product: Mapped[str | None] = mapped_column(String(160), nullable=True)
    unit_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    warranty_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    adapter: Mapped[str] = mapped_column(String(24))  # quotes | awards | web | feed
    source: Mapped[str] = mapped_column(String(80))
    reference: Mapped[str | None] = mapped_column(String(240), nullable=True)
    collected_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------- learning loop (phase 14)


class TrainingLabel(Base):
    """A label produced by a reviewer's correction, used to retrain a model."""

    __tablename__ = "training_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(32), index=True)  # clause | category
    text: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(48))
    predicted: Mapped[str | None] = mapped_column(String(48), nullable=True)
    rfp_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(48), default="reviewer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BidOutcome(Base):
    """What happened to a submitted bid; feeds the win-probability model."""

    __tablename__ = "bid_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    rfp_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    result: Mapped[str] = mapped_column(String(16))  # won | lost | cancelled
    our_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    winning_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    winner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------- workspace settings


class WorkspaceSetting(Base):
    """A workspace-level preference set in the app (e.g. the operating region)."""

    __tablename__ = "workspace_settings"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
