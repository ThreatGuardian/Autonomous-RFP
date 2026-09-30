"""Generate the Data Care Corp data set (mock company used for the end-to-end trial).

Data Care Corp is a Pune-based wholesale dealer of computers, components and
consumer electronics. This script writes everything the system knows about it
into ``backend/app/data/companies/datacare/``:

* ``company.json``      profile, statutory numbers, MSME status, certifications, credentials
* ``catalog.json``      the product catalogue with landed cost, list price, stock and HSN
* ``customers.json``    known customers
* ``market.json``       competitors (Amazon Business, Flipkart Wholesale, HP World,
                        Apple authorised store, Dell Exclusive Store) and street prices
* ``competitor_quotes.csv``  dated price observations collected by the sales team
* ``award_history.csv``      past public awards (GeM style) for the same kind of items
* ``value_adds.json``, ``price_tiers.json`` and the ``knowledge/`` base

All figures are illustrative. Prices are exclusive of GST, in Indian rupees.

    python scripts/make_datacare.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "companies" / "datacare"
USD_INR = 88.2
TODAY = date(2026, 9, 30)

# --------------------------------------------------------------------------- company

COMPANY = {
    "name": "Data Care Corp Pvt. Ltd.",
    "short_name": "Data Care Corp",
    "tagline": "Computers, components and electronics, wholesale.",
    "address_lines": ["Plot 18, Sector 10, PCNTDA Industrial Area", "Bhosari, Pune 411026", "Maharashtra, India"],
    "country": "IN",
    "region": "Maharashtra",
    "tax_id_label": "GSTIN",
    "tax_id": "27AAFCD4417M1Z3",
    "base_currency": "INR",
    "email": "tenders@datacarecorp.in",
    "phone": "+91 20 2712 4455",
    "website": "www.datacarecorp.in",
    "quote_validity_days": 45,
    "bank": {"name": "State Bank of India, Bhosari Industrial Estate", "account": "38912004571", "ifsc": "SBIN0007785",
             "swift": "SBININBB"},
    "signatory": {"name": "Rohan Deshmukh", "title": "Head – Institutional Sales", "email": "tenders@datacarecorp.in"},
    "profile": {
        "legal_name": "Data Care Corp Private Limited",
        "constitution": "Private limited company (Companies Act, 2013)",
        "incorporated_on": "2009-02-11",
        "cin": "U51909PN2009PTC133407",
        "pan": "AAFCD4417M",
        "gstin": "27AAFCD4417M1Z3",
        "msme": {"udyam_number": "UDYAM-MH-26-0017742", "category": "Small", "valid": True,
                 "note": "Small enterprise (trading) registered on Udyam; eligible for EMD exemption and MSE purchase preference."},
        "turnover_inr": {"2022-23": 382000000, "2023-24": 441000000, "2024-25": 518000000, "2025-26": 596000000},
        "turnover_segments_pct": {"it hardware supply": 88, "computer components": 31, "consumer electronics": 12,
                                  "services": 4},
        "net_worth_inr": 96000000,
        "net_worth_as_of": "2026-03-31",
        "employees": 58,
        "certified_engineers": 9,
        "certifications": [
            {"name": "ISO 9001:2015", "standard": "ISO 9001",
             "scope": "Wholesale trading, supply and after-sales service of computers, components and electronics",
             "valid_until": "2028-01-31"},
            {"name": "ISO 14001:2015", "standard": "ISO 14001", "scope": "Environmental management (e-waste handling)",
             "valid_until": "2027-06-30"},
        ],
        "oem_authorisations": [
            "HP", "Dell", "Lenovo", "Acer", "Asus", "Apple", "Logitech", "Zebronics", "Sony", "JBL", "Jabra", "Poly",
            "Intel", "AMD", "NVIDIA", "Zotac", "MSI", "Gigabyte", "Samsung", "LG", "BenQ", "Crucial", "Kingston",
            "Western Digital", "Seagate", "APC", "TP-Link", "Epson", "Microsoft", "Quick Heal",
        ],
        "offices": [
            {"city": "Pune", "state": "Maharashtra", "type": "Head office and central warehouse"},
            {"city": "Mumbai", "state": "Maharashtra", "type": "Branch office (Lamington Road)"},
            {"city": "Nashik", "state": "Maharashtra", "type": "Service point"},
        ],
        "support": {"helpdesk_hours": "09:30-19:00 IST, Monday to Saturday", "helpdesk_24x7": False,
                    "onsite_response_hours": 24, "onsite_response_scope": "within Pune and PCMC limits",
                    "remote_response_hours": 4, "resolution_hours": 72},
        "blacklisted": False,
        "credentials": [
            {"client": "Engineering college, Pune", "sector": "education",
             "scope": "240 laboratory desktops with monitors, keyboards, mice and UPS", "value_inr": 16800000,
             "completed_on": "2025-07-18", "devices": {"desktop": 240, "monitor": 240, "peripheral": 480, "power": 240}},
            {"client": "Deemed university, Pune", "sector": "education",
             "scope": "Language laboratory: 120 headsets, 120 desktops and webcams", "value_inr": 9400000,
             "completed_on": "2024-11-30", "devices": {"desktop": 120, "audio": 120, "peripheral": 120}},
            {"client": "Autonomous institute, Mumbai", "sector": "education",
             "scope": "AI/ML laboratory: 60 GPU upgrades and 60 workstation-class desktops", "value_inr": 11700000,
             "completed_on": "2025-02-14", "devices": {"component": 60, "desktop": 60}},
            {"client": "Zilla Parishad schools, Pune district", "sector": "government",
             "scope": "Faculty laptops and projectors for 45 schools", "value_inr": 13200000,
             "completed_on": "2024-03-28", "devices": {"laptop": 180, "av": 45}},
            {"client": "BPO operations centre, Hinjewadi", "sector": "enterprise",
             "scope": "Seat refresh: 400 headsets, keyboards and mice", "value_inr": 4100000, "completed_on": "2025-09-05",
             "devices": {"audio": 400, "peripheral": 800}},
            {"client": "Polytechnic, Nashik", "sector": "education", "scope": "Computer lab refresh, 90 desktops",
             "value_inr": 5600000, "completed_on": "2023-06-22", "devices": {"desktop": 90}},
        ],
        "local_content": {"class": "Class-II local supplier",
                          "note": "OEM hardware sourced through authorised Indian distributors; local content 22-35% "
                                  "(assembly, staging, logistics and warranty services in India)."},
    },
}

# --------------------------------------------------------------------------- catalogue
# (sku, mpn, name, brand, category, hsn, cost, list, stock, lead, warranty, specs, keywords, description)

P: list[tuple] = [
    # laptops
    ("DCC-LT-101", "HP-9Z9X3PA-250G10", "HP 250 G10 Notebook (Core i5)", "HP", "laptop", "8471", 47800, 55900, 120, 4, 12,
     {"cpu": "Intel Core i5-1335U", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "screen_in": 15.6, "os": "Windows 11 Pro"},
     ["notebook", "laptop", "15.6 inch", "core i5", "student laptop"], "15.6-inch notebook, Core i5 13th Gen, 16 GB RAM, 512 GB SSD, Windows 11 Pro."),
    ("DCC-LT-102", "HP-A1RR7PA-440G11", "HP ProBook 440 G11 (Core Ultra 5)", "HP", "laptop", "8471", 61500, 71900, 85, 5, 12,
     {"cpu": "Intel Core Ultra 5 125U", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "screen_in": 14, "os": "Windows 11 Pro"},
     ["notebook", "business laptop", "14 inch", "faculty laptop"], "14-inch business notebook with Core Ultra 5, 16 GB RAM and 512 GB SSD."),
    ("DCC-LT-103", "DL-V3530-I5-16-512", "Dell Vostro 3530 (Core i5)", "Dell", "laptop", "8471", 49200, 57400, 140, 4, 12,
     {"cpu": "Intel Core i5-1334U", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "screen_in": 15.6, "os": "Windows 11 Pro"},
     ["notebook", "laptop", "15.6 inch", "core i5"], "15.6-inch Vostro notebook, Core i5 13th Gen, 16 GB RAM, 512 GB SSD, Windows 11 Pro."),
    ("DCC-LT-104", "DL-L3550-I7-16-512", "Dell Latitude 3550 (Core i7)", "Dell", "laptop", "8471", 72800, 84900, 40, 7, 36,
     {"cpu": "Intel Core i7-1355U", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "screen_in": 15.6, "os": "Windows 11 Pro"},
     ["notebook", "business laptop", "core i7", "latitude"], "15.6-inch Latitude with Core i7, 16 GB RAM, 512 GB SSD and 3-year warranty."),
    ("DCC-LT-105", "LN-21JK-E14G6", "Lenovo ThinkPad E14 Gen 6 (Core i5)", "Lenovo", "laptop", "8471", 58600, 68500, 70, 6, 12,
     {"cpu": "Intel Core i5-13420H", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "screen_in": 14, "os": "Windows 11 Pro"},
     ["thinkpad", "notebook", "14 inch", "business laptop"], "14-inch ThinkPad with Core i5, 16 GB RAM, 512 GB SSD."),
    ("DCC-LT-106", "LN-83ER-IPS3", "Lenovo IdeaPad Slim 3 (Core i5)", "Lenovo", "laptop", "8471", 44900, 52500, 160, 3, 12,
     {"cpu": "Intel Core i5-12450H", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "screen_in": 15.6, "os": "Windows 11 Home"},
     ["ideapad", "notebook", "student laptop", "15.6 inch"], "15.6-inch consumer notebook with Core i5 12th Gen, 16 GB RAM, 512 GB SSD."),
    ("DCC-LT-107", "AP-MC8H4HN-A", "Apple MacBook Air 13-inch (M3, 16 GB)", "Apple", "laptop", "8471", 96500, 109900, 30, 5, 12,
     {"cpu": "Apple M3", "ram_gb": 16, "storage_gb": 256, "storage_type": "SSD", "screen_in": 13.6, "os": "macOS"},
     ["macbook", "mac", "apple laptop", "13 inch"], "13.6-inch MacBook Air with Apple M3, 16 GB unified memory and 256 GB SSD."),
    ("DCC-LT-108", "AS-X1504VA-VIVO15", "Asus Vivobook 15 (Core i5)", "Asus", "laptop", "8471", 42800, 49900, 110, 4, 12,
     {"cpu": "Intel Core i5-1335U", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "screen_in": 15.6, "os": "Windows 11 Home"},
     ["vivobook", "notebook", "laptop", "15.6 inch"], "15.6-inch Vivobook, Core i5, 16 GB RAM, 512 GB SSD."),
    ("DCC-LT-109", "AC-NHQPJSI-A715", "Acer Aspire 7 (Core i5, RTX 3050)", "Acer", "laptop", "8471", 58200, 67900, 45, 6, 12,
     {"cpu": "Intel Core i5-12450H", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "screen_in": 15.6, "gpu": "RTX 3050 6GB", "os": "Windows 11 Home"},
     ["gaming laptop", "graphics laptop", "rtx laptop"], "15.6-inch laptop with discrete RTX 3050 graphics for design and entry ML work."),
    # desktops
    ("DCC-DT-201", "HP-9H1P7PA-280G9", "HP Pro Tower 280 G9 (Core i5, 16 GB)", "HP", "desktop", "8471", 45600, 53900, 210, 5, 36,
     {"cpu": "Intel Core i5-14500", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "form_factor": "tower", "os": "Windows 11 Pro"},
     ["desktop", "pc", "tower", "lab computer", "core i5"], "Tower desktop with Core i5 14th Gen, 16 GB DDR4, 512 GB NVMe SSD, Windows 11 Pro, 3-year warranty."),
    ("DCC-DT-202", "HP-A3EQ8PA-400G9", "HP ProDesk 400 G9 SFF (Core i7)", "HP", "desktop", "8471", 64800, 75900, 60, 7, 36,
     {"cpu": "Intel Core i7-14700", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "form_factor": "small form factor", "os": "Windows 11 Pro"},
     ["desktop", "sff", "small form factor", "core i7"], "Small-form-factor desktop with Core i7 14th Gen, 16 GB RAM, 512 GB SSD."),
    ("DCC-DT-203", "DL-OP7020T-I5-16", "Dell OptiPlex 7020 Tower (Core i5, 16 GB)", "Dell", "desktop", "8471", 52400, 61900, 150, 5, 36,
     {"cpu": "Intel Core i5-14500", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "form_factor": "tower", "os": "Windows 11 Pro"},
     ["optiplex", "desktop", "tower", "pc", "core i5"], "OptiPlex tower with Core i5 14th Gen, 16 GB DDR5, 512 GB SSD and 3-year on-site warranty."),
    ("DCC-DT-204", "DL-V3030-I5-8", "Dell Vostro 3030 Tower (Core i5, 8 GB)", "Dell", "desktop", "8471", 39800, 46900, 180, 4, 12,
     {"cpu": "Intel Core i5-14400", "ram_gb": 8, "storage_gb": 512, "storage_type": "SSD", "form_factor": "tower", "os": "Windows 11 Pro"},
     ["vostro", "desktop", "tower", "pc"], "Entry business tower, Core i5 14th Gen, 8 GB RAM, 512 GB SSD."),
    ("DCC-DT-205", "LN-12JB-NEO50T", "Lenovo ThinkCentre neo 50t Gen 5 (Core i5)", "Lenovo", "desktop", "8471", 47200, 55400, 130, 5, 36,
     {"cpu": "Intel Core i5-14400", "ram_gb": 16, "storage_gb": 512, "storage_type": "SSD", "form_factor": "tower", "os": "Windows 11 Pro"},
     ["thinkcentre", "desktop", "tower", "pc"], "ThinkCentre tower, Core i5 14th Gen, 16 GB RAM, 512 GB SSD, 3-year warranty."),
    ("DCC-DT-206", "LN-12U3-M70T5", "Lenovo ThinkCentre M70t Gen 5 (Core i7)", "Lenovo", "desktop", "8471", 66900, 78500, 50, 7, 36,
     {"cpu": "Intel Core i7-14700", "ram_gb": 16, "storage_gb": 1000, "storage_type": "SSD", "form_factor": "tower", "os": "Windows 11 Pro"},
     ["thinkcentre", "desktop", "core i7", "tower"], "Core i7 tower with 16 GB RAM and 1 TB SSD for engineering labs."),
    ("DCC-DT-207", "AC-DTVZ4SI-S2690G", "Acer Veriton S2690G (Core i5)", "Acer", "desktop", "8471", 41500, 48900, 95, 6, 36,
     {"cpu": "Intel Core i5-12400", "ram_gb": 8, "storage_gb": 512, "storage_type": "SSD", "form_factor": "small form factor", "os": "Windows 11 Pro"},
     ["veriton", "desktop", "sff"], "Compact business desktop, Core i5 12th Gen, 8 GB RAM, 512 GB SSD."),
    ("DCC-DT-208", "AP-MU9D3HN-MINI", "Apple Mac mini (M4, 16 GB)", "Apple", "desktop", "8471", 52800, 59900, 25, 6, 12,
     {"cpu": "Apple M4", "ram_gb": 16, "storage_gb": 256, "storage_type": "SSD", "form_factor": "mini", "os": "macOS"},
     ["mac mini", "mac", "apple desktop"], "Mac mini with Apple M4, 16 GB unified memory, 256 GB SSD."),
    ("DCC-DT-209", "AP-MWUC3HN-IMAC", "Apple iMac 24-inch (M4)", "Apple", "desktop", "8471", 118000, 134900, 12, 8, 12,
     {"cpu": "Apple M4", "ram_gb": 16, "storage_gb": 256, "storage_type": "SSD", "screen_in": 24, "form_factor": "all in one", "os": "macOS"},
     ["imac", "all in one", "aio", "apple desktop"], "24-inch 4.5K all-in-one with Apple M4."),
    # workstations
    ("DCC-WS-251", "HP-Z2G9-I7-A2000", "HP Z2 G9 Tower Workstation (RTX A2000)", "HP", "workstation", "8471", 148000, 172000, 12, 12, 36,
     {"cpu": "Intel Core i7-14700", "ram_gb": 32, "storage_gb": 1000, "storage_type": "SSD", "gpu": "NVIDIA RTX A2000 12GB", "form_factor": "tower", "os": "Windows 11 Pro"},
     ["workstation", "cad workstation", "gpu workstation"], "Entry workstation with Core i7, 32 GB RAM, 1 TB SSD and RTX A2000 12 GB."),
    ("DCC-WS-252", "DL-P3680-I7-4060", "Dell Precision 3680 Tower (RTX 4000 Ada)", "Dell", "workstation", "8471", 224000, 259000, 6, 14, 36,
     {"cpu": "Intel Core i7-14700", "ram_gb": 32, "storage_gb": 1000, "storage_type": "SSD", "gpu": "NVIDIA RTX 4000 Ada 20GB", "form_factor": "tower", "os": "Windows 11 Pro"},
     ["workstation", "precision", "ai workstation", "rendering workstation"], "Precision tower with RTX 4000 Ada 20 GB for AI and rendering labs."),
    # monitors
    ("DCC-MN-401", "DL-E2425H", "Dell E2425H 24-inch FHD Monitor", "Dell", "monitor", "8528", 8400, 9900, 260, 4, 36,
     {"screen_in": 23.8, "resolution": "1920x1080", "panel": "VA", "ports": "VGA, DisplayPort"},
     ["monitor", "24 inch", "fhd", "display", "led monitor"], "23.8-inch Full HD monitor with VGA and DisplayPort, 3-year warranty."),
    ("DCC-MN-402", "HP-64W34AA-P24G5", "HP P24 G5 23.8-inch FHD Monitor", "HP", "monitor", "8528", 9100, 10900, 220, 5, 36,
     {"screen_in": 23.8, "resolution": "1920x1080", "panel": "IPS", "ports": "HDMI, DisplayPort, VGA"},
     ["monitor", "24 inch", "ips", "fhd", "display"], "23.8-inch IPS Full HD monitor with HDMI, DisplayPort and VGA."),
    ("DCC-MN-403", "LG-24MP400-B", "LG 24MP400 24-inch IPS Monitor", "LG", "monitor", "8528", 7200, 8600, 300, 3, 36,
     {"screen_in": 23.8, "resolution": "1920x1080", "panel": "IPS", "ports": "HDMI, VGA"},
     ["monitor", "24 inch", "ips", "full hd", "led monitor"], "23.8-inch IPS Full HD monitor with HDMI and VGA inputs."),
    ("DCC-MN-404", "SM-LS24C310EA", "Samsung Essential S3 24-inch IPS Monitor", "Samsung", "monitor", "8528", 7600, 8900, 240, 3, 36,
     {"screen_in": 24, "resolution": "1920x1080", "panel": "IPS", "ports": "HDMI, VGA"},
     ["monitor", "24 inch", "ips", "fhd"], "24-inch IPS Full HD monitor, HDMI and VGA."),
    ("DCC-MN-405", "BQ-GW2790", "BenQ GW2790 27-inch Eye-care Monitor", "BenQ", "monitor", "8528", 10900, 12900, 90, 5, 36,
     {"screen_in": 27, "resolution": "1920x1080", "panel": "IPS", "ports": "HDMI, DisplayPort"},
     ["monitor", "27 inch", "eye care", "display"], "27-inch IPS Full HD eye-care monitor."),
    ("DCC-MN-406", "LN-63DFKAR-E24", "Lenovo ThinkVision E24-30 Monitor", "Lenovo", "monitor", "8528", 9600, 11400, 120, 5, 36,
     {"screen_in": 23.8, "resolution": "1920x1080", "panel": "IPS", "ports": "HDMI, DisplayPort, VGA"},
     ["thinkvision", "monitor", "24 inch", "ips"], "23.8-inch IPS Full HD monitor with tilt and height adjustment."),
    # keyboards, mice, webcams (peripheral)
    ("DCC-PR-501", "LG-920-009437-K120", "Logitech K120 USB Keyboard", "Logitech", "peripheral", "8471", 540, 695, 1800, 2, 36,
     {"connectivity": "USB wired", "layout": "full size 104 keys", "spill_resistant": True},
     ["keyboard", "usb keyboard", "wired keyboard", "104 keys"], "Full-size USB wired keyboard, spill resistant, 3-year warranty."),
    ("DCC-PR-502", "DL-KB216-BK", "Dell KB216 Multimedia USB Keyboard", "Dell", "peripheral", "8471", 610, 790, 900, 3, 12,
     {"connectivity": "USB wired", "layout": "full size 104 keys"},
     ["keyboard", "usb keyboard", "multimedia keyboard"], "Full-size USB multimedia keyboard."),
    ("DCC-PR-503", "HP-664R5AA-150", "HP 150 Wired Keyboard", "HP", "peripheral", "8471", 560, 720, 1100, 3, 12,
     {"connectivity": "USB wired", "layout": "full size 104 keys"},
     ["keyboard", "wired keyboard", "usb keyboard"], "Full-size USB wired keyboard."),
    ("DCC-PR-504", "ZB-K20-KEYBOARD", "Zebronics Zeb-K20 USB Keyboard", "Zebronics", "peripheral", "8471", 290, 399, 2500, 2, 12,
     {"connectivity": "USB wired", "layout": "full size 104 keys"},
     ["keyboard", "usb keyboard", "budget keyboard"], "Budget full-size USB keyboard."),
    ("DCC-PR-511", "LG-910-001605-B100", "Logitech B100 USB Optical Mouse", "Logitech", "peripheral", "8471", 290, 395, 2400, 2, 36,
     {"connectivity": "USB wired", "dpi": 800, "sensor": "optical"},
     ["mouse", "usb mouse", "optical mouse", "wired mouse"], "Wired USB optical mouse, ambidextrous, 3-year warranty."),
    ("DCC-PR-512", "DL-MS116-BK", "Dell MS116 USB Optical Mouse", "Dell", "peripheral", "8471", 320, 430, 1600, 3, 12,
     {"connectivity": "USB wired", "dpi": 1000, "sensor": "optical"},
     ["mouse", "usb mouse", "optical mouse"], "Wired USB optical mouse, 1000 DPI."),
    ("DCC-PR-513", "HP-265A9AA-M100", "HP M100 USB Optical Mouse", "HP", "peripheral", "8471", 330, 450, 1200, 3, 12,
     {"connectivity": "USB wired", "dpi": 1600, "sensor": "optical"},
     ["mouse", "wired mouse", "optical mouse"], "Wired USB optical mouse, up to 1600 DPI."),
    ("DCC-PR-514", "LG-910-005672-M331", "Logitech M331 Silent Wireless Mouse", "Logitech", "peripheral", "8471", 980, 1295, 700, 2, 12,
     {"connectivity": "wireless", "dpi": 1000, "sensor": "optical"},
     ["wireless mouse", "silent mouse", "mouse"], "Silent wireless mouse with USB receiver."),
    ("DCC-PR-515", "LG-920-004437-MK270", "Logitech MK270 Wireless Keyboard and Mouse Combo", "Logitech", "peripheral", "8471", 1350, 1795, 800, 2, 12,
     {"connectivity": "wireless", "layout": "full size"},
     ["keyboard mouse combo", "wireless combo", "keyboard", "mouse"], "Wireless keyboard and mouse combo."),
    ("DCC-PR-521", "LG-960-001063-C270", "Logitech C270 HD Webcam", "Logitech", "peripheral", "8525", 1350, 1795, 900, 2, 24,
     {"resolution": "1280x720", "microphone": True},
     ["webcam", "hd webcam", "camera", "720p"], "720p HD webcam with built-in microphone."),
    ("DCC-PR-522", "LG-960-001396-C920", "Logitech C920 HD Pro Webcam", "Logitech", "peripheral", "8525", 5600, 6995, 350, 2, 24,
     {"resolution": "1920x1080", "microphone": True},
     ["webcam", "full hd webcam", "1080p", "camera", "video conferencing"], "1080p Full HD webcam with stereo microphones."),
    ("DCC-PR-523", "HP-53X27AA-W300", "HP W300 1080p Webcam", "HP", "peripheral", "8525", 2350, 2999, 400, 3, 12,
     {"resolution": "1920x1080", "microphone": True},
     ["webcam", "1080p", "full hd webcam", "camera"], "1080p Full HD webcam with built-in microphone."),
    ("DCC-PR-524", "ZB-CRISPCAM-FHD", "Zebronics Zeb-Crisp Pro FHD Webcam", "Zebronics", "peripheral", "8525", 1250, 1699, 600, 2, 12,
     {"resolution": "1920x1080", "microphone": True},
     ["webcam", "1080p", "camera", "budget webcam"], "Budget 1080p webcam with microphone."),
    # audio: headphones and headsets
    ("DCC-AU-601", "LG-981-000014-H390", "Logitech H390 USB Headset with Noise-cancelling Mic", "Logitech", "audio", "8518", 1780, 2295, 1200, 2, 24,
     {"connectivity": "USB wired", "type": "stereo over-ear headset", "microphone": "noise-cancelling boom"},
     ["headset", "usb headset", "headphones with mic", "language lab headset", "noise cancelling mic"], "USB stereo headset with padded ear cups and noise-cancelling boom microphone."),
    ("DCC-AU-602", "LG-981-000593-H111", "Logitech H111 3.5 mm Stereo Headset", "Logitech", "audio", "8518", 640, 850, 1500, 2, 12,
     {"connectivity": "3.5 mm", "type": "stereo headset", "microphone": "boom"},
     ["headset", "3.5mm headset", "headphones with mic"], "Stereo headset with single 3.5 mm plug and rotating mic."),
    ("DCC-AU-603", "JB-23189-999-889-E30", "Jabra Evolve2 30 SE USB Stereo Headset", "Jabra", "audio", "8518", 6100, 7600, 260, 4, 24,
     {"connectivity": "USB-A", "type": "stereo headset", "microphone": "2-mic noise cancelling"},
     ["headset", "call centre headset", "usb headset", "professional headset"], "Professional USB stereo headset with two-microphone noise cancellation."),
    ("DCC-AU-604", "SN-WHCH520-B", "Sony WH-CH520 Wireless On-ear Headphones", "Sony", "audio", "8518", 3450, 4490, 420, 3, 12,
     {"connectivity": "Bluetooth 5.2", "type": "on-ear headphones", "microphone": "built-in"},
     ["headphones", "wireless headphones", "bluetooth headphones", "on ear"], "Bluetooth on-ear headphones, 50-hour battery."),
    ("DCC-AU-605", "JBL-T510BT-BLK", "JBL Tune 510BT Wireless Headphones", "JBL", "audio", "8518", 2750, 3499, 520, 3, 12,
     {"connectivity": "Bluetooth 5.0", "type": "on-ear headphones", "microphone": "built-in"},
     ["headphones", "wireless headphones", "bluetooth headphones"], "Bluetooth on-ear headphones with pure-bass sound."),
    ("DCC-AU-606", "SN-MDRZX110-B", "Sony MDR-ZX110 Wired Over-ear Headphones", "Sony", "audio", "8518", 780, 999, 900, 2, 12,
     {"connectivity": "3.5 mm", "type": "over-ear headphones", "microphone": "none"},
     ["headphones", "wired headphones", "over ear headphones", "multimedia headphones"], "Wired over-ear headphones with 30 mm drivers."),
    ("DCC-AU-607", "HP-428K7AA-G2", "HP G2 USB Stereo Headset", "HP", "audio", "8518", 1650, 2150, 380, 3, 12,
     {"connectivity": "USB wired", "type": "stereo headset", "microphone": "boom"},
     ["headset", "usb headset", "headphones with mic"], "USB stereo headset with adjustable boom microphone."),
    ("DCC-AU-608", "ZB-THUNDER-HP", "Zebronics Zeb-Thunder Wireless Headphones", "Zebronics", "audio", "8518", 690, 999, 1100, 2, 12,
     {"connectivity": "Bluetooth 5.0", "type": "over-ear headphones", "microphone": "built-in"},
     ["headphones", "wireless headphones", "budget headphones"], "Budget Bluetooth over-ear headphones."),
    ("DCC-AU-609", "LG-980-000418-Z120", "Logitech Z120 USB Stereo Speakers", "Logitech", "audio", "8518", 640, 895, 600, 2, 12,
     {"connectivity": "USB powered", "type": "stereo speakers"},
     ["speakers", "desktop speakers", "usb speakers"], "Compact USB-powered stereo speakers."),
    # components: GPU, CPU, memory, motherboards, PSU
    ("DCC-CP-701", "ZT-G40600H-10M", "ZOTAC GeForce RTX 4060 Twin Edge 8 GB", "Zotac", "component", "8473", 26400, 30900, 90, 5, 36,
     {"gpu": "NVIDIA GeForce RTX 4060", "vram_gb": 8, "memory_type": "GDDR6", "interface": "PCIe 4.0 x8", "tdp_w": 115},
     ["graphics card", "gpu", "rtx 4060", "nvidia graphics card", "video card"], "NVIDIA GeForce RTX 4060 graphics card, 8 GB GDDR6."),
    ("DCC-CP-702", "MS-RTX4060TI-VENTUS", "MSI GeForce RTX 4060 Ti Ventus 2X 16 GB", "MSI", "component", "8473", 41800, 47900, 40, 6, 36,
     {"gpu": "NVIDIA GeForce RTX 4060 Ti", "vram_gb": 16, "memory_type": "GDDR6", "interface": "PCIe 4.0 x8", "tdp_w": 165},
     ["graphics card", "gpu", "rtx 4060 ti", "16gb graphics card", "ai gpu"], "NVIDIA GeForce RTX 4060 Ti graphics card, 16 GB GDDR6."),
    ("DCC-CP-703", "GB-N4070WF3OC-12GD", "Gigabyte GeForce RTX 4070 Windforce 12 GB", "Gigabyte", "component", "8473", 54200, 61900, 25, 7, 36,
     {"gpu": "NVIDIA GeForce RTX 4070", "vram_gb": 12, "memory_type": "GDDR6X", "interface": "PCIe 4.0 x16", "tdp_w": 200},
     ["graphics card", "gpu", "rtx 4070", "nvidia"], "NVIDIA GeForce RTX 4070 graphics card, 12 GB GDDR6X."),
    ("DCC-CP-704", "ZT-G30500H-10L", "ZOTAC GeForce RTX 3050 6 GB", "Zotac", "component", "8473", 15200, 17900, 70, 4, 36,
     {"gpu": "NVIDIA GeForce RTX 3050", "vram_gb": 6, "memory_type": "GDDR6", "interface": "PCIe 4.0 x8", "tdp_w": 70},
     ["graphics card", "gpu", "rtx 3050", "entry graphics card"], "NVIDIA GeForce RTX 3050 graphics card, 6 GB GDDR6."),
    ("DCC-CP-711", "IN-BX8071514400F", "Intel Core i5-14400F Processor (boxed)", "Intel", "component", "8542", 14200, 16900, 150, 3, 36,
     {"cpu": "Intel Core i5-14400F", "cores": 10, "socket": "LGA1700"},
     ["processor", "cpu chip", "intel core i5 processor", "boxed processor"], "10-core Intel Core i5 14th Gen desktop processor, boxed with cooler."),
    ("DCC-CP-712", "IN-BX8071514700K", "Intel Core i7-14700K Processor (boxed)", "Intel", "component", "8542", 33800, 38900, 60, 4, 36,
     {"cpu": "Intel Core i7-14700K", "cores": 20, "socket": "LGA1700"},
     ["processor", "intel core i7 processor", "cpu chip"], "20-core Intel Core i7 14th Gen unlocked desktop processor."),
    ("DCC-CP-713", "AM-100-100001015BOX", "AMD Ryzen 5 7600 Processor (boxed)", "AMD", "component", "8542", 16400, 19500, 80, 4, 36,
     {"cpu": "AMD Ryzen 5 7600", "cores": 6, "socket": "AM5"},
     ["processor", "ryzen 5", "amd processor"], "6-core AMD Ryzen 5 7000-series desktop processor with Wraith cooler."),
    ("DCC-CP-714", "AM-100-100000591WOF", "AMD Ryzen 7 7700X Processor", "AMD", "component", "8542", 25900, 29900, 45, 5, 36,
     {"cpu": "AMD Ryzen 7 7700X", "cores": 8, "socket": "AM5"},
     ["processor", "ryzen 7", "amd processor"], "8-core AMD Ryzen 7 7000-series desktop processor."),
    ("DCC-CP-721", "CR-CT16G48C40U5", "Crucial 16 GB DDR5-4800 Desktop RAM", "Crucial", "component", "8473", 3650, 4450, 500, 2, 120,
     {"ram_gb": 16, "memory_type": "DDR5", "speed_mhz": 4800},
     ["ram", "memory module", "ddr5 ram", "16gb ram", "memory upgrade"], "16 GB DDR5-4800 UDIMM desktop memory module."),
    ("DCC-CP-722", "KG-KVR32N22S8-8", "Kingston 8 GB DDR4-3200 Desktop RAM", "Kingston", "component", "8473", 1480, 1890, 700, 2, 120,
     {"ram_gb": 8, "memory_type": "DDR4", "speed_mhz": 3200},
     ["ram", "memory module", "ddr4 ram", "8gb ram", "memory upgrade"], "8 GB DDR4-3200 UDIMM desktop memory module."),
    ("DCC-CP-731", "GB-B760M-DS3H-DDR4", "Gigabyte B760M DS3H DDR4 Motherboard", "Gigabyte", "component", "8473", 9200, 10900, 70, 4, 36,
     {"socket": "LGA1700", "chipset": "B760", "form_factor": "micro atx"},
     ["motherboard", "mainboard", "b760 motherboard"], "Micro-ATX LGA1700 motherboard with DDR4 support."),
    ("DCC-CP-741", "MS-MAG-A650BN", "MSI MAG A650BN 650 W 80+ Bronze PSU", "MSI", "component", "8504", 3700, 4490, 160, 3, 60,
     {"power_w": 650, "efficiency": "80 PLUS Bronze"},
     ["power supply", "psu", "smps", "650w psu"], "650 W 80 PLUS Bronze power supply unit."),
    # storage media
    ("DCC-ST-801", "SM-MZV9P1T0BW-990", "Samsung 990 PRO 1 TB NVMe SSD", "Samsung", "storage_media", "8523", 8200, 9800, 300, 2, 60,
     {"capacity_gb": 1000, "type": "SSD", "interface": "NVMe PCIe 4.0"},
     ["ssd", "nvme ssd", "1tb ssd", "solid state drive", "m.2 ssd"], "1 TB NVMe PCIe 4.0 M.2 SSD."),
    ("DCC-ST-802", "WD-WDS500G3B0C", "WD Blue SN580 500 GB NVMe SSD", "Western Digital", "storage_media", "8523", 3250, 3990, 450, 2, 60,
     {"capacity_gb": 500, "type": "SSD", "interface": "NVMe PCIe 4.0"},
     ["ssd", "nvme ssd", "500gb ssd", "m.2 ssd"], "500 GB NVMe M.2 SSD."),
    ("DCC-ST-803", "SG-ST2000DM008", "Seagate BarraCuda 2 TB HDD", "Seagate", "storage_media", "8471", 4750, 5790, 260, 3, 24,
     {"capacity_gb": 2000, "type": "HDD", "rpm": 7200},
     ["hard disk", "hdd", "2tb hard drive", "internal hard drive"], "2 TB 3.5-inch SATA hard disk, 7200 rpm."),
    ("DCC-ST-804", "SD-SDCZ73-064G", "SanDisk Ultra Flair 64 GB USB 3.0 Pen Drive", "SanDisk", "storage_media", "8523", 420, 590, 3000, 1, 60,
     {"capacity_gb": 64, "type": "USB flash drive", "interface": "USB 3.0"},
     ["pen drive", "usb flash drive", "64gb pendrive"], "64 GB USB 3.0 pen drive."),
    # power
    ("DCC-PW-901", "APC-BX600C-IN", "APC Back-UPS BX600C-IN 600 VA", "APC", "power", "8504", 2980, 3690, 700, 2, 24,
     {"capacity_va": 600, "topology": "line-interactive", "form_factor": "tower"},
     ["ups", "600va ups", "desktop ups", "power backup"], "600 VA line-interactive UPS for a desktop computer, 2-year warranty."),
    ("DCC-PW-902", "APC-BX1100C-IN", "APC Back-UPS BX1100C-IN 1100 VA", "APC", "power", "8504", 5600, 6790, 300, 3, 24,
     {"capacity_va": 1100, "topology": "line-interactive", "form_factor": "tower"},
     ["ups", "1kva ups", "1100va ups", "power backup"], "1100 VA line-interactive UPS."),
    ("DCC-PW-903", "APC-SRV3KI", "APC Easy UPS SRV 3 kVA Online", "APC", "power", "8504", 52000, 61500, 20, 7, 24,
     {"capacity_va": 3000, "topology": "online double-conversion", "form_factor": "tower"},
     ["online ups", "3kva ups", "lab ups", "power backup"], "3 kVA online double-conversion UPS for laboratory circuits."),
    # printers, projectors, networking
    ("DCC-PT-951", "HP-4ZB78A-M211DW", "HP LaserJet Pro M211dw", "HP", "printer", "8443", 13900, 16500, 80, 4, 12,
     {"ppm": 29, "type": "mono laser", "duplex": True, "network": "Wi-Fi, LAN"},
     ["printer", "laser printer", "network printer"], "Mono laser printer, 29 ppm, duplex, Wi-Fi and LAN."),
    ("DCC-PT-952", "EP-C11CJ67501-L3250", "Epson EcoTank L3250 All-in-One", "Epson", "printer", "8443", 11600, 13600, 110, 3, 12,
     {"ppm": 10, "type": "colour ink tank", "duplex": False, "network": "Wi-Fi"},
     ["printer", "ink tank printer", "multifunction printer", "colour printer"], "Colour ink-tank print, scan and copy."),
    ("DCC-AV-961", "EP-V11HA85056-EBX51", "Epson EB-X51 XGA Projector", "Epson", "av", "8528", 38400, 44900, 35, 5, 24,
     {"lumens": 3800, "resolution": "1024x768"},
     ["projector", "classroom projector", "lcd projector"], "3,800-lumen XGA 3LCD classroom projector."),
    ("DCC-AV-962", "BQ-MW560", "BenQ MW560 WXGA Projector", "BenQ", "av", "8528", 36200, 42500, 30, 5, 36,
     {"lumens": 4000, "resolution": "1280x800"},
     ["projector", "dlp projector", "classroom projector"], "4,000-lumen WXGA DLP projector."),
    ("DCC-NW-971", "TP-TL-SG1024D", "TP-Link TL-SG1024D 24-port Gigabit Switch", "TP-Link", "network_switch", "8517", 5200, 6300, 140, 3, 36,
     {"ports": 24, "poe": False, "managed": False},
     ["switch", "24 port switch", "gigabit switch", "unmanaged switch"], "24-port unmanaged gigabit desktop/rack switch."),
    ("DCC-NW-972", "TP-TL-SG3428", "TP-Link JetStream TL-SG3428 24-port Managed Switch", "TP-Link", "network_switch", "8517", 14800, 17600, 40, 5, 60,
     {"ports": 24, "poe": False, "managed": True, "uplinks": "4x 1G SFP"},
     ["managed switch", "l2 switch", "24 port switch"], "24-port gigabit L2+ managed switch with 4 SFP slots."),
    # software
    ("DCC-SW-981", "MS-KW9-00664-HB", "Microsoft Office Home & Business 2024", "Microsoft", "software", "8523", 21800, 24999, 200, 1, 0,
     {"licence": "perpetual, per device"},
     ["ms office", "office licence", "microsoft office"], "Perpetual Office licence for one PC or Mac."),
    ("DCC-SW-982", "QH-TS-1U-3Y", "Quick Heal Total Security (3 years)", "Quick Heal", "software", "8523", 1650, 2400, 1000, 1, 0,
     {"term_months": 36, "licence": "per device"},
     ["antivirus", "endpoint protection", "total security"], "Antivirus and internet security, one device for three years."),
    # services
    ("DCC-SV-991", "DCC-SVC-INSTALL", "On-site Installation, Imaging and Asset Tagging", "Data Care Services", "service", "9987", 350, 900, 99999, 3, 0,
     {"scope": "per device"},
     ["installation", "setup", "imaging", "commissioning", "asset tagging"], "Unpacking, installation, OS imaging, asset tagging and hand-over per device."),
    ("DCC-SV-992", "DCC-SVC-AMC", "Comprehensive AMC (per device per year)", "Data Care Services", "service", "9987", 1100, 2200, 99999, 1, 0,
     {"scope": "per device per year"},
     ["amc", "annual maintenance", "maintenance contract"], "Comprehensive annual maintenance including parts and on-site visits."),
]

# Datasheet attributes a tender specification table typically asks about.
SPEC_EXTRA: dict[str, dict] = {
    "DCC-DT-201": {"usb_ports": 8, "ports": "4x USB 3.2, 4x USB 2.0, HDMI, VGA, DisplayPort", "network": "Gigabit Ethernet",
                   "max_ram_gb": 64, "certification": "BEE star rating, ENERGY STAR"},
    "DCC-DT-203": {"usb_ports": 8, "ports": "5x USB 3.2, 3x USB 2.0, HDMI, DisplayPort", "network": "Gigabit Ethernet",
                   "max_ram_gb": 64, "certification": "ENERGY STAR, EPEAT"},
    "DCC-DT-205": {"usb_ports": 8, "ports": "4x USB 3.2, 4x USB 2.0, HDMI, VGA, DisplayPort", "network": "Gigabit Ethernet",
                   "max_ram_gb": 64, "certification": "ENERGY STAR"},
    "DCC-DT-204": {"usb_ports": 6, "ports": "4x USB 3.2, 2x USB 2.0, HDMI, VGA", "network": "Gigabit Ethernet"},
    "DCC-MN-401": {"surface": "anti-glare", "certification": "BEE star rating, ENERGY STAR"},
    "DCC-MN-402": {"surface": "anti-glare", "certification": "BEE star rating, ENERGY STAR"},
    "DCC-MN-403": {"surface": "anti-glare", "certification": "BEE star rating 3 star"},
    "DCC-MN-404": {"surface": "anti-glare", "certification": "BEE star rating"},
    "DCC-MN-406": {"surface": "anti-glare", "certification": "ENERGY STAR"},
    "DCC-PR-501": {"design": "spill resistant, low profile keys", "layout": "full size 104 keys, US English layout with Rupee symbol"},
    "DCC-PR-502": {"design": "low profile keys", "layout": "full size 104 keys, US English layout with Rupee symbol"},
    "DCC-PR-503": {"design": "spill resistant", "layout": "full size 104 keys, US English layout"},
    "DCC-PR-511": {"buttons": "3 buttons with scroll wheel", "design": "ambidextrous"},
    "DCC-PR-512": {"buttons": "3 buttons with scroll wheel", "design": "ambidextrous"},
    "DCC-PR-513": {"buttons": "3 buttons with scroll wheel", "design": "ambidextrous"},
    "DCC-PR-521": {"fps": 30, "mounting": "universal monitor clip", "interface": "USB plug and play"},
    "DCC-PR-522": {"fps": 30, "mounting": "universal monitor clip, tripod thread", "interface": "USB plug and play"},
    "DCC-PR-523": {"fps": 30, "mounting": "universal monitor clip", "interface": "USB plug and play"},
    "DCC-PR-524": {"fps": 30, "mounting": "universal monitor clip", "interface": "USB plug and play"},
    "DCC-AU-601": {"controls": "in-line volume and mute controls", "cable_m": 1.9, "fit": "stereo over-ear USB headset"},
    "DCC-AU-603": {"controls": "in-line volume, mute and call controls", "cable_m": 1.2, "fit": "stereo on-ear"},
    "DCC-AU-607": {"controls": "in-line volume and mute controls", "cable_m": 1.8, "fit": "stereo over-ear"},
    "DCC-AU-606": {"driver_mm": 30, "connector": "3.5 mm stereo jack", "fit": "wired over-ear stereo headphones"},
    "DCC-LT-101": {"battery_hours": 7, "display": "15.6 inch Full HD anti-glare", "resolution": "1920x1080"},
    "DCC-LT-103": {"battery_hours": 6, "display": "15.6 inch Full HD anti-glare", "resolution": "1920x1080"},
    "DCC-LT-108": {"battery_hours": 6, "display": "15.6 inch Full HD anti-glare", "resolution": "1920x1080"},
    "DCC-CP-701": {"interface": "PCI Express 4.0 x8", "support": "CUDA and cuDNN supported", "min_psu_w": 550},
    "DCC-CP-702": {"interface": "PCI Express 4.0 x8", "support": "CUDA and cuDNN supported", "min_psu_w": 550},
    "DCC-CP-703": {"interface": "PCI Express 4.0 x16", "support": "CUDA and cuDNN supported", "min_psu_w": 650},
    "DCC-PW-901": {"outlets": 3, "sockets": "3 Indian sockets", "backup_minutes": 12},
    "DCC-PW-902": {"outlets": 4, "sockets": "4 Indian sockets", "backup_minutes": 15},
}

TAX_CATEGORY = {"software": "software", "service": "services"}
MIN_MARGIN = {"component": 5, "peripheral": 10, "audio": 10, "storage_media": 6, "laptop": 6, "desktop": 7, "monitor": 7,
              "service": 20, "software": 6}


def catalogue() -> list[dict]:
    rows = []
    for sku, mpn, name, brand, cat, hsn, cost, lst, stock, lead, wty, specs, kw, desc in P:
        if cat not in ("service", "software"):
            # Wholesale buying: distributor price less volume and scheme rebates.
            cost = round(cost * 0.94, 0 if cost < 1000 else -1)
        rows.append({
            "sku": sku, "mpn": mpn, "name": name, "brand": brand, "category": cat, "specs": {**specs, **SPEC_EXTRA.get(sku, {})},
            "keywords": kw,
            "unit": "unit", "unit_cost": cost, "list_price": lst, "min_margin_pct": MIN_MARGIN.get(cat, 8),
            "stock_qty": stock, "lead_time_days": lead, "warranty_months": wty,
            "tax_category": TAX_CATEGORY.get(cat, "goods_standard"), "description": desc, "hsn": hsn,
        })
    return rows


# --------------------------------------------------------------------------- competitors

COMPETITORS = [
    {"id": "amazon_business", "name": "Amazon Business", "hq": "Bengaluru, IN", "currency": "INR",
     "positioning": "Online marketplace (B2B)", "channel": "marketplace", "serves": ["IN"], "reliability": 0.86,
     "default_warranty_months": 12, "lead_time_days": [3, 7], "brands": "*",
     "category_factor": {"peripheral": 0.9, "audio": 0.86, "component": 0.95, "storage_media": 0.92, "laptop": 0.97,
                         "desktop": 1.02, "monitor": 0.95, "*": 0.98},
     "coverage": 0.93, "volatility": 0.035,
     "notes": "GST invoice and bulk pricing on business accounts; no on-site installation; OEM carry-in warranty."},
    {"id": "flipkart_wholesale", "name": "Flipkart Wholesale", "hq": "Bengaluru, IN", "currency": "INR",
     "positioning": "Online wholesale marketplace", "channel": "marketplace", "serves": ["IN"], "reliability": 0.8,
     "default_warranty_months": 12, "lead_time_days": [4, 10], "brands": "*",
     "category_factor": {"peripheral": 0.88, "audio": 0.85, "laptop": 0.96, "monitor": 0.94, "component": 0.97,
                         "desktop": 1.04, "*": 0.99},
     "coverage": 0.82, "volatility": 0.045,
     "notes": "Deep discounts during sale events; limited stock for 50+ unit orders; no tender documentation support."},
    {"id": "hp_world", "name": "HP World (factory outlet)", "hq": "Pune, IN", "currency": "INR",
     "positioning": "HP brand store", "channel": "brand store", "serves": ["IN"], "reliability": 0.93,
     "default_warranty_months": 12, "lead_time_days": [5, 12], "brands": ["HP"],
     "category_factor": {"laptop": 0.98, "desktop": 0.99, "*": 1.0}, "coverage": 1.0, "volatility": 0.02,
     "bundle": "Free HP carry case and 1-year care pack upgrade",
     "notes": "Offers only HP products; education pricing on ProBook and Pro Tower lines."},
    {"id": "apple_store", "name": "Apple authorised store", "hq": "Pune, IN", "currency": "INR",
     "positioning": "Apple authorised reseller", "channel": "brand store", "serves": ["IN"], "reliability": 0.97,
     "default_warranty_months": 12, "lead_time_days": [4, 10], "brands": ["Apple"],
     "category_factor": {"*": 1.02}, "coverage": 1.0, "volatility": 0.01,
     "notes": "Apple products only; education pricing for institutions."},
    {"id": "dell_store", "name": "Dell Exclusive Store", "hq": "Pune, IN", "currency": "INR",
     "positioning": "Dell brand store", "channel": "brand store", "serves": ["IN"], "reliability": 0.92,
     "default_warranty_months": 36, "lead_time_days": [6, 14], "brands": ["Dell"],
     "category_factor": {"desktop": 0.97, "laptop": 0.98, "monitor": 0.96, "*": 1.0}, "coverage": 1.0, "volatility": 0.02,
     "bundle": "Free on-site installation",
     "notes": "Dell products only; 3-year on-site warranty on OptiPlex and Latitude."},
]

PROMOTIONS = [
    {"competitor": "amazon_business", "mpn": "LG-981-000014-H390", "street_factor": 0.78, "label": "Business bulk deal"},
    {"competitor": "flipkart_wholesale", "mpn": "LG-910-001605-B100", "street_factor": 0.74, "label": "Sale event price"},
    {"competitor": "flipkart_wholesale", "mpn": "LG-24MP400-B", "street_factor": 0.86, "label": "Festive sale"},
    {"competitor": "amazon_business", "mpn": "ZT-G40600H-10M", "street_factor": 0.9, "label": "Lightning deal"},
    {"competitor": "hp_world", "mpn": "HP-9H1P7PA-280G9", "street_factor": 0.92, "label": "Education programme"},
    {"competitor": "dell_store", "mpn": "DL-E2425H", "street_factor": 0.88, "label": "Bundle with OptiPlex"},
    {"competitor": "apple_store", "mpn": "AP-MC8H4HN-A", "street_factor": 0.9, "label": "Education pricing"},
]


def market(catalog: list[dict]) -> dict:
    products = {}
    for p in catalog:
        if p["category"] == "service":
            continue
        # Street price: what the item sells for in the open market before GST (list less a typical dealer discount).
        street = p["list_price"] * {"component": 0.99, "peripheral": 0.95, "audio": 0.93}.get(p["category"], 0.99)
        products[p["mpn"]] = {"category": p["category"], "brand": p["brand"], "description": p["name"],
                              "street_price_usd": round(street / USD_INR, 2)}
    return {"_comment": "Mock competitor market for Data Care Corp. Owned by the market service; the pricing engine "
                        "only sees it through the API.",
            "competitors": COMPETITORS, "promotions": PROMOTIONS, "products": products}


# --------------------------------------------------------------------------- collected observations

def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16))


SOURCES = {
    "amazon_business": ("Marketplace listing", "https://www.amazon.in/business/"),
    "flipkart_wholesale": ("Marketplace listing", "https://www.flipkartwholesale.com/"),
    "hp_world": ("Store quotation", "HP World, FC Road, Pune"),
    "apple_store": ("Store quotation", "Apple authorised store, Pune"),
    "dell_store": ("Store quotation", "Dell Exclusive Store, Aundh, Pune"),
}


def quotes(catalog: list[dict], mkt: dict) -> list[dict]:
    """Price observations the sales team collected over the last quarter."""
    rows = []
    for p in catalog:
        if p["category"] in ("service", "software"):
            continue
        street = mkt["products"][p["mpn"]]["street_price_usd"] * USD_INR
        for comp in COMPETITORS:
            if comp["brands"] != "*" and p["brand"] not in comp["brands"]:
                continue
            r = _rng("obs", comp["id"], p["mpn"])
            if r.random() > comp["coverage"] * 0.8:
                continue
            factor = comp["category_factor"].get(p["category"], comp["category_factor"]["*"])
            for k in range(r.choice([1, 2, 2, 3])):
                seen = TODAY - timedelta(days=r.randint(3 + 25 * k, 25 + 30 * k))
                price = round(street * factor * r.uniform(0.95, 1.06), -1 if street < 5000 else 1)
                label, ref = SOURCES[comp["id"]]
                rows.append({"observed_on": seen.isoformat(), "competitor": comp["name"], "competitor_id": comp["id"],
                             "mpn": p["mpn"], "product": p["name"], "quantity": r.choice([1, 10, 25, 50]),
                             "unit_price": price, "currency": "INR", "gst_included": "no",
                             "warranty_months": comp["default_warranty_months"],
                             "source": label, "reference": ref, "collected_by": r.choice(["Sneha P.", "Amit K.", "Rohan D."])})
    rows.sort(key=lambda r: (r["observed_on"], r["competitor"]))
    return rows


LOCAL_BIDDERS = ["Shree Sai Computers", "Om Infotech Solutions", "Pune Computer Mart", "Vardhaman Systems",
                 "Kalpataru Technologies"]
BUYERS = ["State university, Pune", "Government polytechnic, Aurangabad", "ITI, Nashik", "Engineering college, Kolhapur",
          "Municipal school board, Pune", "Deemed university, Sangli", "Autonomous college, Satara"]


def awards(catalog: list[dict], mkt: dict) -> list[dict]:
    """Past public awards (GeM / e-tender results) for comparable items."""
    rows = []
    r = random.Random(4417)
    pool = [p for p in catalog if p["category"] in ("desktop", "laptop", "monitor", "peripheral", "audio", "component", "power")]
    for i in range(80):
        p = r.choice(pool)
        street = mkt["products"][p["mpn"]]["street_price_usd"] * USD_INR
        qty = r.choice([20, 30, 50, 60, 100, 120])
        winner = r.choice(LOCAL_BIDDERS + ["Data Care Corp"] * 2)
        rows.append({"awarded_on": (TODAY - timedelta(days=r.randint(20, 400))).isoformat(),
                     "buyer": r.choice(BUYERS), "portal": r.choice(["GeM", "GeM", "MahaTenders"]),
                     "reference": f"GEM/2026/B/{5200000 + r.randint(0, 99999)}", "mpn": p["mpn"], "product": p["name"],
                     "quantity": qty, "winner": winner,
                     "unit_price": round(street * r.uniform(0.9, 1.0) * (0.97 if qty >= 100 else 1.0), 0),
                     "currency": "INR", "bidders": r.randint(3, 9)})
    rows.sort(key=lambda r: r["awarded_on"])
    return rows


# --------------------------------------------------------------------------- customers, services, knowledge

CUSTOMERS = [
    {"name": "DES Pune University", "country": "IN", "region": "Maharashtra", "segment": "education",
     "tax_id": "27AAATD0421B1ZK", "deals_won": 1},
    {"name": "Symbiosis Skills and Professional University", "country": "IN", "region": "Maharashtra", "segment": "education",
     "tax_id": None, "deals_won": 2},
    {"name": "Pimpri Chinchwad Municipal Corporation", "country": "IN", "region": "Maharashtra", "segment": "public",
     "tax_id": None, "deals_won": 0},
    {"name": "Hinjewadi Contact Centre Services", "country": "IN", "region": "Maharashtra", "segment": "enterprise",
     "tax_id": "27AADCH7719Q1Z1", "deals_won": 3},
    {"name": "Nashik Polytechnic Society", "country": "IN", "region": "Maharashtra", "segment": "education",
     "tax_id": None, "deals_won": 1},
    {"name": "Karnataka Skills Board", "country": "IN", "region": "Karnataka", "segment": "public", "tax_id": None,
     "deals_won": 0},
]

VALUE_ADDS = [
    {"code": "WTY-EXT12", "name": "Extended warranty, +12 months", "kind": "warranty", "basis": "percent", "cost_rate": 2.8,
     "value_rate": 7.5, "warranty_extension_months": 12,
     "categories": ["laptop", "desktop", "workstation", "monitor", "peripheral", "audio", "printer", "av", "power"],
     "description": "Extends the OEM warranty by twelve months, back-to-back with the OEM care pack and handled by Data Care Corp."},
    {"code": "WTY-EXT24", "name": "Extended warranty, +24 months", "kind": "warranty", "basis": "percent", "cost_rate": 5.0,
     "value_rate": 12.5, "warranty_extension_months": 24,
     "categories": ["laptop", "desktop", "workstation", "monitor", "component"],
     "description": "Extends the OEM warranty by twenty-four months including on-site engineer visits in Pune."},
    {"code": "SVC-DEPLOY", "name": "On-site installation, imaging and asset tagging", "kind": "service", "basis": "flat",
     "cost_rate": 350, "value_rate": 900, "warranty_extension_months": 0,
     "categories": ["laptop", "desktop", "workstation", "monitor", "printer", "av"],
     "description": "Unpacking, installation, OS imaging, asset tagging and hand-over at the client's laboratories."},
    {"code": "SVC-GPUFIT", "name": "GPU fitment, driver and CUDA set-up", "kind": "service", "basis": "flat",
     "cost_rate": 450, "value_rate": 1500, "warranty_extension_months": 0, "categories": ["component"],
     "description": "Fitting the card, power-supply check, driver and CUDA toolkit installation and burn-in test."},
    {"code": "SVC-SPARES", "name": "On-site spares buffer (2%)", "kind": "support", "basis": "percent", "cost_rate": 2.0,
     "value_rate": 6.0, "warranty_extension_months": 0, "categories": ["peripheral", "audio", "monitor"],
     "description": "Two per cent spare units kept at the client's site for same-day swap during the warranty."},
    {"code": "TRN-LAB", "name": "Lab administrator training (half day)", "kind": "training", "basis": "flat",
     "cost_rate": 500, "value_rate": 2500, "warranty_extension_months": 0, "categories": ["software", "desktop", "component"],
     "description": "Imaging, driver management and first-level troubleshooting training for lab staff."},
]

PRICE_TIERS = {
    "*": [[10, 2.0], [25, 3.0], [50, 4.5], [100, 6.0]],
    "laptop": [[10, 2.0], [25, 3.5], [50, 5.0], [100, 6.5]],
    "desktop": [[10, 2.0], [25, 3.5], [50, 5.0], [100, 6.5]],
    "monitor": [[10, 2.5], [25, 4.0], [50, 5.5], [100, 7.0]],
    "peripheral": [[25, 4.0], [50, 6.0], [100, 8.0], [250, 10.0]],
    "audio": [[25, 4.0], [50, 6.0], [100, 8.0], [250, 10.0]],
    "component": [[10, 1.5], [25, 2.5], [50, 3.5], [100, 4.5]],
    "storage_media": [[25, 2.5], [100, 4.0]],
    "service": [[10, 3.0], [50, 6.0]],
}

KNOWLEDGE = {
    "01_company_profile.md": """# Company profile

## About Data Care Corp
Data Care Corp is a wholesale dealer and institutional supplier of computers, components and consumer electronics, headquartered in Bhosari, Pune. Since 2009 we have supplied laptops, desktops, monitors, keyboards, mice, headphones and headsets, graphics cards, processors, memory and storage to colleges, universities, government offices, BPOs and retailers across Maharashtra.

## Scale and track record
Our team of 58 includes 9 certified service engineers and a dedicated institutional sales and tender desk. In the last three financial years we have shipped more than 62,000 devices and components, with an on-time delivery rate of 96.4 percent. Our 40,000 sq ft central warehouse in Bhosari holds ready stock of fast-moving lab items.

## Partner credentials
Data Care Corp is an authorised channel partner of HP, Dell, Lenovo, Acer, Asus and Apple, and a direct dealer for Logitech, Sony, JBL, Jabra, Zebronics, Intel, AMD, NVIDIA board partners (Zotac, MSI, Gigabyte), Samsung, LG, BenQ, Crucial, Kingston, Western Digital, Seagate, APC, TP-Link and Epson. Every unit supplied is genuine, carries the full manufacturer warranty and is billed with a GST invoice.

## Why institutions choose us
Institutions choose Data Care Corp because we combine wholesale pricing with tender-grade documentation: OEM authorisation letters, compliance statements, delivery challans with serial numbers and a named account manager who stays with the client through warranty.
""",
    "02_warranty_programs.md": """# Warranty programmes

## Manufacturer warranty
All products carry the manufacturer's standard warranty: three years on-site for business desktops and most monitors, one year for consumer laptops and headphones, and three years for graphics cards, processors and branded keyboards and mice. Warranty registration is completed by us in the institution's name before delivery.

## Extended warranty
We offer twelve and twenty-four month extensions, back-to-back with OEM care packs, so that every desktop, laptop and monitor in a laboratory can be kept under a single five-year warranty period.

## Replacement of peripherals
Faulty keyboards, mice, headsets and webcams under warranty are replaced from our Pune stock within two working days; the defective unit is returned to the OEM by us, not by the institution.
""",
    "03_support_services.md": """# Support and service

## Helpdesk
Our helpdesk operates from 09:30 to 19:00, Monday to Saturday, by phone, e-mail and WhatsApp. Every complaint receives a ticket number and remote response within four working hours.

## On-site service
Service engineers attend on site within 24 hours inside Pune and PCMC limits, and within 48 hours elsewhere in Maharashtra. For laboratory orders we can keep a two per cent spares buffer at the client's premises for same-day swap.

## Annual maintenance
After warranty, we offer comprehensive annual maintenance contracts covering parts and labour for desktops, laptops, printers and UPS units.
""",
    "04_deployment_installation.md": """# Deployment and installation

## Laboratory set-up
Our installation team unpacks, installs and tests every desktop, monitor, keyboard, mouse, headset and UPS at the laboratory, loads the institution's standard OS image, tags each asset and hands over a serial-number register.

## GPU and component upgrades
For AI and graphics laboratories we fit graphics cards, memory and storage into existing machines, check power-supply headroom, install drivers and the CUDA toolkit and run a burn-in test before hand-over.

## Packaging waste
All packaging material is removed from site on the day of installation and sent for recycling.
""",
    "05_delivery_logistics.md": """# Delivery and logistics

## Stock and lead time
Fast-moving laboratory items — keyboards, mice, headsets, webcams, monitors and entry desktops — are held as ready stock in our Pune warehouse and can be delivered within one week for quantities up to 200. Branded desktops and laptops built to order ship in two to three weeks.

## Delivery
Deliveries within Pune are made in our own vehicles with our staff, and every consignment is insured until it is signed for at the client's stores. Delivery challans list model and serial numbers for inspection.
""",
    "06_commercial_terms.md": """# Commercial terms

## Pricing and GST
Prices are quoted exclusive of GST, with CGST and SGST shown separately for supplies within Maharashtra and IGST for supplies to other states. Prices are firm for the validity of the offer.

## Payment
Our standard terms are 100 percent payment within 30 days of delivery, installation and acceptance. For government and university orders we accept the purchaser's standard terms, including payment against inspection certificates.

## Performance security
As a registered small enterprise we are exempt from EMD where the tender allows, and we furnish performance security by bank guarantee or FDR from a scheduled bank.
""",
    "07_certifications_compliance.md": """# Certifications and compliance

## Quality management
Data Care Corp is certified to ISO 9001:2015 for wholesale trading, supply and after-sales service of computers, components and electronics, and to ISO 14001:2015 for environmental management.

## MSME and local supplier status
We are registered on Udyam as a small enterprise (trading and services) and are a Class-II local supplier under the Public Procurement (Preference to Make in India) Order.

## E-waste
We are an authorised e-waste collection partner and take back replaced equipment, batteries and packaging in line with the E-Waste (Management) Rules, 2022.
""",
    "08_security_practices.md": """# Data security

## Disk handling
Replaced storage from warranty repairs is wiped using a certified erasure tool or returned to the institution, and a certificate of sanitisation is issued on request.

## Imaging
Operating system images supplied by the institution are stored on an encrypted server at our warehouse and deleted after the project unless the client asks us to keep them for future re-imaging.
""",
    "09_case_studies.md": """# Case studies

## Engineering college laboratories, Pune
Supplied and installed 240 laboratory desktops with monitors, keyboards, mice and UPS units across six laboratories in 18 days, including imaging and asset tagging.

## Language laboratory, deemed university
Delivered 120 USB headsets with noise-cancelling microphones, 120 desktops and webcams for a language laboratory; the headsets were tested for microphone clarity at every seat before hand-over.

## AI laboratory upgrade, Mumbai
Upgraded 60 machines with NVIDIA RTX graphics cards and additional memory, installed CUDA and deep-learning frameworks, and trained laboratory staff.
""",
    "10_sustainability.md": """# Sustainability

## Energy efficiency
We recommend BEE star-rated and ENERGY STAR qualified products where available and share energy data sheets with every laboratory proposal.

## Take-back
Old keyboards, mice, monitors and CPUs replaced in a laboratory refresh can be taken back for certified recycling at no charge.
""",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "knowledge").mkdir(exist_ok=True)
    cat = catalogue()
    mkt = market(cat)

    def dump(name: str, obj) -> None:
        (OUT / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    dump("company.json", COMPANY)
    dump("catalog.json", cat)
    dump("customers.json", CUSTOMERS)
    dump("market.json", mkt)
    dump("value_adds.json", VALUE_ADDS)
    dump("price_tiers.json", PRICE_TIERS)
    for name, text in KNOWLEDGE.items():
        (OUT / "knowledge" / name).write_text(text, encoding="utf-8")
    for name, rows in (("competitor_quotes.csv", quotes(cat, mkt)), ("award_history.csv", awards(cat, mkt))):
        with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"Wrote {len(cat)} products, {len(COMPETITORS)} competitors to {OUT}")


if __name__ == "__main__":
    main()
