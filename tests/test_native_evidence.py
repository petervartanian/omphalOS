"""Independent binaries must agree on preserved and damaged synthetic evidence.

CI builds both binaries and supplies their paths through the named variables.
No binary is built or downloaded implicitly by this test.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_evidence import make_run

from omphalos.evidence import build_manifest, verify_run
from omphalos.util import canonical_json, sha256_bytes, write_json


class NativeEvidenceTests(unittest.TestCase):
    def test_independent_verifiers(self) -> None:
        project = Path(__file__).resolve().parents[1]
        configured = {
            "go": os.environ.get(
                "OMPHALOS_GO_VERIFIER", str(project / "native/omphalos-verify-go")
            ),
            "rust": os.environ.get(
                "OMPHALOS_RUST_VERIFIER",
                str(project / "native/rust/target/release/omphalos-integrity-verifier"),
            ),
        }
        available = {
            name: Path(path)
            for name, path in configured.items()
            if Path(path).is_file()
        }
        if not available:
            self.skipTest(
                "Build the Go/Rust verifiers or configure OMPHALOS_*_VERIFIER paths"
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "valid"
            make_run(original)
            # Exercise Unicode, HTML characters, and control-character encoding parity.
            analysis = json.loads((original / "analysis.json").read_text())
            analysis["findings"][0]["metrics"][
                "encoding_sample"
            ] = "Café λ 😀 <&>\n\t\b\u2028"
            write_json(original / "analysis.json", analysis)
            (original / "manifest.json").unlink()
            build_manifest(
                original,
                run_id="run_demo",
                case_id="case_demo",
                analysis_digest=sha256_bytes(canonical_json(analysis)),
            )
            variants = {"valid": original}
            for variant in (
                "changed",
                "missing",
                "extra",
                "empty",
                "omitted",
                "invalid_json",
                "duplicate_key",
                "missing_manifest",
                "wrong_analysis_digest",
                "floating_analysis",
                "large_integer_analysis",
            ):
                clone = root / variant
                shutil.copytree(original, clone)
                if variant == "changed":
                    (clone / "catalog.json").write_bytes(
                        b"x" * (clone / "catalog.json").stat().st_size
                    )
                elif variant == "missing":
                    (clone / "catalog.json").unlink()
                elif variant == "extra":
                    (clone / "extra.txt").write_text("Unlisted synthetic data")
                elif variant == "invalid_json":
                    (clone / "manifest.json").write_text("This is not JSON.")
                elif variant == "duplicate_key":
                    raw = (
                        (clone / "manifest.json")
                        .read_text()
                        .replace(
                            '"schema_version":"2.0"',
                            '"schema_version":"2.0","schema_version":"2.0"',
                        )
                    )
                    (clone / "manifest.json").write_text(raw)
                elif variant == "missing_manifest":
                    (clone / "manifest.json").unlink()
                elif variant in {"floating_analysis", "large_integer_analysis"}:
                    changed = json.loads((clone / "analysis.json").read_text())
                    changed["findings"][0]["metrics"]["quantity"] = (
                        0.25 if variant == "floating_analysis" else 2**63
                    )
                    content = canonical_json(changed)
                    (clone / "analysis.json").write_bytes(content)
                    manifest = json.loads((clone / "manifest.json").read_text())
                    manifest["analysis_digest"] = sha256_bytes(content)
                    row = next(
                        row
                        for row in manifest["files"]
                        if row["path"] == "analysis.json"
                    )
                    row["sha256"] = sha256_bytes(content)
                    row["size_bytes"] = len(content)
                    write_json(clone / "manifest.json", manifest)
                else:
                    manifest = json.loads((clone / "manifest.json").read_text())
                    if variant == "empty":
                        manifest["files"] = []
                    elif variant == "omitted":
                        manifest["files"] = [
                            row
                            for row in manifest["files"]
                            if row["path"] != "catalog.json"
                        ]
                    else:
                        manifest["analysis_digest"] = "0" * 64
                    write_json(clone / "manifest.json", manifest)
                variants[variant] = clone
                self.assertFalse(verify_run(clone)["ok"], f"Python accepted {variant}")
            for implementation, binary in available.items():
                for variant, run in variants.items():
                    with self.subTest(implementation=implementation, variant=variant):
                        result = subprocess.run(
                            [str(binary), str(run)],
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        if variant == "valid":
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertIn("authenticity not assessed", result.stdout)
                        else:
                            self.assertNotEqual(
                                result.returncode,
                                0,
                                f"{implementation} accepted {variant}",
                            )


if __name__ == "__main__":
    unittest.main()
