"""
omphalOS Standards Module

Programmatic enforcement of epistemic requirements.
The export gate uses these functions to ensure analytical products
meet minimum standards for interpretive restraint.
"""

import re
from dataclasses import dataclass
from typing import List

# Admissibility thresholds
MIN_CANON_LINES = 60
MIN_MARGIN_LINES = 45

# Regex patterns for SQL investigation validation
_RX_CANON = re.compile(r"^\s*--\s*Canon\b", re.M)
_RX_MARGIN = re.compile(r"^\s*--\s*Margin\b", re.M)
_RX_INV_ID = re.compile(r"^\s*--\s*Investigation\s*:\s*(\S+)", re.M)
_RX_DOMAIN = re.compile(r"^\s*--\s*Domain\s*:\s*(\S+)", re.M)
_RX_INTENT = re.compile(r"^\s*--\s*Intent\s*:\s*(.+)$", re.M)
_RX_LIMIT = re.compile(r"\bLIMIT\b\s+\d+", re.I)

# Prohibited certainty language in packets
PROHIBITED_CERTAINTY_TERMS = [
    "proves",
    "must be",
    "conclusively",
    "certainly",
    "definitively",
    "undoubtedly",
    "irrefutably",
]


@dataclass(frozen=True)
class AdmissibilityReport:
    """Result of admissibility assessment for SQL investigation or packet."""
    ok: bool
    issues: List[str]
    investigation_id: str | None = None
    domain: str | None = None
    intent: str | None = None


def assess_sql_admissibility(sql_text: str) -> AdmissibilityReport:
    """
    Assess whether SQL investigation meets standards.

    Requirements:
        (i) Header identifying Investigation, Domain, Intent
        (ii) Minimum 60 Canon lines (epistemic restraint)
        (iii) Minimum 45 Margin lines (uncertainty acknowledgment)
        (iv) Terminal LIMIT clause (bounded result sets)

    Returns AdmissibilityReport with ok=True if all requirements met.
    """
    issues: List[str] = []

    # Check headers
    inv = _RX_INV_ID.search(sql_text)
    dom = _RX_DOMAIN.search(sql_text)
    intent = _RX_INTENT.search(sql_text)

    if not inv:
        issues.append("missing_header_investigation")
    if not dom:
        issues.append("missing_header_domain")
    if not intent:
        issues.append("missing_header_intent")

    # Check canon/margin thresholds
    canon_n = len(_RX_CANON.findall(sql_text))
    margin_n = len(_RX_MARGIN.findall(sql_text))

    if canon_n < MIN_CANON_LINES:
        issues.append(f"canon_lines_insufficient:{canon_n}<{MIN_CANON_LINES}")
    if margin_n < MIN_MARGIN_LINES:
        issues.append(f"margin_lines_insufficient:{margin_n}<{MIN_MARGIN_LINES}")

    # Check for terminal LIMIT
    if not _RX_LIMIT.search(sql_text):
        issues.append("missing_limit")

    return AdmissibilityReport(
        ok=(len(issues) == 0),
        issues=issues,
        investigation_id=(inv.group(1) if inv else None),
        domain=(dom.group(1) if dom else None),
        intent=(intent.group(1).strip() if intent else None),
    )


def assess_packet_admissibility(packet: dict) -> AdmissibilityReport:
    """
    Assess whether packet meets export gate requirements.

    Requirements per STANDARDS_OF_REVIEW.md:
        (i) Evidence: explicit artifact pointers with hashes
        (ii) Unknowns: what claims do not establish
        (iii) Alternatives: rival explanations
        (iv) Falsifiers: what would overturn claims
        (v) No prohibited certainty language

    Returns AdmissibilityReport with ok=True if exportable.
    """
    issues: List[str] = []

    # Check mandatory epistemic scaffolding
    if "observations" not in packet or not packet["observations"]:
        issues.append("missing_observations")

    if "unknowns" not in packet or not packet["unknowns"]:
        issues.append("missing_unknowns")

    if "alternatives" not in packet or not packet["alternatives"]:
        issues.append("missing_alternatives")

    if "falsifiers" not in packet or not packet["falsifiers"]:
        issues.append("missing_falsifiers")

    # Check for prohibited certainty language in observations
    if "observations" in packet:
        obs_text = str(packet["observations"]).lower()
        for term in PROHIBITED_CERTAINTY_TERMS:
            if term in obs_text:
                issues.append(f"prohibited_certainty_language:{term}")

    # Check for evidence pointers with hashes
    if "annexes" in packet and packet["annexes"]:
        for annex in packet["annexes"]:
            if "sha256" not in annex:
                issues.append(f"missing_hash_in_annex:{annex.get('path', 'unknown')}")

    return AdmissibilityReport(
        ok=(len(issues) == 0),
        issues=issues,
    )


def verify_conformance(case_path: str, run_dir: str) -> dict:
    """
    Execute full conformance check.

    Returns dict with:
        - pack_verification: bool
        - run_integrity: bool
        - packet_admissibility: bool
        - verifier_rust: bool | None
        - verifier_go: bool | None
    """
    # Placeholder for full conformance implementation
    # This will be implemented in conformance.py
    return {
        "pack_verification": False,
        "run_integrity": False,
        "packet_admissibility": False,
        "verifier_rust": None,
        "verifier_go": None,
    }
