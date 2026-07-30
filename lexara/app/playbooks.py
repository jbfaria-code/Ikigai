"""Built-in negotiation playbooks.

A playbook is a named set of positions a team takes into a negotiation. Each
rule pairs a title with the standard the reviewer measures the document against.
Teams can also post their own playbook at run time; these are the defaults that
ship so the feature is useful on first launch.
"""

PLAYBOOKS = {
    "mutual_nda": {
        "key": "mutual_nda",
        "name": "Mutual NDA — receiving party",
        "perspective": "receiving party",
        "description": "Standard positions for a two-way confidentiality agreement.",
        "rules": [
            {
                "title": "Definition of Confidential Information",
                "standard": "Limited to information marked confidential, or disclosed orally and confirmed in writing within 30 days. Blanket 'all information disclosed' definitions are a deviation.",
            },
            {
                "title": "Standard exclusions",
                "standard": "Must exclude information that is public through no fault of the recipient, already known, independently developed, or received from a third party without restriction.",
            },
            {
                "title": "Term of confidentiality",
                "standard": "Obligations run 3 years from disclosure. Perpetual obligations are a deviation except for trade secrets, where perpetual is acceptable.",
            },
            {
                "title": "Permitted disclosure to representatives",
                "standard": "Recipient may share with employees, affiliates, and professional advisers on a need-to-know basis, and is responsible for their breach.",
            },
            {
                "title": "Compelled disclosure",
                "standard": "Disclosure required by law or regulator is permitted, with notice to the discloser where legally allowed. Notice must not be a precondition to disclosure.",
            },
            {
                "title": "Residuals",
                "standard": "Prefer a residuals clause permitting use of unaided memory. Absence is a low-severity deviation.",
            },
            {
                "title": "No licence and no warranty",
                "standard": "Agreement grants no IP licence and disclaims warranties as to accuracy of disclosed information.",
            },
            {
                "title": "Return or destruction",
                "standard": "On request, return or destroy, with a carve-out for archival backups and copies retained for legal or regulatory compliance.",
            },
            {
                "title": "Remedies",
                "standard": "Injunctive relief is acceptable. Liquidated damages, indemnities, or fee-shifting are deviations.",
            },
            {
                "title": "Non-solicitation and exclusivity",
                "standard": "An NDA should contain no non-solicit, no non-compete, and no exclusivity. Any such clause is a high-severity deviation.",
            },
            {
                "title": "Governing law and forum",
                "standard": "England and Wales, Delaware, or New York, with courts of the same jurisdiction. Anything else escalates.",
            },
            {
                "title": "Assignment",
                "standard": "Assignable to an affiliate or successor in a merger or sale of substantially all assets without consent.",
            },
        ],
    },
    "saas_msa": {
        "key": "saas_msa",
        "name": "SaaS agreement — customer",
        "perspective": "customer",
        "description": "Buy-side positions for subscription software and services.",
        "rules": [
            {
                "title": "Service levels and remedy",
                "standard": "At least 99.9% monthly uptime with service credits, and a termination right for repeated or sustained failure. Credits as sole remedy without a termination right is a deviation.",
            },
            {
                "title": "Term, renewal and notice",
                "standard": "Initial term with auto-renewal only where the notice period to opt out is 30 days or less. Notice periods over 60 days are a deviation.",
            },
            {
                "title": "Price increases on renewal",
                "standard": "Capped at the lower of CPI or 5% per renewal term. Uncapped increases are a high-severity deviation.",
            },
            {
                "title": "Customer data ownership",
                "standard": "Customer owns all customer data. Vendor's rights limited to providing the service. Any right to use customer data for product improvement or model training requires opt-in.",
            },
            {
                "title": "Data protection and sub-processors",
                "standard": "A DPA is incorporated, sub-processors are listed with notice of changes, and international transfers rely on a valid mechanism.",
            },
            {
                "title": "Security standards and audit",
                "standard": "Vendor maintains SOC 2 Type II or ISO 27001 and provides the report annually. Customer has audit rights on a security incident.",
            },
            {
                "title": "Incident notification",
                "standard": "Written notice of a security incident affecting customer data without undue delay and in any event within 72 hours.",
            },
            {
                "title": "IP indemnity",
                "standard": "Vendor indemnifies for third-party IP claims, uncapped or capped well above the general cap, with defence and settlement control.",
            },
            {
                "title": "Limitation of liability",
                "standard": "General cap at the greater of 12 months' fees or a fixed floor, with super-caps for data breach and confidentiality. Caps at less than 12 months' fees are a deviation.",
            },
            {
                "title": "Excluded losses",
                "standard": "Mutual exclusion of indirect and consequential loss. A one-sided exclusion favouring the vendor is a deviation.",
            },
            {
                "title": "Suspension rights",
                "standard": "Suspension only for material breach or a genuine security risk, after notice and a cure period, except in an emergency.",
            },
            {
                "title": "Termination for convenience and exit",
                "standard": "Customer may terminate for convenience with notice, and gets data export in a machine-readable format plus a transition period of at least 30 days.",
            },
            {
                "title": "Unilateral change to terms or service",
                "standard": "No unilateral amendment of the agreement. Material degradation of functionality gives a termination right.",
            },
            {
                "title": "Assignment and change of control",
                "standard": "Neither party assigns without consent, except to an affiliate or successor. Customer keeps a termination right if the vendor is acquired by a competitor.",
            },
            {
                "title": "Governing law and dispute resolution",
                "standard": "Customer's home jurisdiction, courts rather than mandatory arbitration, no class-action waiver.",
            },
        ],
    },
    "employment": {
        "key": "employment",
        "name": "Employment agreement — employer",
        "perspective": "employer",
        "description": "Standard positions for senior hires.",
        "rules": [
            {"title": "Role, reporting and location", "standard": "Title, reporting line, and primary work location are stated, with a reasonable variation right."},
            {"title": "Compensation and review", "standard": "Base salary, bonus mechanics, and any equity are stated, with bonus discretionary and subject to being employed and not under notice on the payment date."},
            {"title": "Probationary period", "standard": "Probation of 3 to 6 months with a shortened notice period during probation."},
            {"title": "Notice period", "standard": "Between 1 and 6 months depending on seniority, mutual, with payment in lieu at the employer's option."},
            {"title": "Garden leave", "standard": "Express right to place on garden leave during notice, with continued pay and benefits."},
            {"title": "IP assignment", "standard": "Present assignment of all work-related IP with a waiver of moral rights and a further-assurance obligation."},
            {"title": "Confidentiality", "standard": "Survives termination indefinitely for trade secrets, with a standard whistleblowing carve-out."},
            {"title": "Post-termination restrictions", "standard": "Non-compete no longer than 6 months, non-solicit of clients and staff no longer than 12 months, each with a clear geographic and business scope, and set off against garden leave."},
            {"title": "Termination for cause", "standard": "Defined gross-misconduct grounds permitting summary termination without notice or payment in lieu."},
            {"title": "Return of property and data", "standard": "Obligation to return all company property and delete company data from personal devices on termination."},
            {"title": "Governing law and jurisdiction", "standard": "Governing law of the employee's place of work, with mandatory local employment protections acknowledged."},
        ],
    },
}


def list_playbooks() -> list[dict]:
    return [
        {
            "key": p["key"],
            "name": p["name"],
            "perspective": p["perspective"],
            "description": p["description"],
            "rule_count": len(p["rules"]),
        }
        for p in PLAYBOOKS.values()
    ]


def get(key: str) -> dict | None:
    return PLAYBOOKS.get(key)
