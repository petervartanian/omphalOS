import re
from dataclasses import dataclass
from typing import List, Tuple

# v1.0 admissibility thresholds. The shipped catalog exceeds these.
MIN_CANON_LINES = 60
MIN_MARGIN_LINES = 45

_RX_CANON = re.compile(r"^\s*--\s*Canon\b", re.M)
_RX_MARGIN = re.compile(r"^\s*--\s*Margin\b", re.M)
_RX_INV_ID = re.compile(r"^\s*--\s*Investigation\s*:\s*(\S+)", re.M)
_RX_DOMAIN = re.compile(r"^\s*--\s*Domain\s*:\s*(\S+)", re.M)
_RX_INTENT = re.compile(r"^\s*--\s*Intent\s*:\s*(.+)$", re.M)
_RX_LIMIT = re.compile(r"\bLIMIT\b\s+\d+", re.I)


@dataclass(frozen=True)
class AdmissibilityReport:
    ok: bool
    issues: List[str]
    investigation_id: str | None = None
    domain: str | None = None
    intent: str | None = None


def assess_sql_admissibility(sql_text: str) -> AdmissibilityReport:
    issues: List[str] = []

    inv = _RX_INV_ID.search(sql_text)
    dom = _RX_DOMAIN.search(sql_text)
    intent = _RX_INTENT.search(sql_text)

    if not inv:
        issues.append("missing_header_investigation")  # identity
    if not dom:
        issues.append("missing_header_domain")  # jurisdiction
    if not intent:
        issues.append("missing_header_intent")  # purpose

    canon_n = len(_RX_CANON.findall(sql_text))
    margin_n = len(_RX_MARGIN.findall(sql_text))
    if canon_n < MIN_CANON_LINES:
        issues.append(f"canon_lines_insufficient:{canon_n}")
    if margin_n < MIN_MARGIN_LINES:
        issues.append(f"margin_lines_insufficient:{margin_n}")

    if not _RX_LIMIT.search(sql_text):
        issues.append("missing_limit")

    return AdmissibilityReport(
        ok=(len(issues) == 0),
        issues=issues,
        investigation_id=(inv.group(1) if inv else None),
        domain=(dom.group(1) if dom else None),
        intent=(intent.group(1).strip() if intent else None),
    )
