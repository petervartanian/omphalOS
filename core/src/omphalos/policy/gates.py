import json
import re
from pathlib import Path

# v1.0 export gate: blocks secrets and refuses epistemically unserious packets.
# Designed for offline use; it does not phone home.

_SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws_access_key_like"),
    (re.compile(r"-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----"), "private_key_block"),
    (re.compile(r"password\s*[:=]\s*[^\s]{6,}", re.I), "password_assignment"),
    (re.compile(r"token\s*[:=]\s*[^\s]{8,}", re.I), "token_assignment"),
]

# Lexical gate: disallow conclusory certainty unless separately litigated.
_OVERCONFIDENT = [
    re.compile(r"\bproves?\b", re.I),
    re.compile(r"\bmust\s+be\b", re.I),
    re.compile(r"\bconclusively\b", re.I),
    re.compile(r"\bbeyond\s+reasonable\s+doubt\b", re.I),
]

_REQUIRED_PACKET_FIELDS = [
    "schema_version",
    "case_id",
    "run_id",
    "created_utc",
    "question",
    "scope",
    "memo",
    "claims",
]


def _scan_text(txt: str):
    hits = []
    for rx, name in _SECRET_PATTERNS:
        if rx.search(txt):
            hits.append(name)
    for rx in _OVERCONFIDENT:
        if rx.search(txt):
            hits.append("overconfident_language")
            break
    return hits


def export_gate(packet_path: str | Path):
    p = Path(packet_path)
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"read_error: {e}"

    hits = _scan_text(txt)

    # Structural check: packet must parse.
    try:
        obj = json.loads(txt)
    except Exception:
        hits.append("packet_json_invalid")
        return False, "blocked: " + ", ".join(sorted(set(hits)))

    if not isinstance(obj, dict):
        hits.append("packet_structure_invalid")
        return False, "blocked: " + ", ".join(sorted(set(hits)))

    for f in _REQUIRED_PACKET_FIELDS:
        if f not in obj:
            hits.append(f"missing_field:{f}")

    if obj.get("schema_version") != "1.0":
        hits.append("unsupported_schema_version")

    # Mandatory doubts: each claim must carry evidence, unknowns, alternatives, falsifiers.
    claims = obj.get("claims")
    if not isinstance(claims, list) or len(claims) == 0:
        hits.append("claims_empty_or_invalid")
    else:
        for i, c in enumerate(claims):
            if not isinstance(c, dict):
                hits.append(f"claim_invalid:{i}")
                continue
            for k in ("evidence", "unknowns", "alternatives", "falsifiers"):
                v = c.get(k)
                if not isinstance(v, list) or len(v) == 0:
                    hits.append(f"claim_missing_or_empty:{i}:{k}")

    # Memo must be substantive.
    memo = obj.get("memo", "")
    if not isinstance(memo, str) or len(memo.strip()) < 20:
        hits.append("memo_insufficient")

    if hits:
        return False, "blocked: " + ", ".join(sorted(set(hits)))
    return True, ""
