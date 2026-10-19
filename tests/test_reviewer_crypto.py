"""Independent cryptographic and trust-boundary checks of the shipped browser code."""

import subprocess
from pathlib import Path


def test_browser_reviewer_receipts_with_real_webcrypto():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        ["node", str(root / "tools/check_reviewer.mjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"ok":true' in result.stdout
