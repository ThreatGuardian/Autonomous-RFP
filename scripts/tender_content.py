"""Content of the two long sample tenders (shared by the PDF and DOCX builders).

Both are fictional organisations written in the structure and language of real
Indian public and institutional tenders: a notice inviting tender with key
dates, instructions to bidders, pre-qualification criteria, scope of work,
technical specification tables, a bill of quantities, commercial terms,
evaluation method, general conditions and annexure forms.

A document is a list of elements:
``("title", text)``, ``("h1", text)``, ``("h2", text)``, ``("p", text)``,
``("clause", number, text)``, ``("table", header, rows, widths)``, ``("break",)``.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- tender 1: municipal (PDF, L1)

GV_ORG = "Godavari Valley Smart City Development Corporation Limited"
GV_REF = "GVSCDCL/IT/2026-27/07"


def _spec(rows: list[tuple[str, str]]) -> tuple:
    return ("table", ["S. No.", "Parameter", "Minimum specification"],
            [[str(i), p, s] for i, (p, s) in enumerate(rows, start=1)], [12, 45, 113])


GODAVARI: list[tuple] = [
    ("title", GV_ORG),
    ("p", "(A Special Purpose Vehicle of Nashik Municipal Corporation under the Smart Cities Mission)"),
    ("p", "Smart City Bhavan, Trimbak Road, Nashik 422002, Maharashtra"),
    ("p", "GSTIN: 27AAGCG5521K1Z9"),
    ("title", "TENDER DOCUMENT"),
    ("p", "Tender No.: " + GV_REF),
    ("p", "Subject: Supply, Installation, Testing and Commissioning of IT Infrastructure for Twelve Ward Offices "
          "and the Citizen Facilitation Centre"),
    ("p", "Date of issue: 21 September 2026"),
    ("p", "Mode of tendering: Online through the Maharashtra e-Tendering portal (mahatenders.gov.in), two-envelope system"),
    ("p", "This document contains 14 pages including the annexures. Bidders are advised to read the entire document "
          "carefully before submitting their bid."),
    ("break",),

    ("h1", "SECTION I – NOTICE INVITING TENDER"),
    ("clause", "1.1", "The Chief Executive Officer, Godavari Valley Smart City Development Corporation Limited (hereinafter "
                      "referred to as the Purchaser), invites online bids from eligible and experienced bidders for the "
                      "supply, installation, testing and commissioning of IT infrastructure for twelve ward offices and the "
                      "Citizen Facilitation Centre as detailed in this document."),
    ("clause", "1.2", "The key data and critical dates of this tender are given below."),
    ("table", ["S. No.", "Particulars", "Details"], [
        ["1", "Tender number", GV_REF],
        ["2", "Estimated cost of the work", "Rs. 2.25 crore (inclusive of GST)"],
        ["3", "Earnest Money Deposit (EMD)", "Rs. 4,50,000 (Rupees four lakh fifty thousand only)"],
        ["4", "Tender document fee", "Rs. 5,900 (non-refundable, inclusive of GST)"],
        ["5", "Date of publication", "21 September 2026"],
        ["6", "Pre-bid meeting", "01 October 2026 at 11:00 hrs, Conference Hall, Smart City Bhavan, Nashik"],
        ["7", "Last date for receipt of pre-bid queries", "30 September 2026 up to 17:00 hrs"],
        ["8", "Last date and time for online bid submission", "20 October 2026 up to 15:00 hrs"],
        ["9", "Opening of technical bids", "21 October 2026 at 15:30 hrs"],
        ["10", "Bid validity", "120 days from the last date of bid submission"],
        ["11", "Completion period", "60 days from the date of issue of the purchase order"],
    ], [12, 70, 88]),
    ("clause", "1.3", "The tender document can be downloaded free of cost from the e-Tendering portal. The tender fee and "
                      "EMD shall be paid online through the payment gateway of the portal only."),
    ("clause", "1.4", "Micro and Small Enterprises (MSEs) registered with Udyam or NSIC for the tendered items are exempted "
                      "from payment of the tender fee and EMD, subject to submission of a valid registration certificate "
                      "with the technical bid."),
    ("clause", "1.5", "The Purchaser reserves the right to accept or reject any or all bids without assigning any reason."),
    ("clause", "1.6", "Bids received after the due date and time will not be accepted under any circumstances."),

    ("h1", "SECTION II – INSTRUCTIONS TO BIDDERS"),
    ("h2", "2.1 General"),
    ("clause", "2.1.1", "The bidder shall examine all instructions, forms, terms, specifications and other information in "
                        "the tender document. Failure to furnish all information required, or submission of a bid not "
                        "substantially responsive to the tender document in every respect, will be at the bidder's risk "
                        "and may result in rejection of the bid."),
    ("clause", "2.1.2", "The bidder shall bear all costs associated with the preparation and submission of its bid, and the "
                        "Purchaser will in no case be responsible or liable for those costs."),
    ("clause", "2.1.3", "Consortium or joint venture bids are not permitted. Sub-contracting of the supply is not allowed; "
                        "installation manpower may be engaged by the bidder under its own responsibility."),
    ("h2", "2.2 Clarifications and pre-bid meeting"),
    ("clause", "2.2.1", "A prospective bidder requiring any clarification shall submit its queries by e-mail to "
                        "it.tenders@gvscdcl.in in the prescribed format before the last date for pre-bid queries."),
    ("clause", "2.2.2", "Replies to the queries and any amendment to the tender will be published on the portal as a "
                        "corrigendum and shall form part of the tender document."),
    ("h2", "2.3 Preparation and submission of bids"),
    ("clause", "2.3.1", "The bid shall be submitted online in two envelopes: Envelope A (technical bid) and Envelope B "
                        "(financial bid). Price shall not be indicated anywhere in the technical bid; any bid disclosing "
                        "price in the technical bid will be summarily rejected."),
    ("clause", "2.3.2", "The technical bid must contain all documents listed in the checklist at Annexure-1, duly signed "
                        "and stamped by the authorised signatory on every page."),
    ("clause", "2.3.3", "The bidder must quote for all items in the Bill of Quantities. Partial bids will be treated as "
                        "non-responsive."),
    ("clause", "2.3.4", "Prices shall be quoted in Indian Rupees only, with GST shown separately against each item in the "
                        "financial bid format."),
    ("clause", "2.3.5", "Conditional bids shall not be accepted. Any deviation from the specifications or terms must be "
                        "stated clearly in the compliance statement at Annexure-5."),
    ("clause", "2.3.6", "The bidder must upload a power of attorney or board resolution in favour of the authorised signatory."),
    ("h2", "2.4 Bid security"),
    ("clause", "2.4.1", "The EMD of unsuccessful bidders will be refunded without interest within 30 days of award of the "
                        "contract. The EMD of the successful bidder will be released on receipt of the performance security."),
    ("clause", "2.4.2", "The EMD shall be forfeited if the bidder withdraws its bid during the period of bid validity or "
                        "fails to furnish the performance security within the stipulated time."),

    ("h1", "SECTION III – ELIGIBILITY AND PRE-QUALIFICATION CRITERIA"),
    ("p", "Only bidders fulfilling all of the following criteria shall be considered for evaluation of the technical bid. "
          "Documentary evidence for each criterion must be enclosed."),
    ("table", ["S. No.", "Eligibility criterion", "Supporting documents"], [
        ["1", "The bidder should be a company registered under the Companies Act or a partnership firm registered in India, "
              "in existence for at least five years as on the date of publication.",
         "Certificate of incorporation or partnership deed"],
        ["2", "The bidder should have an average annual turnover of not less than Rs. 3 crore from IT hardware supply in "
              "the last three financial years (2022-23, 2023-24 and 2024-25).",
         "Audited balance sheets and CA certificate"],
        ["3", "The bidder should have a positive net worth as on 31 March 2025.", "CA certificate"],
        ["4", "The bidder should have successfully completed similar works during the last seven years ending on the last "
              "day of the month previous to the one in which bids are invited, either three similar completed works each "
              "costing not less than 40% of the estimated cost; or two similar completed works each costing not less than "
              "50% of the estimated cost; or one similar completed work costing not less than 80% of the estimated cost.",
         "Work orders with completion certificates"],
        ["5", "The bidder must hold a valid ISO 9001:2015 certificate.", "Copy of certificate"],
        ["6", "The bidder must be an authorised partner of the Original Equipment Manufacturer (OEM) for each quoted "
              "product and submit a Manufacturer's Authorisation Form (MAF) in the format at Annexure-3.",
         "MAF from each OEM"],
        ["7", "The bidder should have a registered office or service centre in Maharashtra.",
         "Registration certificate or rent agreement"],
        ["8", "The bidder shall not have been blacklisted or debarred by any Central or State Government department or "
              "PSU as on the date of bid submission.", "Self-declaration at Annexure-4"],
        ["9", "The bidder must have a valid GST registration and PAN.", "GST certificate and PAN card"],
        ["10", "Only Class-I and Class-II local suppliers as defined in the Public Procurement (Preference to Make in India) "
               "Order, 2017 are eligible to bid.", "Self-certificate of local content"],
    ], [12, 108, 50]),

    ("h1", "SECTION IV – SCOPE OF WORK"),
    ("clause", "4.1", "The scope of work covers supply, transportation, unloading, installation, configuration, testing and "
                      "commissioning of the equipment listed in the Bill of Quantities at the twelve ward offices and the "
                      "Citizen Facilitation Centre (CFC) at Smart City Bhavan, Nashik."),
    ("clause", "4.2", "The successful bidder shall carry out a site survey of all thirteen locations within seven days of "
                      "the purchase order and submit a deployment plan for approval."),
    ("clause", "4.3", "The bidder shall supply and lay structured cabling (Cat6 UTP) within each ward office, including "
                      "PVC conduits, patch panels and patch cords, and shall certify each node."),
    ("clause", "4.4", "All end-user devices shall be delivered with the operating system pre-installed and activated, joined "
                      "to the Purchaser's domain and tagged with asset labels."),
    ("clause", "4.5", "The bidder shall configure VLANs, wireless SSIDs and firewall policies as per the network design "
                      "approved by the Purchaser, and shall provide as-built documentation."),
    ("clause", "4.6", "The bidder shall train at least two staff members per ward office in basic troubleshooting and "
                      "provide a half-day administrator training for the Purchaser's IT cell."),
    ("clause", "4.7", "The bidder shall provide one resident engineer at the CFC for three months after commissioning."),

    ("h1", "SECTION V – TECHNICAL SPECIFICATIONS"),
    ("p", "The following are minimum specifications. Equipment of equivalent or higher specification is acceptable. "
          "The bidder must fill the compliance column of Annexure-5 against each parameter."),
    ("h2", "5.1 Desktop Computer"),
    _spec([("Processor", "Intel Core i5 14th generation or higher"), ("Memory", "16 GB DDR5 RAM, expandable to 64 GB"),
           ("Storage", "512 GB NVMe SSD"), ("Form factor", "Tower"), ("Operating system", "Windows 11 Professional, 64-bit, pre-installed"),
           ("Ports", "Minimum 6 USB ports including 2 USB 3.2"), ("Warranty", "5 years comprehensive onsite warranty")]),
    ("h2", "5.2 Monitor"),
    _spec([("Screen size", "23.8 inch or 24 inch"), ("Panel", "IPS, anti-glare"), ("Resolution", "1920 x 1080 Full HD"),
           ("Inputs", "HDMI and DisplayPort"), ("Warranty", "5 years comprehensive onsite warranty")]),
    ("h2", "5.3 Laptop"),
    _spec([("Processor", "Intel Core i5 13th generation or higher"), ("Memory", "16 GB RAM"), ("Storage", "512 GB SSD"),
           ("Display", "14 inch Full HD anti-glare"), ("Operating system", "Windows 11 Professional"),
           ("Warranty", "3 years onsite warranty")]),
    ("h2", "5.4 Access Switch (24-port)"),
    _spec([("Ports", "24 x 1G PoE+ ports"), ("Uplinks", "4 x 10G SFP+ uplink ports"), ("Layer", "Layer 3 managed"),
           ("PoE budget", "Minimum 370 W"), ("Warranty", "5 years with next business day replacement")]),
    ("h2", "5.5 Core Switch (48-port)"),
    _spec([("Ports", "48 x 1G PoE+ ports"), ("Layer", "Layer 3 managed with static routing"), ("PoE budget", "Minimum 740 W"),
           ("Warranty", "5 years with next business day replacement")]),
    ("h2", "5.6 Wireless Access Point"),
    _spec([("Standard", "Wi-Fi 6 (802.11ax)"), ("Mounting", "Ceiling mount"), ("Power", "PoE powered"),
           ("Management", "Centralised cloud or controller management")]),
    ("h2", "5.7 Next Generation Firewall"),
    _spec([("Firewall throughput", "Minimum 20 Gbps"), ("Form factor", "1U rack mountable"),
           ("Subscriptions", "IPS, antivirus and web filtering for 3 years"), ("Warranty", "3 years")]),
    ("h2", "5.8 Online UPS"),
    _spec([("Capacity", "3 kVA"), ("Topology", "Online double conversion"), ("Backup", "Minimum 30 minutes at full load"),
           ("Warranty", "3 years including batteries")]),
    ("h2", "5.9 Network Laser Printer"),
    _spec([("Type", "Monochrome laser, A4"), ("Speed", "Minimum 35 ppm"), ("Duplex", "Automatic duplex printing"),
           ("Network", "Ethernet")]),
    ("h2", "5.10 Network Attached Storage"),
    _spec([("Drive bays", "8 bays"), ("Form factor", "2U rack mount"), ("Network", "4 x 1GbE")]),

    ("h1", "SECTION VI – SCHEDULE OF REQUIREMENTS (BILL OF QUANTITIES)"),
    ("table", ["S. No.", "Item description", "Unit", "Quantity"], [
        ["1", "Desktop Computer as per specification 5.1 (Core i5, 16 GB RAM, 512 GB SSD, tower)", "Nos.", "85"],
        ["2", "24 inch Full HD IPS Monitor as per specification 5.2", "Nos.", "85"],
        ["3", "Laptop as per specification 5.3 (Core i5, 16 GB RAM, 512 GB SSD, 14 inch)", "Nos.", "20"],
        ["4", "24-port Layer 3 PoE+ Access Switch as per specification 5.4", "Nos.", "12"],
        ["5", "48-port Layer 3 PoE+ Core Switch as per specification 5.5", "Nos.", "2"],
        ["6", "Wi-Fi 6 ceiling mount Access Point as per specification 5.6", "Nos.", "36"],
        ["7", "Next Generation Firewall, 1U, as per specification 5.7", "Nos.", "1"],
        ["8", "3 kVA Online UPS as per specification 5.8", "Nos.", "12"],
        ["9", "Network monochrome laser printer with duplex as per specification 5.9", "Nos.", "12"],
        ["10", "8-bay rack mount NAS as per specification 5.10", "Nos.", "1"],
        ["11", "Cat6 UTP cable box of 305 m", "Box", "40"],
    ], [12, 118, 18, 22]),
    ("p", "Installation, configuration, cabling labour, training and the resident engineer are part of the scope of work and "
          "shall be included in the quoted item rates."),

    ("h1", "SECTION VII – COMMERCIAL TERMS AND CONDITIONS"),
    ("h2", "7.1 Prices and taxes"),
    ("clause", "7.1.1", "Prices shall be firm and fixed until completion of the contract and shall be inclusive of freight, "
                        "insurance, installation and all incidental charges. GST shall be shown separately."),
    ("clause", "7.1.2", "No price variation will be allowed on account of change in exchange rates or input costs."),
    ("h2", "7.2 Delivery and completion"),
    ("clause", "7.2.1", "The supplier shall deliver all items within 45 days and complete installation and commissioning "
                        "within 60 days from the date of issue of the purchase order."),
    ("clause", "7.2.2", "Delivery shall be made at the respective ward offices in Nashik as per the distribution list "
                        "provided with the purchase order."),
    ("h2", "7.3 Payment terms"),
    ("clause", "7.3.1", "80% of the contract value shall be paid on delivery and inspection of the goods, and the balance "
                        "20% on successful installation, commissioning and acceptance."),
    ("clause", "7.3.2", "Payment shall be released within 30 days of receipt of a valid GST invoice along with the delivery "
                        "challan and installation report. No advance payment will be made."),
    ("h2", "7.4 Warranty and support"),
    ("clause", "7.4.1", "All desktops, monitors and network switches shall carry a comprehensive onsite warranty of five "
                        "years from the date of acceptance, covering all parts and labour."),
    ("clause", "7.4.2", "The bidder shall attend to complaints within 4 hours and resolve them within 24 hours of logging "
                        "the complaint. A standby unit shall be provided if a fault is not rectified within 48 hours."),
    ("clause", "7.4.3", "The bidder must operate a 24x7 helpdesk with a toll-free number and a web-based complaint logging "
                        "system during the warranty period."),
    ("h2", "7.5 Performance security"),
    ("clause", "7.5.1", "The successful bidder shall furnish a performance security of 5% of the contract value in the form "
                        "of a bank guarantee within 15 days of the purchase order, valid for sixty days beyond the warranty period."),
    ("h2", "7.6 Liquidated damages"),
    ("clause", "7.6.1", "In case of delay in supply or commissioning, liquidated damages at 0.5% of the value of the delayed "
                        "items per week or part thereof shall be levied, subject to a maximum of 10% of the contract value."),
    ("h2", "7.7 Inspection and acceptance"),
    ("clause", "7.7.1", "All goods shall be inspected by a committee constituted by the Purchaser. The bidder shall "
                        "demonstrate that the supplied equipment conforms to the specifications before acceptance."),
    ("clause", "7.7.2", "Equipment must be new, of the latest model and not declared end-of-life by the OEM for at least "
                        "five years from the date of bid submission."),
    ("clause", "7.7.3", "The bidder must comply with the E-Waste (Management) Rules, 2022 and take back packaging material."),

    ("h1", "SECTION VIII – EVALUATION OF BIDS"),
    ("clause", "8.1", "The technical bids of bidders meeting the eligibility criteria will be evaluated for compliance with "
                      "the technical specifications. Only technically compliant bidders will be considered for opening of "
                      "the financial bid."),
    ("clause", "8.2", "The contract will be awarded to the lowest evaluated (L1) technically compliant bidder on the basis of "
                      "the total cost of all items in the Bill of Quantities, inclusive of GST."),
    ("clause", "8.3", "Purchase preference shall be given to Micro and Small Enterprises in accordance with the Public "
                      "Procurement Policy for MSEs Order, 2012, and to Class-I local suppliers under the Make in India order."),
    ("clause", "8.4", "The Purchaser reserves the right to vary the quantities by up to 25% at the time of award at the same "
                      "unit rates."),

    ("h1", "SECTION IX – GENERAL CONDITIONS OF CONTRACT"),
    ("clause", "9.1", "Termination for default: the Purchaser may terminate the contract in whole or in part if the supplier "
                      "fails to deliver any or all of the goods within the period specified in the contract."),
    ("clause", "9.2", "Force majeure: the supplier shall not be liable for forfeiture of its performance security or "
                      "liquidated damages if the delay in performance is the result of an event of force majeure."),
    ("clause", "9.3", "Confidentiality: the supplier shall not disclose any information relating to the Purchaser's network, "
                      "systems or data to any third party, and shall comply with the Digital Personal Data Protection Act, 2023."),
    ("clause", "9.4", "Indemnity: the supplier shall indemnify the Purchaser against all third-party claims of infringement "
                      "of patent, trademark or industrial design rights arising from use of the goods."),
    ("clause", "9.5", "Settlement of disputes: disputes shall be resolved by arbitration under the Arbitration and "
                      "Conciliation Act, 1996. The venue of arbitration shall be Nashik and courts at Nashik shall have "
                      "exclusive jurisdiction."),
    ("clause", "9.6", "The supplier's aggregate liability under the contract shall not exceed the contract value, except in "
                      "cases of fraud, gross negligence or wilful misconduct."),

    ("h1", "ANNEXURE-1: CHECKLIST OF DOCUMENTS"),
    ("table", ["S. No.", "Document", "Page no. in bid"], [
        ["1", "Bid covering letter (Annexure-2)", ""], ["2", "Tender fee and EMD receipt or MSE exemption certificate", ""],
        ["3", "Certificate of incorporation, GST and PAN", ""], ["4", "Audited balance sheets for three years and CA certificate", ""],
        ["5", "Work orders and completion certificates", ""], ["6", "ISO 9001:2015 certificate", ""],
        ["7", "Manufacturer's Authorisation Forms (Annexure-3)", ""], ["8", "Declaration of non-blacklisting (Annexure-4)", ""],
        ["9", "Technical compliance statement (Annexure-5)", ""], ["10", "Local content self-certificate", ""],
    ], [12, 128, 30]),
    ("h1", "ANNEXURE-2: BID COVERING LETTER"),
    ("p", "To, The Chief Executive Officer, Godavari Valley Smart City Development Corporation Limited, Nashik."),
    ("p", "Sir, having examined the tender document, we the undersigned offer to supply and install the equipment in "
          "conformity with the said document for the sum shown in the financial bid. We undertake, if our bid is accepted, "
          "to complete the work within the period specified. We agree to abide by this bid for the bid validity period."),
    ("p", "Signature of authorised signatory, name, designation and seal of the bidder."),
    ("h1", "ANNEXURE-3: MANUFACTURER'S AUTHORISATION FORM"),
    ("p", "We, the manufacturer of the goods offered, hereby authorise the bidder to submit a bid and to negotiate and sign "
          "the contract for the goods manufactured by us against the above tender. We extend our full warranty for the "
          "goods offered by the above firm."),
    ("h1", "ANNEXURE-4: DECLARATION REGARDING BLACKLISTING"),
    ("p", "We hereby declare that our firm has not been blacklisted or debarred by any Central or State Government "
          "department, PSU or local body as on the date of bid submission."),
    ("h1", "ANNEXURE-5: TECHNICAL COMPLIANCE STATEMENT"),
    ("p", "The bidder shall state against each parameter of Section V whether the offered product complies (Yes or No), "
          "along with the make and model offered and the page number of the OEM datasheet as evidence."),
    ("h1", "ANNEXURE-6: FINANCIAL BID FORMAT"),
    ("table", ["S. No.", "Item", "Qty", "Unit rate (Rs.)", "GST (%)", "Total (Rs.)"],
     [[str(i), f"Item {i} of the Bill of Quantities", "", "", "", ""] for i in range(1, 12)], [12, 70, 16, 26, 20, 26]),
]


# --------------------------------------------------------------------------- tender 2: university (DOCX, QCBS)

KONKAN: list[tuple] = [
    ("title", "Konkan Technical University"),
    ("p", "Established under the Maharashtra Act No. XIV of 2014"),
    ("p", "University Campus, Kuwarbav MIDC Road, Ratnagiri 415639, Maharashtra"),
    ("p", "GSTIN: 27AAAJK7715R1ZQ"),
    ("title", "Request for Proposal"),
    ("p", "RFP No.: KTU/ICT/RFP/2026/19"),
    ("p", "Subject: Selection of a System Integrator for Campus Digital Infrastructure – Smart Classrooms, Research "
          "Computing and Campus Network"),
    ("p", "Date of issue: 24 September 2026"),
    ("break",),

    ("h1", "Invitation for Proposals"),
    ("p", "Konkan Technical University (the University) invites proposals from reputed system integrators for the "
          "supply, installation, integration and maintenance of campus digital infrastructure at its Ratnagiri campus. "
          "Selection will follow the Quality and Cost Based Selection (QCBS) method described in this RFP."),
    ("table", ["Particulars", "Details"], [
        ["RFP number", "KTU/ICT/RFP/2026/19"],
        ["Estimated project value", "Rs. 3.60 crore"],
        ["Bid security (EMD)", "Rs. 7,20,000 by bank guarantee or online transfer"],
        ["Pre-proposal conference", "06 October 2026 at 11:00 hrs, Senate Hall"],
        ["Last date for submission of queries", "05 October 2026"],
        ["Last date for submission of proposals", "26 October 2026 at 17:00 hrs"],
        ["Opening of technical proposals", "27 October 2026 at 11:00 hrs"],
        ["Proposal validity", "180 days from the last date of submission"],
        ["Contact", "Dr. Sunil Patwardhan, Registrar, procurement@ktu.ac.in"],
    ], [60, 110]),

    ("break",),
    ("h1", "Background and Objectives"),
    ("h2", "1.1 About the University"),
    ("p", "The University offers undergraduate and postgraduate programmes in engineering, applied sciences and marine "
          "technology to about 6,500 students. A new academic block with 40 smart classrooms and a research computing "
          "facility is being commissioned for the academic year 2027-28."),
    ("h2", "1.2 Objectives"),
    ("p", "The project aims to provide every classroom with collaboration equipment, to equip faculty with modern "
          "notebooks, to create a small research computing and storage facility, and to upgrade the campus network with "
          "Wi-Fi 6 coverage and a next generation firewall."),

    ("break",),
    ("h1", "Pre-Qualification Criteria"),
    ("p", "The bidder must meet each of the following pre-qualification criteria. Proposals not meeting any criterion will "
          "be rejected without further evaluation."),
    ("clause", "2.1", "The bidder must be a company registered in India under the Companies Act, 2013 or earlier Acts, and "
                      "must have been in operation for a minimum of seven years."),
    ("clause", "2.2", "The bidder must have an average annual turnover of at least Rs. 50 crore during the last three "
                      "financial years, of which not less than 60% should be from ICT system integration."),
    ("clause", "2.3", "The bidder must have executed at least two similar projects of value not less than Rs. 1.5 crore each "
                      "for universities, colleges or government institutions in the last five years."),
    ("clause", "2.4", "The bidder must have supplied at least 500 laptops to educational institutions in the last three years."),
    ("clause", "2.5", "The bidder must possess valid ISO 9001:2015 and ISO/IEC 20000-1:2018 certifications."),
    ("clause", "2.6", "The bidder must have at least 20 OEM-certified engineers on its payroll."),
    ("clause", "2.7", "The bidder should have a service centre in Maharashtra capable of providing onsite support within "
                      "one business day."),
    ("clause", "2.8", "The bidder shall not be under a declaration of ineligibility for corrupt or fraudulent practices."),
    ("clause", "2.9", "The bidder must submit Manufacturer's Authorisation Forms for laptops, servers, switches and firewalls."),

    ("break",),
    ("h1", "Scope of Work"),
    ("h2", "3.1 Smart classrooms"),
    ("clause", "3.1.1", "The system integrator shall equip meeting and seminar rooms with video collaboration bars, and "
                        "shall integrate them with the University's Microsoft Teams tenant."),
    ("h2", "3.2 Faculty computing"),
    ("clause", "3.2.1", "The system integrator shall supply premium notebooks for faculty, imaged with the University's "
                        "standard build and enrolled in device management."),
    ("h2", "3.3 Research computing and storage"),
    ("clause", "3.3.1", "The system integrator shall supply, rack and commission two rack servers, a network attached "
                        "storage system and the backup software, and shall configure daily backups with 30-day retention."),
    ("clause", "3.3.2", "The system integrator shall migrate approximately 6 TB of research data from existing file servers."),
    ("h2", "3.4 Campus network"),
    ("clause", "3.4.1", "The system integrator shall design and deploy Wi-Fi 6 coverage for the academic block and hostels, "
                        "replace distribution switches and install a next generation firewall pair in high availability."),
    ("h2", "3.5 Warranty, support and training"),
    ("clause", "3.5.1", "All hardware shall be covered by a comprehensive onsite warranty of three years."),
    ("clause", "3.5.2", "The system integrator must provide a dedicated onsite engineer at the campus during working hours "
                        "for the first six months after go-live."),
    ("clause", "3.5.3", "Critical incidents must be responded to within 2 hours and resolved within 8 hours."),
    ("clause", "3.5.4", "The system integrator shall train 20 IT staff on administration of servers, storage and the firewall."),
    ("clause", "3.5.5", "Preference will be given to solutions with energy-efficient, ENERGY STAR or EPEAT registered devices."),

    ("break",),
    ("h1", "Technical Specifications"),
    ("h2", "4.1 Faculty Notebook"),
    _spec([("Processor", "Intel Core Ultra 7 or Intel Core i7 13th generation or higher"), ("Memory", "32 GB RAM"),
           ("Storage", "1 TB NVMe SSD"), ("Display", "14 inch, Full HD or higher"), ("Operating system", "Windows 11 Professional"),
           ("Warranty", "3 years onsite")]),
    ("h2", "4.2 Research Workstation"),
    _spec([("Processor", "Intel Core i9 14th generation"), ("Memory", "64 GB RAM"), ("Storage", "2 TB NVMe SSD"),
           ("Graphics", "NVIDIA RTX A2000 12 GB or better"), ("Warranty", "3 years onsite")]),
    ("h2", "4.3 Rack Server"),
    _spec([("Processor", "2 x Intel Xeon Silver"), ("Memory", "128 GB DDR5 RAM"), ("Storage", "3.84 TB SSD usable"),
           ("Form factor", "2U rack"), ("Power supply", "Dual redundant hot-plug power supplies"), ("Warranty", "3 years onsite")]),
    ("h2", "4.4 Network Attached Storage"),
    _spec([("Drive bays", "Minimum 8 bays"), ("Form factor", "Rack mount"), ("Drives", "Populated with 8 TB NAS-grade drives")]),
    ("h2", "4.5 Distribution Switch"),
    _spec([("Ports", "48 x 1G PoE+"), ("Layer", "Layer 3"), ("Management", "Web and CLI management")]),
    ("h2", "4.6 Wireless Access Point"),
    _spec([("Standard", "Wi-Fi 6"), ("Radio", "4x4 MU-MIMO"), ("Mounting", "Ceiling")]),
    ("h2", "4.7 Next Generation Firewall"),
    _spec([("Throughput", "Minimum 20 Gbps firewall throughput"), ("Form factor", "1U"),
           ("High availability", "Active-passive HA pair")]),
    ("h2", "4.8 Video Collaboration Bar"),
    _spec([("Camera", "4K camera with auto framing"), ("Certification", "Certified for Microsoft Teams Rooms")]),
    ("h2", "4.9 Monitors for research labs"),
    _spec([("Size", "27 inch"), ("Resolution", "4K UHD 3840 x 2160"), ("Connectivity", "USB-C with power delivery")]),

    ("break",),
    ("h1", "Bill of Material"),
    ("table", ["S. No.", "Description", "Unit", "Qty"], [
        ["1", "Faculty notebook, Core Ultra 7, 32 GB RAM, 1 TB SSD, 14 inch", "Nos.", "40"],
        ["2", "Research workstation, Core i9, 64 GB RAM, RTX A2000", "Nos.", "6"],
        ["3", "27 inch 4K USB-C monitor", "Nos.", "12"],
        ["4", "2U rack server, dual Xeon Silver, 128 GB RAM", "Nos.", "2"],
        ["5", "8-bay rack NAS", "Nos.", "1"],
        ["6", "8 TB NAS hard drives", "Nos.", "8"],
        ["7", "Backup software, 5 instances, annual subscription", "Nos.", "1"],
        ["8", "Windows Server 2022 Standard 16-core licence", "Nos.", "2"],
        ["9", "48-port PoE+ Layer 3 distribution switch", "Nos.", "6"],
        ["10", "Wi-Fi 6 ceiling access point, 4x4", "Nos.", "40"],
        ["11", "Next generation firewall, 1U, 20 Gbps", "Nos.", "2"],
        ["12", "Video collaboration bar, 4K, Teams certified", "Nos.", "10"],
        ["13", "Microsoft 365 Business Standard, annual, per user", "Users", "150"],
    ], [14, 112, 18, 16]),

    ("break",),
    ("h1", "Evaluation Methodology"),
    ("clause", "6.1", "Proposals will be evaluated using Quality and Cost Based Selection with a weightage of 70:30 for the "
                      "technical and financial proposals respectively."),
    ("clause", "6.2", "Only bidders scoring a minimum of 70 marks out of 100 in the technical evaluation will qualify for "
                      "opening of the financial proposal."),
    ("table", ["S. No.", "Technical evaluation criterion", "Maximum marks"], [
        ["1", "Average annual turnover above the minimum requirement", "10"],
        ["2", "Similar projects for educational or government institutions", "20"],
        ["3", "Certified engineers on payroll", "10"],
        ["4", "Approach, methodology and project plan", "25"],
        ["5", "Compliance with technical specifications", "25"],
        ["6", "Technical presentation", "10"],
    ], [14, 120, 36]),
    ("clause", "6.3", "The combined score will be computed as 0.70 x technical score + 0.30 x financial score, where the "
                      "financial score of the lowest proposal is 100 and others are scored proportionately."),

    ("break",),
    ("h1", "Commercial Terms"),
    ("clause", "7.1", "Prices shall be quoted in Indian Rupees, exclusive of GST, which shall be shown separately."),
    ("clause", "7.2", "Delivery of all hardware shall be completed within 8 weeks of the purchase order and the project shall "
                      "go live within 12 weeks."),
    ("clause", "7.3", "Payment: 10% advance against an advance bank guarantee of equal value, 60% on delivery, 20% on "
                      "go-live and 10% after three months of successful operation."),
    ("clause", "7.4", "Payment will be released within 45 days of receipt of an undisputed invoice."),
    ("clause", "7.5", "The successful bidder shall submit a performance bank guarantee of 10% of the contract value valid "
                      "until the end of the warranty period."),
    ("clause", "7.6", "Liquidated damages of 1% of the contract value per week of delay shall be levied, subject to a maximum "
                      "of 10%."),
    ("clause", "7.7", "The system integrator shall accept unlimited liability for any loss of University data caused by its "
                      "personnel."),

    ("break",),
    ("h1", "General Conditions"),
    ("clause", "8.1", "The contract shall be governed by the laws of India and courts at Ratnagiri shall have jurisdiction."),
    ("clause", "8.2", "The system integrator shall comply with the Digital Personal Data Protection Act, 2023 in respect of "
                      "student and staff data."),
    ("clause", "8.3", "The University may terminate the contract for convenience with 30 days' notice."),
    ("clause", "8.4", "Sub-contracting of any part of the work requires the prior written approval of the University."),

    ("break",),
    ("h1", "Annexure A – Proposal Submission Form"),
    ("p", "We, the undersigned, offer to provide the services for the above in accordance with your RFP. We are hereby "
          "submitting our proposal, which includes the technical proposal and the financial proposal sealed separately."),
    ("h1", "Annexure B – Format for Similar Projects"),
    ("table", ["S. No.", "Client", "Scope", "Value (Rs.)", "Completion date"],
     [[str(i), "", "", "", ""] for i in range(1, 6)], [14, 40, 60, 28, 28]),
    ("h1", "Annexure C – Manufacturer's Authorisation Form"),
    ("p", "We, the OEM, confirm that the bidder is authorised to offer our products for this RFP and that we will support "
          "the products for the warranty period."),
]
