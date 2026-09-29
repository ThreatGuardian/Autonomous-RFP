"""Populate the internal pricing database from the JSON seed files.

The seeder is idempotent: tables that already contain rows are left untouched,
so user edits made through the catalogue screens survive restarts.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.db.models import Customer, DealHistory, PriceTier, Product, TaxRule, ValueAdd
from app.db.session import create_schema, session_scope

SEGMENTS = ["enterprise", "smb", "public", "education", "healthcare"]
DEAL_CATEGORIES = [
    "laptop", "desktop", "monitor", "network_switch", "wireless", "firewall",
    "server", "storage", "power", "software", "peripheral", "service",
]
# Price sensitivity by buyer segment: public and education tenders are awarded
# largely on price, enterprise buyers weigh service and risk more heavily.
SEGMENT_PRICE_SENSITIVITY = {"public": 1.35, "education": 1.2, "smb": 1.0, "healthcare": 0.85, "enterprise": 0.75}


def load_json(name: str) -> Any:
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def _empty(session: Session, model: type) -> bool:
    return session.scalar(select(func.count()).select_from(model)) == 0


def seed_catalogue(session: Session) -> None:
    if _empty(session, Product):
        for row in load_json("catalog.json"):
            session.add(Product(**row))
    if _empty(session, PriceTier):
        for category, tiers in load_json("price_tiers.json").items():
            for min_qty, pct in tiers:
                session.add(PriceTier(category=category, min_qty=min_qty, discount_pct=pct))
    if _empty(session, ValueAdd):
        for row in load_json("value_adds.json"):
            session.add(ValueAdd(**row))


def seed_customers(session: Session) -> None:
    if _empty(session, Customer):
        for row in load_json("customers.json"):
            session.add(Customer(**row))


def seed_tax_rules(session: Session) -> None:
    if _empty(session, TaxRule):
        for row in load_json("tax_rules.json"):
            session.add(TaxRule(**row))


def _true_win_logit(
    price_ratio: float, warranty_delta: int, lead_delta: int, bundled: bool, repeat: bool, segment: str
) -> float:
    """Latent market behaviour used to synthesise the historical bid ledger.

    The trained model never sees this function; it only sees the sampled
    outcomes, exactly as it would with a real CRM export.
    """
    sensitivity = SEGMENT_PRICE_SENSITIVITY[segment]
    logit = 0.35
    logit -= 11.0 * sensitivity * (price_ratio - 1.0)
    logit += 0.035 * warranty_delta
    logit -= 0.045 * lead_delta
    logit += 0.55 if bundled else 0.0
    logit += 0.7 if repeat else 0.0
    return logit


def generate_deal_history(n: int = 2400, seed: int = 20260929) -> list[DealHistory]:
    rng = random.Random(seed)
    start = datetime(2023, 4, 1, tzinfo=timezone.utc)
    rows: list[DealHistory] = []
    for i in range(n):
        segment = rng.choices(SEGMENTS, weights=[3, 4, 2, 3, 2])[0]
        category = rng.choice(DEAL_CATEGORIES)
        price_ratio = max(0.8, min(1.35, rng.gauss(1.03, 0.08)))
        warranty_delta = rng.choice([-12, 0, 0, 0, 12, 12, 24])
        lead_delta = int(rng.gauss(0, 5))
        bundled = rng.random() < 0.3
        repeat = rng.random() < 0.28
        p_win = 1.0 / (1.0 + math.exp(-_true_win_logit(price_ratio, warranty_delta, lead_delta, bundled, repeat, segment)))
        won = rng.random() < p_win
        rows.append(
            DealHistory(
                closed_on=start + timedelta(days=int(i * 900 / n)),
                customer_segment=segment,
                category=category,
                quantity=max(1, int(rng.lognormvariate(2.6, 0.9))),
                price_ratio=round(price_ratio, 4),
                margin_pct=round(max(1.0, rng.gauss(14, 5)), 2),
                warranty_delta_months=warranty_delta,
                lead_time_delta_days=lead_delta,
                bundled_value_add=bundled,
                repeat_customer=repeat,
                won=won,
            )
        )
    return rows


def seed_history(session: Session) -> None:
    if _empty(session, DealHistory):
        session.add_all(generate_deal_history())


def seed_all() -> None:
    create_schema()
    with session_scope() as session:
        seed_catalogue(session)
        seed_customers(session)
        seed_tax_rules(session)
        seed_history(session)


if __name__ == "__main__":  # pragma: no cover
    seed_all()
    print("Database seeded.")
