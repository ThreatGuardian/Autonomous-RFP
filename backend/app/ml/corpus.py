"""Synthetic training corpora.

Procurement documents follow strongly conventional phrasing, so a template
grammar with randomised slot fillers produces a realistic, varied corpus.
Templates are partitioned per class into *train* and *held-out* families so the
reported accuracy measures generalisation to unseen phrasings, not memorisation.
"""

from __future__ import annotations

import random
import re

CLAUSE_LABELS = [
    "line_item", "delivery", "payment", "warranty_support", "compliance", "evaluation", "submission", "scope",
]

SLOTS: dict[str, list[str]] = {
    "qty": ["2", "4", "5", "6", "10", "12", "15", "20", "24", "25", "30", "40", "50", "60", "75", "100", "120", "150",
            "200", "250", "ten", "twenty", "forty", "fifty", "one hundred", "twenty-five", "a dozen"],
    "item": ["business laptops", "notebooks", "desktop computers", "24-inch monitors", "27 inch 4K displays",
             "48-port PoE switches", "Wi-Fi 6 access points", "next-generation firewalls", "rack servers",
             "tower servers", "8-bay NAS appliances", "online UPS units 3kVA", "42U server racks", "Cat6 cable boxes",
             "wireless keyboard and mouse sets", "USB headsets", "docking stations", "network laser printers",
             "video conferencing bars", "Microsoft 365 licences", "endpoint protection licences",
             "backup software subscriptions", "mini PCs", "CAD workstations", "patch panels", "VPN routers"],
    "spec": ["with 16GB RAM and 512GB SSD", "Intel Core i5 or better", "minimum 32 GB memory", "with PoE+ support",
             "4K resolution, USB-C", "dual power supply", "Windows 11 Pro preinstalled", "with 3 years warranty",
             "rack mountable", "minimum 8 TB usable capacity", "with height adjustable stand", "Core i7, 1TB SSD",
             "2x Xeon Silver, 64GB", "Wi-Fi 6 with 4x4 MIMO", "10 Gbps firewall throughput", ""],
    "place": ["our Pune campus", "the head office in Mumbai", "the Bengaluru data centre", "our Dubai warehouse",
              "the Singapore office", "our London headquarters", "the Berlin plant", "all four branch sites",
              "the district office in Sacramento", "the hospital main block", "Toronto City Hall annex"],
    "days": ["15", "21", "30", "45", "60", "7", "four weeks", "six weeks", "10 business days"],
    "date": ["15 November 2026", "30/10/2026", "2026-11-20", "December 5, 2026", "31st October 2026", "12 Jan 2027"],
    "pct": ["30", "40", "50", "60", "70", "20", "25", "10"],
    "cert": ["ISO 9001", "ISO/IEC 27001", "ISO 14001", "GDPR", "SOC 2 Type II", "BIS certification", "CE marking",
             "the DPDP Act 2023", "RoHS", "ENERGY STAR", "EPEAT Gold"],
    "months": ["12", "24", "36", "48", "60", "three years", "five years"],
    "incoterm": ["DDP", "DAP", "CIF", "FOB", "EXW", "FCA"],
    "currency": ["INR", "USD", "EUR", "GBP", "AED", "SGD", "Indian Rupees", "US dollars", "euros"],
    "org": ["the University", "the Hospital", "the Authority", "the Company", "the District", "the Purchaser", "the Client"],
    "email": ["procurement@example.org", "tenders@city.gov", "it.purchase@company.com", "bids@hospital.org"],
}

# (train templates, held-out templates) per label
TEMPLATES: dict[str, tuple[list[str], list[str]]] = {
    "line_item": (
        [
            "Supply of {qty} {item} {spec}.",
            "{qty} x {item} {spec}",
            "Item {n}: {item}, quantity {qty}",
            "We require {qty} {item} {spec}.",
            "Quantity required: {qty} nos of {item}.",
            "Provide {qty} units of {item} {spec}.",
            "{item} {spec} - Qty: {qty}",
            "Lot {n}: {qty} {item}",
            "Procurement of {qty} {item} {spec} for staff use.",
            "{n}. {item} ({spec}) - {qty} units",
        ],
        [
            "The bidder shall quote for {qty} {item} {spec}.",
            "Requirement: {item}, {qty} pieces, {spec}",
            "Please price {qty} {item}.",
            "{qty} nos. {item} {spec} are needed.",
        ],
    ),
    "delivery": (
        [
            "Delivery must be completed within {days} days of the purchase order.",
            "All goods shall be delivered to {place}.",
            "Prices should be quoted on a {incoterm} basis to {place}.",
            "The supplier is responsible for freight, insurance and unloading at {place}.",
            "Delivery schedule: phased delivery over {days}.",
            "Goods must arrive at {place} no later than {date}.",
            "Shipping terms: {incoterm} {place}.",
            "Partial shipments are acceptable provided the full order is delivered within {days} days.",
        ],
        [
            "Consignment to be delivered at {place} within {days} from award.",
            "Lead time for delivery should not exceed {days}.",
            "Incoterm {incoterm} applies; destination is {place}.",
        ],
    ),
    "payment": (
        [
            "Payment will be made within {days} days of receipt of a valid invoice.",
            "Quote all prices in {currency}.",
            "{pct}% advance payment against purchase order, balance on delivery.",
            "Invoices shall be raised in {currency} and settled by bank transfer.",
            "Payment terms: net {days} from invoice date.",
            "No advance payment will be released by {org}.",
            "Prices must be inclusive of all taxes and duties and quoted in {currency}.",
            "Milestone payments: {pct}% on delivery and the remainder on installation.",
        ],
        [
            "The commercial offer must be denominated in {currency}.",
            "{org} settles invoices {days} days after acceptance.",
            "Kindly state your payment expectations; {pct} percent advance is not permitted.",
        ],
    ),
    "warranty_support": (
        [
            "All equipment must carry a minimum {months} months comprehensive warranty.",
            "The vendor shall provide on-site support with next business day response.",
            "Annual maintenance contract for {months} months should be quoted separately.",
            "Warranty must cover parts, labour and on-site service.",
            "Faulty units must be replaced within {days} days.",
            "Support desk must be reachable during business hours with a {days} hour response.",
            "Provide details of your service level agreement and escalation matrix.",
            "Extended warranty options up to {months} months are preferred.",
            "Minimum {months} warranty on all hardware.",
            "{months} months onsite warranty required for all {item}.",
            "Warranty: {months}, comprehensive, next business day.",
        ],
        [
            "Onsite comprehensive warranty of {months} is mandatory for every device.",
            "Describe your after-sales support model including response times.",
            "Hardware failures during the warranty period must be rectified at no cost.",
        ],
    ),
    "compliance": (
        [
            "The bidder must hold a valid {cert} certificate.",
            "Products must comply with {cert}.",
            "Bidders shall submit proof of {cert} along with the technical bid.",
            "Only OEM-authorised partners may participate; attach the authorisation letter.",
            "The supplier must comply with all data protection obligations including {cert}.",
            "All equipment should meet {cert} requirements.",
            "Vendors must not be blacklisted by any government agency.",
            "Provide a copy of your GST registration and PAN.",
        ],
        [
            "Evidence of {cert} compliance is a mandatory eligibility requirement.",
            "Certificates such as {cert} must be enclosed.",
            "Bidders lacking {cert} will be disqualified.",
        ],
    ),
    "evaluation": (
        [
            "Bids will be evaluated on price ({pct}%) and technical merit.",
            "The contract will be awarded to the lowest compliant bidder.",
            "Evaluation criteria: price {pct}%, delivery {pct}%, support {pct}%.",
            "{org} reserves the right to accept or reject any bid.",
            "Technical proposals scoring below {pct} points will not be considered.",
            "Past experience with similar projects will carry weightage in evaluation.",
            "Award will be made on a total cost of ownership basis.",
        ],
        [
            "Scoring: commercial {pct} percent, technical {pct} percent.",
            "L1 bidder among technically qualified vendors will be selected.",
            "{org} will shortlist vendors based on value for money.",
        ],
    ),
    "submission": (
        [
            "Proposals must be submitted by {date}.",
            "Send your quotation to {email} before {date}.",
            "The last date for submission of bids is {date}.",
            "Queries should be addressed to {email}.",
            "Submit the technical and commercial bids in separate sealed envelopes.",
            "Late submissions will not be accepted.",
            "Bids must remain valid for {days} days from the closing date.",
            "Responses should be sent in PDF format to {email}.",
        ],
        [
            "Closing date for responses: {date}.",
            "Quotations reaching {org} after {date} will be rejected.",
            "Contact {email} for clarifications before {date}.",
        ],
    ),
    "scope": (
        [
            "{org} is modernising its IT infrastructure across all sites.",
            "This request for proposal covers the refresh of end-user computing.",
            "The purpose of this RFP is to identify a qualified supplier.",
            "{org} operates {qty} locations with around {qty} staff.",
            "Background: the current equipment is over five years old.",
            "The project aims to improve connectivity and security for staff.",
            "This document describes the requirements of {org}.",
            "The selected partner will work closely with our IT department.",
        ],
        [
            "{org} invites proposals from experienced IT suppliers.",
            "Our organisation is expanding and needs to equip a new office.",
            "The objective is to standardise hardware across departments.",
        ],
    ),
}

_PREFIXES = ["", "", "", "Note: ", "Important: ", "The bidder shall note that ", "Clause 4.2 ", "(a) ", "- "]


def _fill(template: str, rng: random.Random) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key == "n":
            return str(rng.randint(1, 12))
        return rng.choice(SLOTS[key])

    text = re.sub(r"\{(\w+)\}", repl, template)
    text = rng.choice(_PREFIXES) + text
    if rng.random() < 0.15:
        text = text.upper() if rng.random() < 0.3 else text.lower()
    return re.sub(r"\s+", " ", text).strip()


def clause_corpus(per_label: int = 450, *, held_out: bool = False, seed: int = 11) -> tuple[list[str], list[str]]:
    rng = random.Random(seed + (1000 if held_out else 0))
    texts, labels = [], []
    for label, (train_t, test_t) in TEMPLATES.items():
        pool = test_t if held_out else train_t
        for _ in range(per_label):
            texts.append(_fill(rng.choice(pool), rng))
            labels.append(label)
    return texts, labels


# --------------------------------------------------------------------------- product categories

CATEGORY_PHRASES: dict[str, list[str]] = {
    "laptop": ["laptop", "notebook", "ultrabook", "business laptop", "portable computer", "thinkpad", "latitude",
               "elitebook", "probook", "macbook", "student laptops", "faculty notebooks", "2-in-1 laptop"],
    "desktop": ["desktop", "desktop computer", "pc", "tower pc", "all in one pc", "mini pc", "small form factor pc",
                "optiplex", "thinkcentre", "lab computers", "office pcs", "thin client"],
    "workstation": ["workstation", "cad workstation", "engineering workstation", "rendering workstation",
                    "gpu workstation", "precision workstation", "design workstation"],
    "monitor": ["monitor", "display", "lcd screen", "led monitor", "4k monitor", "24 inch monitor", "27 inch display",
                "curved monitor", "screen", "dual monitors"],
    "network_switch": ["switch", "network switch", "poe switch", "access switch", "core switch", "managed switch",
                       "48 port switch", "24 port gigabit switch", "layer 3 switch", "catalyst switch"],
    "wireless": ["access point", "wifi access point", "wireless ap", "wi-fi 6", "wireless network", "ceiling ap",
                 "wlan", "meraki ap", "unifi"],
    "firewall": ["firewall", "utm appliance", "next generation firewall", "ngfw", "network security appliance",
                 "fortigate", "perimeter security"],
    "router": ["router", "vpn router", "gateway router", "branch router", "sd-wan router", "multi wan router"],
    "server": ["server", "rack server", "tower server", "virtualization host", "database server", "file server",
               "poweredge", "proliant", "compute node", "application server"],
    "storage": ["nas", "network attached storage", "san", "storage array", "backup storage", "file storage",
                "synology", "storage appliance"],
    "storage_media": ["hard drive", "hdd", "ssd", "solid state drive", "hard disk", "nas drive", "8tb drive"],
    "power": ["ups", "uninterruptible power supply", "online ups", "battery backup", "pdu", "power distribution unit",
              "kva ups", "inverter"],
    "rack": ["rack", "server rack", "42u rack", "network cabinet", "enclosure", "wall mount rack"],
    "cabling": ["cat6 cable", "network cabling", "structured cabling", "patch panel", "patch cord", "lan cable",
                "ethernet cable", "fibre patch cord", "cable box"],
    "peripheral": ["keyboard", "mouse", "keyboard mouse combo", "webcam", "headset", "docking station", "usb dock",
                   "speakerphone", "headphones"],
    "printer": ["printer", "laser printer", "multifunction printer", "mfp", "network printer", "scanner printer"],
    "av": ["video conferencing", "video bar", "conference room system", "meeting room camera", "vc system",
           "room kit", "interactive display"],
    "software": ["licence", "license", "subscription", "microsoft 365", "office 365", "antivirus", "endpoint protection",
                 "backup software", "windows server licence", "security subscription", "saas seats"],
    "service": ["installation", "configuration service", "deployment service", "implementation", "migration service",
                "professional services", "engineer days", "onsite setup", "commissioning", "training"],
}

_QUALIFIERS = ["", "", "new", "enterprise grade", "high performance", "energy efficient", "branded", "genuine",
               "business class", "rugged", "compact", "latest generation"]
_WRAPPERS = ["{q} {p}", "{p}", "{p} {s}", "supply of {q} {p}", "{n} {p}", "{n} x {q} {p} {s}", "{p} for our office",
             "procure {p}", "{q} {p} with warranty"]
_SPECLETS = ["16gb ram", "512gb ssd", "i5", "i7", "poe+", "4k", "dual psu", "1u", "wifi 6", "3 year warranty",
             "usb-c", "24 port", "rack mount", "1500va", "per user", "annual", "cat6", ""]


def category_corpus(catalog: list[dict], per_category: int = 160, seed: int = 5) -> tuple[list[str], list[str]]:
    """Line-item phrases labelled with product category, seeded from the catalogue itself."""
    rng = random.Random(seed)
    bank: dict[str, list[str]] = {c: list(p) for c, p in CATEGORY_PHRASES.items()}
    for prod in catalog:
        bank.setdefault(prod["category"], []).extend(
            [prod["name"].lower(), f"{prod['brand']} {prod['category'].replace('_', ' ')}".lower(), *prod["keywords"]]
        )
    texts, labels = [], []
    for category, phrases in bank.items():
        for _ in range(per_category):
            text = rng.choice(_WRAPPERS).format(
                q=rng.choice(_QUALIFIERS), p=rng.choice(phrases), s=rng.choice(_SPECLETS), n=rng.randint(1, 300)
            )
            texts.append(re.sub(r"\s+", " ", text).strip())
            labels.append(category)
    return texts, labels
