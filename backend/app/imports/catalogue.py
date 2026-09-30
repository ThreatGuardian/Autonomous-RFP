"""Company data import: catalogue, prices, stock, HSN and GST from CSV, Excel or Tally.

The flow is *preview then commit*. ``preview`` reads the file, maps its columns,
parses every row, matches it to an existing product (SKU, then MPN, then exact
name), and reports what would be created, updated or skipped, with row-level
issues. ``commit`` applies the same plan, writes a price version for every price
or stock change, and records the batch so the history can be audited.

Category, specifications and keywords for new products are derived from the
item name by rules and the trained category classifier, so a plain accounting
export ("HP 250 G10 i5 16GB 512GB SSD 15.6") becomes a searchable catalogue
entry without manual tagging.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ImportBatch, PriceVersion, Product
from app.imports.tabular import Mapping, Table, map_headers, parse_int, parse_months, parse_number, read_table

FIELDS: dict[str, list[str]] = {
    "sku": ["sku", "item code", "product code", "sku code", "code", "alias", "part code", "internal code"],
    "mpn": ["mpn", "part number", "part no", "model number", "model no", "manufacturer part number", "oem part no", "model"],
    "name": ["name", "item name", "product name", "stock item", "stock item name", "item", "product", "particulars",
             "item description"],
    "brand": ["brand", "make", "manufacturer", "oem", "brand name"],
    "category": ["category", "stock group", "item group", "group", "product category", "sub category", "type"],
    "hsn": ["hsn", "hsn code", "hsn sac", "hsn sac code", "sac", "hsn/sac"],
    "gst": ["gst", "gst rate", "gst %", "tax rate", "igst rate", "igst", "gst rate %", "tax %"],
    "unit_cost": ["unit cost", "cost", "landed cost", "purchase price", "purchase rate", "buying price", "dealer price",
                  "cost price", "net cost", "standard cost", "rate"],
    "list_price": ["list price", "selling price", "sale price", "sales rate", "price", "standard price", "mrp",
                   "retail price", "selling rate"],
    "stock_qty": ["stock", "stock qty", "closing stock", "closing qty", "closing quantity", "qty", "quantity",
                  "on hand", "available", "inventory", "balance qty"],
    "lead_time_days": ["lead time", "lead time days", "delivery days", "lead days", "supply days"],
    "warranty_months": ["warranty", "warranty months", "warranty period", "oem warranty"],
    "min_margin_pct": ["min margin", "minimum margin", "min margin %", "margin floor", "floor margin"],
    "unit": ["unit", "uom", "units", "base unit", "base units"],
    "description": ["description", "details", "specification", "specifications", "remarks"],
}

# Accounting groups and free text -> catalogue category (checked before the classifier).
_GROUP_RULES: list[tuple[str, str]] = [
    (r"graphics? card|\bgpu\b|\brtx\b|\bgtx\b|processor|\bcpu chip\b|\bram\b|memory module|motherboard|\bsmps\b|"
     r"power supply|\bpsu\b|component", "component"),
    (r"head ?phone|head ?set|ear ?phone|speaker|audio", "audio"),
    (r"key ?board|mouse|mice|webcam|web cam|peripheral|accessor", "peripheral"),
    (r"laptop|notebook|macbook|ultrabook", "laptop"),
    (r"workstation", "workstation"),
    (r"desktop|\bpc\b|all.in.one|tower|mac mini|imac", "desktop"),
    (r"monitor|display|\bled\b|\blcd\b", "monitor"),
    (r"\bssd\b|\bhdd\b|hard dis[ck]|pen ?drive|flash drive|storage media", "storage_media"),
    (r"\bups\b|inverter|battery backup", "power"),
    (r"printer|scanner", "printer"),
    (r"projector", "av"),
    (r"switch", "network_switch"),
    (r"router|wi-?fi", "wireless"),
    (r"software|licen[cs]e|antivirus|office", "software"),
    (r"service|installation|amc|maintenance", "service"),
]
KNOWN_CATEGORIES = {c for _, c in _GROUP_RULES}
GST_BY_TAX_CATEGORY = {"goods_standard": 18.0, "software": 18.0, "services": 18.0}


def infer_category(*texts: str) -> tuple[str | None, str]:
    for text in texts:
        t = (text or "").lower()
        if t.replace(" ", "_") in KNOWN_CATEGORIES:
            return t.replace(" ", "_"), "column"
        for pattern, cat in _GROUP_RULES:
            if re.search(pattern, t):
                return cat, "rule"
    joined = " ".join(t for t in texts if t)
    if not joined.strip():
        return None, "none"
    from app.ml.registry import registry

    pred = registry.category_classifier().predict_one(joined)
    return (pred.label, "model") if pred.confidence >= 0.45 else (None, "none")


def infer_specs(text: str) -> dict[str, Any]:
    t = text.lower()
    specs: dict[str, Any] = {}
    if m := re.search(r"(core (?:ultra )?[ i]?[3579][- ]?\w*|ryzen \d \w+|apple m\d\w*|xeon \w+)", t):
        specs["cpu"] = m.group(1).replace("core i", "Intel Core i").replace("ryzen", "AMD Ryzen").title() \
            .replace("Intel Core I", "Intel Core i")
    if m := re.search(r"(\d{1,3})\s*gb\s*(?:ddr\d\s*)?(?:ram|memory)", t) or re.search(r"(\d{1,3})\s*gb\b(?!\s*(?:ssd|hdd|nvme))", t):
        specs["ram_gb"] = int(m.group(1))
    if m := re.search(r"(\d+(?:\.\d+)?)\s*(tb|gb)\s*(ssd|nvme|hdd|m\.2)", t):
        size = float(m.group(1)) * (1000 if m.group(2) == "tb" else 1)
        specs["storage_gb"] = int(size)
        specs["storage_type"] = "HDD" if m.group(3) == "hdd" else "SSD"
    if m := re.search(r"(\d{2}(?:\.\d)?)\s*(?:\"|inch|in\b|-inch)", t):
        specs["screen_in"] = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
    if m := re.search(r"(\d+(?:\.\d+)?)\s*(k?va)\b", t):
        specs["capacity_va"] = int(float(m.group(1)) * (1000 if m.group(2) == "kva" else 1))
    if m := re.search(r"(rtx|gtx)\s*(a?\d{3,4}(?:\s*ti)?)", t):
        specs["gpu"] = f"NVIDIA {m.group(1).upper()} {m.group(2).upper()}"
    if "fhd" in t or "1080" in t or "full hd" in t:
        specs["resolution"] = "1920x1080"
    return specs


def _keywords(name: str, category: str | None) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) > 2][:6]
    return list(dict.fromkeys(([category.replace("_", " ")] if category else []) + words))


# --------------------------------------------------------------------------- Tally


def tally_to_table(data: bytes) -> Table:
    """Flatten a Tally ERP / TallyPrime stock-item XML export into rows."""
    root = ET.fromstring(data.decode("utf-8-sig", errors="replace").encode())
    rows: list[dict[str, str]] = []
    for item in root.iter("STOCKITEM"):
        def txt(tag: str) -> str:
            el = item.find(f".//{tag}")
            return (el.text or "").strip() if el is not None and el.text else ""

        gst = ""
        for rate in item.iter("RATEDETAILS.LIST"):
            head = (rate.findtext("GSTRATEDUTYHEAD") or "").lower()
            if "integrated" in head or "igst" in head:
                gst = (rate.findtext("GSTRATE") or "").strip()
        cost = item.find(".//STANDARDCOSTLIST.LIST/RATE")
        price = item.find(".//STANDARDPRICELIST.LIST/RATE")
        rows.append({
            "Item Name": item.get("NAME") or txt("NAME"),
            "Alias": txt("ALIAS") or (item.findtext(".//NAME.LIST/NAME[2]") or ""),
            "Part No": txt("MAILINGNAME") or txt("PARTNUMBER"),
            "Stock Group": txt("PARENT"),
            "Base Unit": txt("BASEUNITS"),
            "Closing Qty": txt("CLOSINGBALANCE") or txt("OPENINGBALANCE"),
            "Purchase Rate": (cost.text if cost is not None and cost.text else txt("OPENINGRATE")),
            "Selling Rate": price.text if price is not None and price.text else "",
            "HSN Code": txt("HSNCODE"),
            "GST Rate": gst,
            "Description": txt("DESCRIPTION"),
        })
    headers = list(rows[0]) if rows else []
    return Table(headers, rows, "Tally stock items", 0)


# --------------------------------------------------------------------------- plan


@dataclass
class RowPlan:
    row: int
    action: str  # create | update | unchanged | skip
    sku: str | None
    name: str
    values: dict[str, Any] = field(default_factory=dict)
    changes: dict[str, list[Any]] = field(default_factory=dict)  # field -> [old, new]
    issues: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ImportPlan:
    filename: str
    format: str
    mapping: Mapping
    rows: list[RowPlan]
    sheet: str | None = None

    def counts(self) -> dict[str, int]:
        out = {"create": 0, "update": 0, "unchanged": 0, "skip": 0}
        for r in self.rows:
            out[r.action] += 1
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename, "format": self.format, "sheet": self.sheet,
            "mapping": self.mapping.fields, "unmapped": self.mapping.unmapped, "counts": self.counts(),
            "rows": [r.as_dict() for r in self.rows],
            "issues": sum(len(r.issues) for r in self.rows),
        }


def _load(filename: str, data: bytes) -> tuple[Table, str]:
    name = filename.lower()
    if name.endswith(".xml") or data.lstrip()[:200].upper().find(b"<ENVELOPE") >= 0:
        return tally_to_table(data), "tally"
    return read_table(filename, data), "xlsx" if name.endswith((".xlsx", ".xlsm")) else "csv"


_TRACKED = ("name", "brand", "category", "hsn", "gst_rate_pct", "unit_cost", "list_price", "stock_qty", "lead_time_days",
            "warranty_months", "min_margin_pct", "unit", "description")


def preview(db: Session, filename: str, data: bytes) -> ImportPlan:
    table, fmt = _load(filename, data)
    mapping = map_headers(table.headers, FIELDS)
    products = list(db.scalars(select(Product)))
    by_sku = {p.sku.lower(): p for p in products}
    by_mpn = {p.mpn.lower(): p for p in products}
    by_name = {p.name.lower(): p for p in products}
    plans: list[RowPlan] = []
    seen: set[str] = set()
    for i, raw in enumerate(table.rows, start=table.header_row + 1):
        get = lambda f: mapping.get(raw, f)  # noqa: E731
        name, sku, mpn = get("name"), get("sku"), get("mpn")
        plan = RowPlan(row=i, action="skip", sku=sku or None, name=name or sku or mpn or "(blank)")
        if not (name or sku or mpn):
            plan.issues.append({"field": "name", "severity": "error", "message": "Row has no item name, code or part number."})
            plans.append(plan)
            continue
        existing = by_sku.get(sku.lower()) if sku else None
        existing = existing or (by_mpn.get(mpn.lower()) if mpn else None) or (by_name.get(name.lower()) if name else None)
        v: dict[str, Any] = {}
        if name:
            v["name"] = name
        if get("brand"):
            v["brand"] = get("brand")
        if get("hsn"):
            hsn = re.sub(r"\D", "", get("hsn"))
            if len(hsn) not in (4, 6, 8):
                plan.issues.append({"field": "hsn", "severity": "warning", "message": f"HSN '{get('hsn')}' should have 4, 6 or 8 digits."})
            v["hsn"] = hsn or None
        for fld, parse in (("unit_cost", parse_number), ("list_price", parse_number), ("gst", parse_number),
                           ("stock_qty", parse_int), ("lead_time_days", parse_int), ("warranty_months", parse_months),
                           ("min_margin_pct", parse_number)):
            text = get(fld)
            if not text:
                continue
            val = parse(text)
            if val is None:
                plan.issues.append({"field": fld, "severity": "warning", "message": f"Could not read '{text}' as a number."})
                continue
            v["gst_rate_pct" if fld == "gst" else fld] = val
        if "gst_rate_pct" in v and v["gst_rate_pct"] not in (0, 0.25, 3, 5, 12, 18, 28, 40):
            plan.issues.append({"field": "gst", "severity": "warning", "message": f"GST rate {v['gst_rate_pct']}% is not a standard slab."})
        if get("unit"):
            v["unit"] = get("unit").lower().rstrip(".")[:16]
        if get("description"):
            v["description"] = get("description")
        cat, how = infer_category(get("category"), name, get("description"))
        if cat:
            v["category"] = cat
            if how == "model":
                plan.issues.append({"field": "category", "severity": "info", "message": f"Category '{cat}' inferred from the item name."})

        cost, price = v.get("unit_cost"), v.get("list_price")
        if cost is not None and price is None and existing is None:
            plan.issues.append({"field": "list_price", "severity": "info", "message": "No selling price; set at cost + 15%."})
            v["list_price"] = price = round(cost * 1.15, 2)
        if cost is not None and price is not None and price < cost:
            plan.issues.append({"field": "list_price", "severity": "warning", "message": f"Selling price {price:,.0f} is below cost {cost:,.0f}."})

        if existing is not None:
            plan.sku = existing.sku
            key = existing.sku.lower()
            if key in seen:
                plan.issues.append({"field": "sku", "severity": "error", "message": "Duplicate row for the same product."})
                plans.append(plan)
                continue
            seen.add(key)
            for fld in _TRACKED:
                if fld in v and v[fld] != getattr(existing, fld) and not (fld == "category" and how == "model"):
                    old = getattr(existing, fld)
                    if isinstance(old, float) and isinstance(v[fld], (int, float)) and abs(old - v[fld]) < 0.005:
                        continue
                    plan.changes[fld] = [old, v[fld]]
            for fld in ("unit_cost", "list_price"):
                if fld in plan.changes and plan.changes[fld][0]:
                    old, new = plan.changes[fld]
                    pct = 100 * (new - old) / old
                    if abs(pct) >= 25:
                        plan.issues.append({"field": fld, "severity": "warning",
                                            "message": f"{fld.replace('_', ' ').capitalize()} changes by {pct:+.0f}% ({old:,.0f} → {new:,.0f})."})
            plan.action = "update" if plan.changes else "unchanged"
            plan.values = {k: v[k] for k in plan.changes}
        else:
            missing = [f for f in ("name", "unit_cost") if f not in v]
            if missing:
                plan.issues.append({"field": missing[0], "severity": "error",
                                    "message": f"New product needs {' and '.join(m.replace('_', ' ') for m in missing)}."})
                plans.append(plan)
                continue
            if "category" not in v:
                plan.issues.append({"field": "category", "severity": "error", "message": "Could not work out the product category."})
                plans.append(plan)
                continue
            new_sku = sku or f"IMP-{re.sub(r'[^A-Z0-9]', '', (mpn or name).upper())[:14]}"
            if new_sku.lower() in by_sku or new_sku.lower() in seen:
                new_sku = f"{new_sku[:26]}-{i}"
            seen.add(new_sku.lower())
            text = " ".join(filter(None, [name, get("description")]))
            v.update(sku=new_sku, mpn=mpn or new_sku, brand=v.get("brand") or name.split()[0],
                     specs=infer_specs(text), keywords=_keywords(name, v["category"]),
                     description=v.get("description") or name)
            plan.action, plan.sku, plan.values = "create", new_sku, v
        plans.append(plan)
    return ImportPlan(filename, fmt, mapping, plans, table.sheet)


def commit(db: Session, plan: ImportPlan, actor: str = "Reviewer") -> ImportBatch:
    counts = plan.counts()
    batch = ImportBatch(filename=plan.filename, format=plan.format, rows=len(plan.rows), created=counts["create"],
                        updated=counts["update"], unchanged=counts["unchanged"], skipped=counts["skip"],
                        mapping=plan.mapping.fields, actor=actor,
                        issues=[{"row": r.row, **i} for r in plan.rows for i in r.issues])
    db.add(batch)
    db.flush()
    now = datetime.now(timezone.utc)
    for r in plan.rows:
        if r.action == "create":
            v = dict(r.values)
            v.pop("gst", None)
            product = Product(**{k: val for k, val in v.items() if hasattr(Product, k)}, price_updated_at=now)
            db.add(product)
            db.flush()
        elif r.action == "update":
            product = db.scalar(select(Product).where(Product.sku == r.sku))
            if product is None:
                continue
            for fld, (_, new) in r.changes.items():
                setattr(product, fld, new)
            if {"unit_cost", "list_price", "stock_qty"} & set(r.changes):
                product.price_updated_at = now
        else:
            continue
        if r.action == "create" or {"unit_cost", "list_price", "stock_qty"} & set(r.changes):
            db.add(PriceVersion(sku=product.sku, unit_cost=product.unit_cost, list_price=product.list_price,
                                stock_qty=product.stock_qty, effective_from=now, source=f"Import: {plan.filename}",
                                batch_id=batch.id))
    from app.ml.registry import registry

    if counts["create"]:
        registry.forget("category-classifier")
    return batch
