"""Content of the DES Pune University RFP used for the Data Care Corp trial.

A request for proposal in the structure of an Indian university purchase:
notice with key dates, instructions to bidders, eligibility, scope, technical
specifications for each product, bill of quantities (50 of each item for the
new computer laboratories), commercial terms, L1 evaluation, general conditions
and annexure forms. Same element format as ``tender_content.py``.
"""

from __future__ import annotations

ORG = "DES Pune University"
REF = "DESPU/PUR/ICT-LAB/2026-27/14"


def _spec(rows: list[tuple[str, str]]) -> tuple:
    return ("table", ["S. No.", "Parameter", "Minimum specification"],
            [[str(i), p, s] for i, (p, s) in enumerate(rows, start=1)], [12, 45, 113])


DES: list[tuple] = [
    ("title", ORG),
    ("p", "(Established under the Maharashtra Self-financed Universities (Establishment and Regulation) Act and "
          "sponsored by the Deccan Education Society, Pune)"),
    ("p", "DES Campus, Fergusson College Road, Shivajinagar, Pune 411004, Maharashtra"),
    ("p", "GSTIN: 27AAATD0421B1ZK"),
    ("p", "Purchase Section, Office of the Registrar · Telephone: 020 2567 1200 · E-mail: purchase@despu.edu.in"),
    ("title", "REQUEST FOR PROPOSAL"),
    ("p", "RFP No.: " + REF),
    ("p", "Subject: Supply, Installation and Commissioning of Computers, Peripherals, Headsets and Graphics Cards for "
          "the New Computer, Language and AI Laboratories"),
    ("p", "Date of issue: 28 September 2026"),
    ("p", "Mode of bidding: Two-envelope system (technical bid and financial bid), sealed physical submission with a "
          "soft copy on pen drive"),
    ("p", "This document contains twelve pages including the annexures. Bidders are requested to read the complete "
          "document carefully before submitting their proposal. The document is not transferable."),
    ("break",),

    ("h1", "SECTION I – NOTICE INVITING PROPOSALS"),
    ("clause", "1.1", "The Registrar, DES Pune University (hereinafter referred to as the University), invites sealed "
                      "proposals from eligible authorised dealers, distributors and system integrators for the supply, "
                      "installation and commissioning of desktop computers, monitors, keyboards, mice, headsets, "
                      "headphones, webcams, laptops, graphics cards and UPS units for the new laboratories on the "
                      "University campus, as detailed in this document."),
    ("clause", "1.2", "The University is setting up three new laboratories in the academic year 2026-27: a Computer "
                      "Programming Laboratory, a Language and Communication Laboratory and an Artificial Intelligence and "
                      "Machine Learning (AI/ML) Laboratory. Each item is required in a quantity of fifty (50) units."),
    ("clause", "1.3", "The key data and critical dates of this RFP are given below."),
    ("table", ["S. No.", "Particulars", "Details"], [
        ["1", "RFP number", REF],
        ["2", "Estimated cost of the purchase", "Rs. 1.05 crore (inclusive of GST)"],
        ["3", "Earnest Money Deposit (EMD)", "Rs. 2,00,000 (Rupees two lakh only) by demand draft or bank guarantee"],
        ["4", "RFP document fee", "Rs. 2,360 (non-refundable, inclusive of GST)"],
        ["5", "Date of issue", "28 September 2026"],
        ["6", "Last date for receipt of pre-bid queries", "05 October 2026 up to 17:00 hrs"],
        ["7", "Pre-bid meeting", "07 October 2026 at 11:00 hrs, Board Room, Registrar's Office, DES Campus"],
        ["8", "Last date and time for submission of proposals", "19 October 2026 up to 15:00 hrs"],
        ["9", "Opening of technical bids", "19 October 2026 at 16:00 hrs"],
        ["10", "Proposal validity", "90 days from the last date of submission"],
        ["11", "Delivery and installation period", "30 days from the date of the purchase order"],
    ], [12, 70, 88]),
    ("clause", "1.4", "The RFP document can be downloaded from the University website (www.despu.edu.in/tenders). The "
                      "document fee shall be paid by demand draft in favour of \"DES Pune University\" payable at Pune, "
                      "and enclosed with the technical bid."),
    ("clause", "1.5", "Micro and Small Enterprises (MSEs) registered with Udyam or NSIC for the items in this RFP are "
                      "exempted from payment of the RFP document fee and EMD, subject to submission of a valid "
                      "registration certificate with the technical bid."),
    ("clause", "1.6", "The University reserves the right to accept or reject any or all proposals, in full or in part, "
                      "without assigning any reason, and its decision shall be final."),
    ("clause", "1.7", "Proposals received after the due date and time will not be accepted under any circumstances. "
                      "Proposals sent by fax or e-mail will not be considered."),

    ("h1", "SECTION II – INSTRUCTIONS TO BIDDERS"),
    ("h2", "2.1 General"),
    ("clause", "2.1.1", "The bidder shall examine all instructions, forms, terms, specifications and other information in "
                        "the RFP document. Failure to furnish all information required, or submission of a proposal not "
                        "substantially responsive to the RFP in every respect, will be at the bidder's risk and may result "
                        "in rejection of the proposal."),
    ("clause", "2.1.2", "The bidder shall bear all costs associated with the preparation and submission of its proposal, "
                        "and the University will in no case be responsible or liable for those costs."),
    ("clause", "2.1.3", "Consortium or joint venture proposals are not permitted. Only one proposal shall be submitted by a "
                        "bidder; firms with common partners or directors shall not submit separate proposals."),
    ("clause", "2.1.4", "The bidder may visit the laboratory sites on any working day between 10:00 and 16:00 hrs before "
                        "the submission date, with prior intimation to the Purchase Section."),
    ("h2", "2.2 Clarifications and pre-bid meeting"),
    ("clause", "2.2.1", "A prospective bidder requiring any clarification shall send its queries by e-mail to "
                        "purchase@despu.edu.in in the prescribed format before the last date for pre-bid queries."),
    ("clause", "2.2.2", "Replies to the queries and any amendment to the RFP will be published on the University website "
                        "as a corrigendum and shall form part of the RFP document."),
    ("h2", "2.3 Preparation and submission of proposals"),
    ("clause", "2.3.1", "The proposal shall be submitted in two separately sealed envelopes: Envelope A (technical bid) and "
                        "Envelope B (financial bid), both placed in an outer envelope superscribed with the RFP number and "
                        "the words \"Do not open before 19 October 2026, 16:00 hrs\"."),
    ("clause", "2.3.2", "Price shall not be indicated anywhere in the technical bid. Any proposal disclosing price in the "
                        "technical bid will be summarily rejected."),
    ("clause", "2.3.3", "The technical bid must contain all documents listed in the checklist at Annexure-1, page "
                        "numbered, signed and stamped by the authorised signatory on every page."),
    ("clause", "2.3.4", "The bidder must quote for all items in the Bill of Quantities. Partial proposals will be treated "
                        "as non-responsive."),
    ("clause", "2.3.5", "Prices shall be quoted in Indian Rupees only, with GST shown separately against each item in the "
                        "financial bid format at Annexure-6."),
    ("clause", "2.3.6", "Conditional proposals shall not be accepted. Any deviation from the specifications or terms must be "
                        "stated clearly in the technical compliance statement at Annexure-5."),
    ("clause", "2.3.7", "The bidder must enclose a letter of authority or board resolution in favour of the authorised "
                        "signatory."),
    ("h2", "2.4 Earnest money deposit"),
    ("clause", "2.4.1", "The EMD of unsuccessful bidders will be returned without interest within 30 days of the award of "
                        "the purchase order. The EMD of the successful bidder will be returned on receipt of the performance "
                        "security."),
    ("clause", "2.4.2", "The EMD shall be forfeited if the bidder withdraws its proposal during the period of validity or "
                        "fails to furnish the performance security within the stipulated time."),

    ("h1", "SECTION III – ELIGIBILITY CRITERIA"),
    ("p", "Only bidders fulfilling all of the following criteria shall be considered for evaluation of the technical bid. "
          "Documentary evidence for each criterion must be enclosed."),
    ("table", ["S. No.", "Eligibility criterion", "Supporting documents"], [
        ["1", "The bidder should be a company registered under the Companies Act, a limited liability partnership or a "
              "partnership firm registered in India, in existence for at least three years as on the date of issue of "
              "this RFP.", "Certificate of incorporation or partnership deed"],
        ["2", "The bidder should have an average annual turnover of not less than Rs. 2 crore from the supply of computer "
              "hardware in the last three financial years (2023-24, 2024-25 and 2025-26).",
         "Audited balance sheets and CA certificate"],
        ["3", "The bidder should have a positive net worth as on 31 March 2026.", "CA certificate"],
        ["4", "The bidder should have successfully completed at least one order for the supply of computers or computer "
              "peripherals to an educational institution or government organisation of a value not less than Rs. 50 lakh "
              "during the last five years.", "Purchase orders with completion certificates"],
        ["5", "The bidder must hold a valid ISO 9001:2015 certificate.", "Copy of certificate"],
        ["6", "The bidder must be an authorised dealer or partner of the Original Equipment Manufacturer (OEM) for the "
              "quoted desktop computers, laptops and monitors, and submit a Manufacturer's Authorisation Form (MAF) in the "
              "format at Annexure-3.", "MAF from each OEM"],
        ["7", "The bidder should have a registered office or service centre in Pune or Pimpri-Chinchwad.",
         "Shop and establishment licence or GST registration showing the address"],
        ["8", "The bidder shall not have been blacklisted or debarred by any Central or State Government department, "
              "university or PSU as on the date of submission.", "Self-declaration at Annexure-4"],
        ["9", "The bidder must have a valid GST registration and PAN.", "GST certificate and PAN card"],
    ], [12, 108, 50]),

    ("h1", "SECTION IV – SCOPE OF WORK"),
    ("clause", "4.1", "The scope of work covers supply, transportation, unloading, installation, testing and commissioning "
                      "of the equipment listed in the Bill of Quantities at the three laboratories on the DES campus, "
                      "Shivajinagar, Pune."),
    ("clause", "4.2", "The laboratories and the seats to be equipped are listed below. The final allocation of items to "
                      "each laboratory will be confirmed with the purchase order."),
    ("table", ["S. No.", "Laboratory", "Location", "Seats"], [
        ["1", "Computer Programming Laboratory", "Second floor, Engineering Block", "50"],
        ["2", "Language and Communication Laboratory", "Ground floor, Humanities Block", "50"],
        ["3", "AI/ML Laboratory (existing workstations to be upgraded)", "Third floor, Engineering Block", "50"],
    ], [12, 70, 66, 22]),
    ("clause", "4.3", "All desktop computers and laptops shall be delivered with Windows 11 Professional pre-installed and "
                      "activated, and the University's standard software image shall be loaded by the bidder at site."),
    ("clause", "4.4", "Graphics cards shall be installed by the bidder in the University's existing AI/ML laboratory "
                      "workstations, with the latest drivers and the CUDA toolkit installed and a burn-in test performed "
                      "on each machine."),
    ("clause", "4.5", "Each desktop, monitor, laptop and UPS shall be tagged with an asset label supplied by the University, "
                      "and the bidder shall hand over a register of make, model and serial numbers."),
    ("clause", "4.6", "The bidder shall remove all packaging material from the campus on the day of installation."),
    ("clause", "4.7", "The bidder shall provide half-day training to the laboratory assistants on basic troubleshooting, "
                      "re-imaging and warranty call logging."),

    ("h1", "SECTION V – TECHNICAL SPECIFICATIONS"),
    ("p", "The following are minimum specifications. Products of equivalent or higher specification are acceptable. The "
          "bidder must fill the compliance column of Annexure-5 against each parameter and quote the make and model."),
    ("h2", "5.1 Desktop Computer"),
    _spec([("Processor", "Intel Core i5 14th generation or higher"), ("Memory", "16 GB DDR4 or DDR5 RAM, expandable to 32 GB"),
           ("Storage", "512 GB NVMe SSD"), ("Form factor", "Tower"), ("Operating system", "Windows 11 Professional, 64-bit, pre-installed"),
           ("Ports", "Minimum 6 USB ports including 2 USB 3.2, HDMI and VGA or DisplayPort"),
           ("Network", "Gigabit Ethernet"), ("Warranty", "3 years comprehensive onsite warranty")]),
    ("h2", "5.2 Monitor"),
    _spec([("Screen size", "23.8 inch or 24 inch"), ("Panel", "IPS, anti-glare"), ("Resolution", "1920 x 1080 Full HD"),
           ("Inputs", "HDMI and VGA"), ("Certification", "BEE star rating or ENERGY STAR"),
           ("Warranty", "3 years comprehensive onsite warranty")]),
    ("h2", "5.3 USB Keyboard"),
    _spec([("Type", "Wired USB keyboard, full size, 104 keys"), ("Design", "Spill resistant, low-profile keys"),
           ("Layout", "US English with Rupee symbol"), ("Warranty", "1 year")]),
    ("h2", "5.4 USB Optical Mouse"),
    _spec([("Type", "Wired USB optical mouse, 3 buttons with scroll wheel"), ("Resolution", "Minimum 1000 DPI"),
           ("Design", "Ambidextrous"), ("Warranty", "1 year")]),
    ("h2", "5.5 USB Headset with Microphone"),
    _spec([("Type", "Stereo over-ear USB headset for the language laboratory"),
           ("Microphone", "Noise-cancelling boom microphone"), ("Controls", "In-line volume and mute controls"),
           ("Cable", "Minimum 1.8 m USB cable"), ("Warranty", "1 year")]),
    ("h2", "5.6 Over-ear Headphones"),
    _spec([("Type", "Wired over-ear stereo headphones for multimedia listening"), ("Connector", "3.5 mm stereo jack"),
           ("Drivers", "Minimum 30 mm drivers"), ("Warranty", "1 year")]),
    ("h2", "5.7 Webcam"),
    _spec([("Resolution", "1080p Full HD at 30 fps"), ("Microphone", "Built-in microphone"),
           ("Mounting", "Universal monitor clip"), ("Interface", "USB, plug and play"), ("Warranty", "1 year")]),
    ("h2", "5.8 Laptop for Faculty"),
    _spec([("Processor", "Intel Core i5 13th generation or higher"), ("Memory", "16 GB RAM"), ("Storage", "512 GB SSD"),
           ("Display", "15.6 inch Full HD anti-glare"), ("Operating system", "Windows 11 Professional"),
           ("Battery", "Minimum 6 hours"), ("Warranty", "3 years onsite warranty")]),
    ("h2", "5.9 Graphics Card"),
    _spec([("GPU", "NVIDIA GeForce RTX 4060 or higher"), ("Video memory", "Minimum 8 GB GDDR6"),
           ("Interface", "PCI Express 4.0"), ("Support", "CUDA and cuDNN supported, compatible with the existing tower "
                                                       "workstations (minimum 550 W power supply)"),
           ("Warranty", "3 years")]),
    ("h2", "5.10 UPS"),
    _spec([("Capacity", "600 VA"), ("Topology", "Line interactive"), ("Backup", "Minimum 10 minutes for one desktop and monitor"),
           ("Outlets", "Minimum 3 Indian sockets"), ("Warranty", "2 years including battery")]),

    ("h1", "SECTION VI – BILL OF QUANTITIES"),
    ("table", ["S. No.", "Item description", "Unit", "Quantity"], [
        ["1", "Desktop Computer as per specification 5.1 (Core i5, 16 GB RAM, 512 GB SSD, tower)", "Nos.", "50"],
        ["2", "24 inch Full HD IPS Monitor as per specification 5.2", "Nos.", "50"],
        ["3", "USB Keyboard, wired, 104 keys, as per specification 5.3", "Nos.", "50"],
        ["4", "USB Optical Mouse, wired, as per specification 5.4", "Nos.", "50"],
        ["5", "USB Headset with noise-cancelling microphone as per specification 5.5", "Nos.", "50"],
        ["6", "Over-ear wired Headphones as per specification 5.6", "Nos.", "50"],
        ["7", "Full HD 1080p Webcam as per specification 5.7", "Nos.", "50"],
        ["8", "Laptop for faculty as per specification 5.8 (Core i5, 16 GB RAM, 512 GB SSD, 15.6 inch)", "Nos.", "50"],
        ["9", "Graphics Card, NVIDIA RTX 4060 8 GB, as per specification 5.9", "Nos.", "50"],
        ["10", "600 VA line interactive UPS as per specification 5.10", "Nos.", "50"],
    ], [12, 118, 18, 22]),
    ("p", "Installation, imaging, asset tagging, graphics card fitment and training are part of the scope of work and "
          "shall be included in the quoted item rates."),

    ("h1", "SECTION VII – COMMERCIAL TERMS AND CONDITIONS"),
    ("h2", "7.1 Prices and taxes"),
    ("clause", "7.1.1", "Prices shall be firm and fixed until completion of the order and shall be inclusive of freight, "
                        "insurance, installation and all incidental charges. GST shall be shown separately."),
    ("clause", "7.1.2", "No price variation will be allowed on any account during the validity of the order."),
    ("h2", "7.2 Delivery and installation"),
    ("clause", "7.2.1", "The supplier shall deliver all items within 21 days and complete installation and commissioning "
                        "within 30 days from the date of the purchase order."),
    ("clause", "7.2.2", "Delivery shall be made at the Central Stores, DES Campus, Shivajinagar, Pune, on working days "
                        "between 10:00 and 17:00 hrs."),
    ("h2", "7.3 Payment terms"),
    ("clause", "7.3.1", "90% of the order value shall be paid on delivery, installation and acceptance of the goods, and "
                        "the balance 10% after submission of the performance security."),
    ("clause", "7.3.2", "Payment shall be released within 30 days of receipt of a valid GST invoice along with the delivery "
                        "challan, installation report and inspection certificate. No advance payment will be made."),
    ("h2", "7.4 Warranty and support"),
    ("clause", "7.4.1", "All desktop computers, monitors and laptops shall carry a comprehensive onsite warranty of three "
                        "years from the date of acceptance, covering all parts and labour."),
    ("clause", "7.4.2", "Graphics cards shall carry a warranty of three years and UPS units two years including batteries. "
                        "Keyboards, mice, headsets, headphones and webcams shall carry a warranty of one year."),
    ("clause", "7.4.3", "The bidder shall attend to complaints within 24 hours and resolve them within 72 hours of logging "
                        "the complaint. A standby unit shall be provided if a fault is not rectified within 72 hours."),
    ("h2", "7.5 Performance security"),
    ("clause", "7.5.1", "The successful bidder shall furnish a performance security of 3% of the order value in the form of "
                        "a bank guarantee or fixed deposit receipt within 15 days of the purchase order, valid for sixty "
                        "days beyond the warranty period."),
    ("h2", "7.6 Liquidated damages"),
    ("clause", "7.6.1", "In case of delay in supply or installation, liquidated damages at 0.5% of the value of the delayed "
                        "items per week or part thereof shall be levied, subject to a maximum of 10% of the order value."),
    ("h2", "7.7 Inspection and acceptance"),
    ("clause", "7.7.1", "All goods shall be inspected by a committee constituted by the University. The bidder shall "
                        "demonstrate that the supplied equipment conforms to the specifications before acceptance."),
    ("clause", "7.7.2", "Equipment must be new, genuine and of the latest model, supplied with the OEM's original packing "
                        "and warranty cards. Refurbished or grey-market products will be rejected."),
    ("clause", "7.7.3", "The bidder must comply with the E-Waste (Management) Rules, 2022 and take back packaging material."),

    ("h1", "SECTION VIII – EVALUATION OF PROPOSALS"),
    ("clause", "8.1", "The technical bids of bidders meeting the eligibility criteria will be evaluated for compliance with "
                      "the technical specifications. Only technically compliant bidders will be considered for opening of "
                      "the financial bid."),
    ("clause", "8.2", "The purchase order will be awarded to the lowest evaluated (L1) technically compliant bidder on the "
                      "basis of the total cost of all items in the Bill of Quantities, inclusive of GST."),
    ("clause", "8.3", "Purchase preference shall be given to Micro and Small Enterprises in accordance with the Public "
                      "Procurement Policy for MSEs Order, 2012."),
    ("clause", "8.4", "The University reserves the right to vary the quantities by up to 20% at the time of award at the "
                      "same unit rates."),
    ("clause", "8.5", "The University may negotiate with the L1 bidder only if the L1 price is found to be abnormally high "
                      "in comparison with the prevailing market price."),

    ("h1", "SECTION IX – GENERAL CONDITIONS OF CONTRACT"),
    ("clause", "9.1", "Termination for default: the University may terminate the order in whole or in part if the supplier "
                      "fails to deliver any or all of the goods within the period specified in the order."),
    ("clause", "9.2", "Force majeure: the supplier shall not be liable for forfeiture of its performance security or "
                      "liquidated damages if the delay in performance is the result of an event of force majeure."),
    ("clause", "9.3", "Confidentiality: the supplier shall not disclose any information relating to the University's "
                      "network, systems or student data to any third party, and shall comply with the Digital Personal "
                      "Data Protection Act, 2023."),
    ("clause", "9.4", "Indemnity: the supplier shall indemnify the University against all third-party claims of "
                      "infringement of patent, trademark or industrial design rights arising from use of the goods."),
    ("clause", "9.5", "Settlement of disputes: disputes shall be resolved amicably, failing which by arbitration under the "
                      "Arbitration and Conciliation Act, 1996. The venue of arbitration shall be Pune and courts at Pune "
                      "shall have exclusive jurisdiction."),
    ("clause", "9.6", "The supplier's aggregate liability under the order shall not exceed the order value, except in cases "
                      "of fraud, gross negligence or wilful misconduct."),
    ("clause", "9.7", "Integrity: the bidder shall not offer any gift, inducement or consideration to any officer of the "
                      "University in connection with this RFP. Any such act will lead to rejection of the proposal and "
                      "debarment."),

    ("h1", "ANNEXURE-1: CHECKLIST OF DOCUMENTS"),
    ("table", ["S. No.", "Document", "Page no. in bid"], [
        ["1", "Bid covering letter (Annexure-2)", ""], ["2", "RFP fee and EMD, or MSE exemption certificate", ""],
        ["3", "Certificate of incorporation, GST and PAN", ""], ["4", "Audited balance sheets for three years and CA certificate", ""],
        ["5", "Purchase orders and completion certificates", ""], ["6", "ISO 9001:2015 certificate", ""],
        ["7", "Manufacturer's Authorisation Forms (Annexure-3)", ""], ["8", "Declaration of non-blacklisting (Annexure-4)", ""],
        ["9", "Technical compliance statement (Annexure-5)", ""], ["10", "Proof of office or service centre in Pune", ""],
        ["11", "Letter of authority for the signatory", ""],
    ], [12, 128, 30]),
    ("h1", "ANNEXURE-2: BID COVERING LETTER"),
    ("p", "To, The Registrar, DES Pune University, Fergusson College Road, Shivajinagar, Pune 411004."),
    ("p", "Sir or Madam, having examined the RFP document, we the undersigned offer to supply, install and commission the "
          "equipment in conformity with the said document for the sum shown in the financial bid. We undertake, if our "
          "proposal is accepted, to complete the work within the period specified. We agree to abide by this proposal for "
          "the validity period and it shall remain binding upon us."),
    ("p", "Signature of authorised signatory, name, designation and seal of the bidder."),
    ("h1", "ANNEXURE-3: MANUFACTURER'S AUTHORISATION FORM"),
    ("p", "We, the manufacturer of the goods offered, hereby authorise the bidder to submit a proposal and to negotiate and "
          "sign the order for the goods manufactured by us against the above RFP. We extend our full warranty for the goods "
          "offered by the above firm."),
    ("h1", "ANNEXURE-4: DECLARATION REGARDING BLACKLISTING"),
    ("p", "We hereby declare that our firm has not been blacklisted or debarred by any Central or State Government "
          "department, university, PSU or local body as on the date of submission of this proposal."),
    ("h1", "ANNEXURE-5: TECHNICAL COMPLIANCE STATEMENT"),
    ("p", "The bidder shall state against each parameter of Section V whether the offered product complies (Yes or No), "
          "along with the make and model offered and the page number of the OEM datasheet as evidence."),
    ("table", ["S. No.", "Item", "Make and model offered", "Complies (Yes/No)", "Datasheet page"],
     [[str(i), f"Item {i} of the Bill of Quantities", "", "", ""] for i in range(1, 11)], [12, 60, 50, 24, 24]),
    ("h1", "ANNEXURE-6: FINANCIAL BID FORMAT"),
    ("table", ["S. No.", "Item", "Qty", "Unit rate (Rs.)", "GST (%)", "Total (Rs.)"],
     [[str(i), f"Item {i} of the Bill of Quantities", "50", "", "", ""] for i in range(1, 11)], [12, 70, 16, 26, 20, 26]),
    ("p", "Total amount in figures and words, inclusive of GST. Signature and seal of the bidder."),
    ("h1", "ANNEXURE-7: FORMAT OF PERFORMANCE BANK GUARANTEE"),
    ("p", "In consideration of DES Pune University having agreed to exempt the supplier from the demand of security "
          "deposit, we, the bank, undertake to pay the University an amount not exceeding 3% of the order value against "
          "any loss or damage caused to or suffered by the University by reason of any breach by the supplier of the "
          "terms and conditions of the order. This guarantee shall remain valid until sixty days after the end of the "
          "warranty period."),
]
