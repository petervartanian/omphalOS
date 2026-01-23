"""
Conformance suite for omphalOS v1.0.

This is the release constitution: a v1.0 repository is "final" only insofar as these
checks pass and the schemas remain frozen.
"""
import os
import subprocess
from pathlib import Path

from ..packs import pack_verify
from ..runner import run_case, verify_run
from ..policy.gates import export_gate


def _try(cmd, cwd=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
        return True, (p.stdout.strip() + ("\n" + p.stderr.strip() if p.stderr.strip() else "")).strip()
    except FileNotFoundError:
        return False, "missing_executable"
    except subprocess.CalledProcessError as e:
        out = (e.stdout or "") + ("\n" + (e.stderr or ""))
        return False, out.strip()


def main():
    repo_root = Path(__file__).resolve()
    for cand in [repo_root] + list(repo_root.parents):
        if (cand / "packs").is_dir() and (cand / "hydrate").is_dir():
            repo_root = cand
            break

    packs_index = repo_root / "packs" / "INDEX.json"
    if not packs_index.exists():
        raise SystemExit("packs/INDEX.json missing")

    ok = pack_verify(packs_index)
    if not ok:
        raise SystemExit("FAIL: pack_verify")

    case_path = repo_root / "hydrate" / "cases" / "case_chemicals.json"
    if not case_path.exists():
        raise SystemExit("FAIL: missing hydrate/cases/case_chemicals.json")

    out_root = repo_root / "hydrate" / "_conformance_runs"
    run_dir = Path(run_case(case_path, out_root=str(out_root)))

    if not verify_run(run_dir):
        raise SystemExit("FAIL: verify_run")

    packet_path = run_dir / "packet.json"
    ok, report = export_gate(packet_path)
    if not ok:
        raise SystemExit("FAIL: export_gate\n" + report)

    # Attempt independent verifiers if toolchains exist. These are best-effort;
    # v1.0 requires the Python path above to pass regardless.
    go_ver = repo_root / "core" / "agents" / "go" / "verifier"
    rust_ver = repo_root / "core" / "agents" / "rust" / "verifier"

    go_ok, go_out = _try(["go", "run", "." , str(run_dir)], cwd=str(go_ver))
    rust_ok, rust_out = _try(["cargo", "run", "--quiet", "--", str(run_dir)], cwd=str(rust_ver))

    print("OK: python")
    print("go:", "OK" if go_ok else "SKIP/FAIL")
    if go_out:
        print(go_out)
    print("rust:", "OK" if rust_ok else "SKIP/FAIL")
    if rust_out:
        print(rust_out)

    print(f"conformance_run_dir={run_dir}")


if __name__ == "__main__":
    main()
