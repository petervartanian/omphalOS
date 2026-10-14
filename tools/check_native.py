"""Build both verifier implementations and require their shared conformance tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
suffix = ".exe" if os.name == "nt" else ""
go_binary = root / "native" / ("omphalos-verify-go" + suffix)
rust_binary = (
    root
    / "native"
    / "rust"
    / "target"
    / "release"
    / ("omphalos-integrity-verifier" + suffix)
)
subprocess.run(["go", "test", "./..."], cwd=root / "native" / "go", check=True)
subprocess.run(
    ["go", "build", "-o", str(go_binary), "."], cwd=root / "native" / "go", check=True
)
subprocess.run(["cargo", "test", "--locked"], cwd=root / "native" / "rust", check=True)
subprocess.run(
    ["cargo", "build", "--release", "--locked"],
    cwd=root / "native" / "rust",
    check=True,
)
environment = {
    **os.environ,
    "OMPHALOS_GO_VERIFIER": str(go_binary),
    "OMPHALOS_RUST_VERIFIER": str(rust_binary),
}
subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "tests/test_native_evidence.py"],
    cwd=root,
    env=environment,
    check=True,
)
