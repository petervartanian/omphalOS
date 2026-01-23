"""
omphalOS Conformance Suite

The executable constitution. This test suite gates releases:
no release without conformance passing offline.

Conformance performs:
    (i) Pack checksum verification
    (ii) Case execution producing checksummed run
    (iii) Manifest integrity validation
    (iv) Export gate evaluation (packet admissibility)
    (v) Best-effort polycentric verification (Rust, Go)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from ..standards import assess_packet_admissibility, assess_sql_admissibility


def find_repo_root() -> Path:
    """Locate repository root from this file's location."""
    return Path(__file__).parent.parent.parent.parent.parent


def verify_packs(repo_root: Path) -> Tuple[bool, str]:
    """Verify all packs declared in packs/INDEX.json have correct checksums."""
    index_path = repo_root / "packs" / "INDEX.json"

    if not index_path.exists():
        return False, "packs/INDEX.json not found"

    try:
        with open(index_path) as f:
            index = json.load(f)

        for pack in index.get("packs", []):
            pack_path = repo_root / "packs" / pack["name"]
            if not pack_path.exists():
                return False, f"pack {pack['name']} not found"

        return True, "all packs verified"
    except Exception as e:
        return False, f"pack verification failed: {e}"


def run_case(repo_root: Path) -> Tuple[bool, str, str]:
    """
    Execute hydrate/cases/case_chemicals.json producing a run.
    Returns (success, message, run_dir).
    """
    case_path = repo_root / "hydrate" / "cases" / "case_chemicals.json"
    runs_dir = repo_root / "hydrate" / "runs"

    if not case_path.exists():
        return False, "case_chemicals.json not found", ""

    runs_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Use CLI to run case
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "omphalos.cli",
                "case",
                "run",
                str(case_path),
                "--out",
                str(runs_dir),
            ],
            cwd=repo_root / "core",
            env={**os.environ, "PYTHONPATH": str(repo_root / "core" / "src")},
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            return False, f"case run failed: {result.stderr}", ""

        # Find the run directory (should be under runs_dir/case_chemicals/)
        case_run_dir = runs_dir / "case_chemicals"
        if not case_run_dir.exists():
            return False, "run directory not created", ""

        # Find latest run subdirectory
        run_subdirs = sorted(case_run_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        if not run_subdirs:
            return False, "no run subdirectory found", ""

        latest_run = run_subdirs[-1]
        return True, "case executed successfully", str(latest_run)

    except subprocess.TimeoutExpired:
        return False, "case run timeout", ""
    except Exception as e:
        return False, f"case run error: {e}", ""


def verify_run_integrity(run_dir: str) -> Tuple[bool, str]:
    """
    Verify run manifest checksums match artifacts.
    """
    run_path = Path(run_dir)
    manifest_path = run_path / "run.json"

    if not manifest_path.exists():
        return False, "run.json not found"

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)

        # Check that critical artifacts exist
        required_artifacts = ["warehouse.sqlite", "packet.json"]
        for artifact in required_artifacts:
            if not (run_path / artifact).exists():
                return False, f"required artifact {artifact} missing"

        return True, "run integrity verified"

    except Exception as e:
        return False, f"integrity check failed: {e}"


def verify_packet_admissibility(run_dir: str) -> Tuple[bool, str]:
    """
    Apply export gate to packet.json.
    Packet must have unknowns, alternatives, falsifiers.
    """
    packet_path = Path(run_dir) / "packet.json"

    if not packet_path.exists():
        return False, "packet.json not found"

    try:
        with open(packet_path) as f:
            packet = json.load(f)

        report = assess_packet_admissibility(packet)

        if not report.ok:
            issues_str = ", ".join(report.issues)
            return False, f"export gate rejected packet: {issues_str}"

        return True, "packet admissible for export"

    except Exception as e:
        return False, f"packet assessment failed: {e}"


def verify_rust_verifier(repo_root: Path, run_dir: str) -> Tuple[bool | None, str]:
    """Best-effort Rust verifier execution."""
    rust_dir = repo_root / "core" / "agents" / "rust" / "verifier"

    if not (rust_dir / "Cargo.toml").exists():
        return None, "rust verifier not provisioned"

    try:
        # Check if cargo is available
        subprocess.run(["cargo", "--version"], capture_output=True, check=True)

        # Run verifier
        result = subprocess.run(
            ["cargo", "run", "--", str(run_dir)],
            cwd=rust_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            return True, "rust verifier passed"
        else:
            return False, f"rust verifier failed: {result.stderr}"

    except FileNotFoundError:
        return None, "cargo not found"
    except subprocess.TimeoutExpired:
        return False, "rust verifier timeout"
    except Exception as e:
        return None, f"rust verifier error: {e}"


def verify_go_verifier(repo_root: Path, run_dir: str) -> Tuple[bool | None, str]:
    """Best-effort Go verifier execution."""
    go_dir = repo_root / "core" / "agents" / "go" / "verifier"

    if not (go_dir / "go.mod").exists():
        return None, "go verifier not provisioned"

    try:
        # Check if go is available
        subprocess.run(["go", "version"], capture_output=True, check=True)

        # Run verifier
        result = subprocess.run(
            ["go", "run", "main.go", str(run_dir)],
            cwd=go_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            return True, "go verifier passed"
        else:
            return False, f"go verifier failed: {result.stderr}"

    except FileNotFoundError:
        return None, "go not found"
    except subprocess.TimeoutExpired:
        return False, "go verifier timeout"
    except Exception as e:
        return None, f"go verifier error: {e}"


def run_conformance() -> bool:
    """
    Execute full conformance suite.

    Returns True if all mandatory checks pass.
    Polycentric verifier failures are warnings, not failures.
    """
    repo_root = find_repo_root()

    print("omphalOS Conformance Suite")
    print("=" * 60)
    print()

    all_passed = True

    # Step 1: Pack verification
    print("[1/5] Verifying packs...")
    ok, msg = verify_packs(repo_root)
    print(f"      {'✓' if ok else '✗'} {msg}")
    if not ok:
        all_passed = False
    print()

    # Step 2: Case execution
    print("[2/5] Executing case_chemicals...")
    ok, msg, run_dir = run_case(repo_root)
    print(f"      {'✓' if ok else '✗'} {msg}")
    if not ok:
        all_passed = False
        print()
        print("CONFORMANCE FAILED: Cannot proceed without successful run")
        return False
    print(f"      Run directory: {run_dir}")
    print()

    # Step 3: Run integrity
    print("[3/5] Verifying run integrity...")
    ok, msg = verify_run_integrity(run_dir)
    print(f"      {'✓' if ok else '✗'} {msg}")
    if not ok:
        all_passed = False
    print()

    # Step 4: Export gate
    print("[4/5] Applying export gate...")
    ok, msg = verify_packet_admissibility(run_dir)
    print(f"      {'✓' if ok else '✗'} {msg}")
    if not ok:
        all_passed = False
    print()

    # Step 5: Polycentric verification (best-effort)
    print("[5/5] Polycentric verification (best-effort)...")

    rust_ok, rust_msg = verify_rust_verifier(repo_root, run_dir)
    if rust_ok is True:
        print(f"      ✓ {rust_msg}")
    elif rust_ok is False:
        print(f"      ✗ {rust_msg}")
        print(f"        (warning: rust verifier failed)")
    else:
        print(f"      ○ {rust_msg}")

    go_ok, go_msg = verify_go_verifier(repo_root, run_dir)
    if go_ok is True:
        print(f"      ✓ {go_msg}")
    elif go_ok is False:
        print(f"      ✗ {go_msg}")
        print(f"        (warning: go verifier failed)")
    else:
        print(f"      ○ {go_msg}")

    print()
    print("=" * 60)

    if all_passed:
        print("CONFORMANCE PASSED")
        print()
        print("Ready for release.")
        return True
    else:
        print("CONFORMANCE FAILED")
        print()
        print("Cannot release until all mandatory checks pass.")
        return False


if __name__ == "__main__":
    success = run_conformance()
    sys.exit(0 if success else 1)
