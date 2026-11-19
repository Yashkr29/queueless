"""Starter configurations per organization type. They are conveniences, not data: every value is editable afterwards.
Average durations are typical *priors* used until real service times accumulate (the engine blends them with measured times)."""

TEMPLATES: dict[str, dict] = {
    "hospital": {
        "label": "Hospital / clinic",
        "hours": ("08:00", "20:00"),
        "counters": 4,
        "services": [
            ("Registration & Billing", "R", "New patient registration, billing and insurance desk", 6),
            ("General OPD", "O", "Outpatient consultation queue", 12),
            ("Diagnostics & Lab", "L", "Sample collection, scans and reports", 9),
            ("Pharmacy", "P", "Prescription dispensing", 5),
        ],
    },
    "college": {
        "label": "College / university",
        "hours": ("09:30", "16:30"),
        "counters": 4,
        "services": [
            ("Admissions", "A", "Admission enquiries and document submission", 15),
            ("Fees & Accounts", "F", "Fee payment, receipts and refunds", 6),
            ("Examination Cell", "E", "Hall tickets, results and revaluation", 8),
            ("Student Records", "S", "Certificates, transcripts and ID cards", 7),
        ],
    },
    "bank": {
        "label": "Bank branch",
        "hours": ("10:00", "16:00"),
        "counters": 4,
        "services": [
            ("Cash Services", "C", "Deposits and withdrawals", 5),
            ("Account Services", "A", "Account opening, KYC and updates", 12),
            ("Loans & Advisory", "L", "Loan enquiries and advisory", 20),
            ("Customer Support", "S", "Cards, cheques and general support", 8),
        ],
    },
    "government": {
        "label": "Government service centre",
        "hours": ("10:00", "17:00"),
        "counters": 4,
        "services": [
            ("Application Submission", "A", "New applications and forms", 10),
            ("Document Verification", "D", "Certificate and ID verification", 11),
            ("Payments", "P", "Fees, fines and taxes", 5),
            ("Grievances", "G", "Complaints and follow-ups", 14),
        ],
    },
    "other": {
        "label": "Other service centre",
        "hours": ("09:00", "17:00"),
        "counters": 2,
        "services": [
            ("General Enquiry", "G", "Questions and general help", 6),
            ("Service Desk", "S", "Main service desk", 10),
        ],
    },
}
