"""Currency conversion with a live-provider → cache → reference fallback chain.

Rates are stored against the company base currency (INR): ``rate`` is the
number of units of ``quote`` bought by one unit of ``base``. Cross rates are
derived through the base, so a single fetch serves every currency pair.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select

from app.config import get_settings
from app.db.models import FxRate
from app.db.seed import load_json
from app.db.session import session_scope

BASE = "INR"
PROVIDERS = (
    ("frankfurter.app (ECB)", "https://api.frankfurter.app/latest?from={base}", "rates"),
    ("open.er-api.com", "https://open.er-api.com/v6/latest/{base}", "rates"),
)


class UnknownCurrency(ValueError):
    pass


@dataclass(frozen=True)
class FxQuote:
    base: str
    quote: str
    rate: float  # units of quote per 1 base
    source: str
    as_of: str
    stale: bool = False

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class FxService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._table: dict[str, float] | None = None
        self._source = ""
        self._as_of = ""
        self._stale = False
        self._loaded_at = 0.0

    # ------------------------------------------------------------------ loading

    def _fetch_live(self) -> tuple[dict[str, float], str] | None:
        settings = get_settings()
        for name, url, key in PROVIDERS:
            try:
                resp = httpx.get(url.format(base=BASE), timeout=settings.fx_timeout_seconds)
                resp.raise_for_status()
                rates = {k.upper(): float(v) for k, v in resp.json()[key].items() if float(v) > 0}
                if len(rates) >= 10:
                    rates[BASE] = 1.0
                    return rates, name
            except Exception:
                continue
        return None

    def _load_cache(self) -> tuple[dict[str, float], str, datetime] | None:
        with session_scope() as s:
            rows = list(s.scalars(select(FxRate).where(FxRate.base == BASE)))
        if not rows:
            return None
        fetched = min(r.fetched_at for r in rows)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return {r.quote: r.rate for r in rows}, rows[0].source, fetched

    def _store_cache(self, rates: dict[str, float], source: str) -> None:
        now = datetime.now(timezone.utc)
        with session_scope() as s:
            s.execute(delete(FxRate).where(FxRate.base == BASE))
            s.add_all(FxRate(base=BASE, quote=q, rate=r, source=source, fetched_at=now) for q, r in rates.items())

    @staticmethod
    def _reference() -> tuple[dict[str, float], str, str]:
        ref = load_json("fx_reference.json")
        return {c: 1.0 / v for c, v in ref["inr_per_unit"].items()}, "reference table", ref["as_of"]

    def _ensure(self) -> None:
        settings = get_settings()
        ttl = timedelta(hours=settings.fx_cache_ttl_hours)
        if self._table is not None and time.time() - self._loaded_at < 300:
            return
        cache = self._load_cache()
        now = datetime.now(timezone.utc)
        if cache and now - cache[2] < ttl:
            self._set(cache[0], cache[1], cache[2].isoformat(timespec="minutes"), stale=False)
            return
        if settings.fx_mode == "live":
            live = self._fetch_live()
            if live:
                self._store_cache(*live)
                self._set(live[0], live[1], now.isoformat(timespec="minutes"), stale=False)
                return
        if cache:
            self._set(cache[0], cache[1] + " (cached)", cache[2].isoformat(timespec="minutes"), stale=True)
            return
        table, source, as_of = self._reference()
        self._set(table, source, as_of, stale=settings.fx_mode == "live")

    def _set(self, table: dict[str, float], source: str, as_of: str, stale: bool) -> None:
        self._table, self._source, self._as_of, self._stale = table, source, as_of, stale
        self._loaded_at = time.time()

    # ------------------------------------------------------------------ public API

    def quote(self, base: str, quote: str) -> FxQuote:
        base, quote = base.upper(), quote.upper()
        with self._lock:
            self._ensure()
            table = self._table or {}
            if base not in table or quote not in table:
                missing = base if base not in table else quote
                raise UnknownCurrency(f"No exchange rate available for {missing}")
            rate = table[quote] / table[base]
            return FxQuote(base, quote, rate, self._source, self._as_of, self._stale)

    def convert(self, amount: float, from_ccy: str, to_ccy: str) -> float:
        if from_ccy.upper() == to_ccy.upper():
            return amount
        return amount * self.quote(from_ccy, to_ccy).rate

    def snapshot(self) -> dict:
        with self._lock:
            self._ensure()
            return {"base": BASE, "source": self._source, "as_of": self._as_of, "stale": self._stale,
                    "rates": {k: round(v, 8) for k, v in sorted((self._table or {}).items())}}

    def refresh(self) -> dict:
        with self._lock:
            self._table = None
            with session_scope() as s:
                s.execute(delete(FxRate).where(FxRate.base == BASE))
        return self.snapshot()


fx = FxService()
