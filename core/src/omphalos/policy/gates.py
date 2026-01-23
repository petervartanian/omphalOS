import json, re
from pathlib import Path

# Conservative gate: blocks obvious secrets, credentials, and high-risk strings.
# Designed for offline use; does not phone home.

_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws_access_key_like"),
    (re.compile(r"-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----"), "private_key_block"),
    (re.compile(r"password\s*[:=]\s*[^\s]{6,}", re.I), "password_assignment"),
    (re.compile(r"token\s*[:=]\s*[^\s]{8,}", re.I), "token_assignment"),
]

def export_gate(packet_path: str | Path):
    p = Path(packet_path)
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"read_error: {e}"

    hits = []
    for rx, name in _PATTERNS:
        if rx.search(txt):
            hits.append(name)

    # Additional structural check: packet must parse and contain memo.
    try:
        obj = json.loads(txt)
        if not isinstance(obj, dict) or "memo" not in obj:
            hits.append("packet_structure_invalid")
    except Exception:
        hits.append("packet_json_invalid")

    if hits:
        return False, "blocked: " + ", ".join(sorted(set(hits)))
    return True, ""
