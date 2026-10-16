"""Evidence contracts exercised with benign, synthetic data."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from omphalos import evidence
from omphalos.util import canonical_json, sha256_bytes, sha256_file, write_json


def make_run(root: Path, *, finding: bool = True) -> tuple[dict, dict]:
    root.mkdir(parents=True)
    case = {
        "schema_version": "2.0",
        "case_id": "case_demo",
        "question": "Explain the synthetic measurement change.",
        "dataset_id": "demo",
        "as_of": "2026-10-13",
        "investigations": ["data_quality"],
        "scope": {},
        "parameters": {},
        "watchlist_snapshot_id": None,
    }
    finding_data = {
        "finding_id": "F1",
        "investigation_id": "data_quality",
        "title": "A <b>literal</b> label",
        "observation": "One synthetic entity has a missing address.",
        "entity_ids": ["E1"],
        "record_refs": [{"table": "entities", "record_id": "E1"}],
        "metrics": {"count": 1},
        "unknowns": ["The omitted address has not been confirmed."],
        "alternatives": ["The import may have omitted an optional field."],
        "falsifiers": ["An original record could show the address."],
        "source_refs": [],
    }
    analysis = {
        "findings": [finding_data] if finding else [],
        "coverage": [
            {
                "investigation_id": "data_quality",
                "status": "executed",
                "records_evaluated": 1,
                "findings_count": 1 if finding else 0,
                "reason": "",
                "limitations": ["Synthetic test data only."],
            }
        ],
        "scope_counts": {"entities": 1},
        "warnings": [],
    }
    write_json(root / "case.json", case)
    write_json(root / "analysis.json", analysis)
    write_json(
        root / "data/dataset.json",
        {
            "tables": {"entities": [{"entity_id": "E1", "name": "Synthetic Example"}]},
            "metadata": {"synthetic": True},
        },
    )
    write_json(root / "catalog.json", [{"id": "data_quality"}])
    write_json(root / "environment.json", {"python": "3.13", "test": True})
    (root / "engine").mkdir()
    (root / "engine/analysis.py").write_text("def identity(value):\n    return value\n")
    manifest = evidence.build_manifest(
        root,
        run_id="run_demo",
        case_id="case_demo",
        analysis_digest=sha256_bytes(canonical_json(analysis)),
    )
    review = {
        "schema_version": "2.0",
        "run_id": "run_demo",
        "reviewer": "Synthetic Reviewer",
        "summary": "I examined the imported synthetic evidence and recorded its limitations.",
        "acknowledge_limitations": True,
        "findings": (
            [
                {
                    "finding_id": "F1",
                    "disposition": "follow_up",
                    "rationale": "Request the original form to distinguish missing data from a parsing omission.",
                    "unknowns": [
                        "The original form was unavailable during this review."
                    ],
                    "alternatives": [
                        "The address may have been left blank by the submitter."
                    ],
                    "falsifiers": [
                        "Compare the original form with the preserved import mapping."
                    ],
                }
            ]
            if finding
            else []
        ),
    }
    return manifest, review


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.manifest, self.review = make_run(self.run)
        self.review_path = self.root / "review.json"
        self.write_review()

    def write_review(self) -> None:
        write_json(
            self.review_path,
            {
                "review_id": "review_demo",
                "created_at": "2026-10-13T12:00:00Z",
                "run_manifest_sha256": sha256_file(self.run / "manifest.json"),
                "review": self.review,
            },
        )

    def bundle(self) -> Path:
        path = self.root / "evidence.zip"
        evidence.export_bundle(self.run, self.review_path, path)
        return path

    def rewrite_bundle(self, path: Path, operation) -> None:
        with zipfile.ZipFile(path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        operation(members)
        with zipfile.ZipFile(path, "w") as archive:
            for name, value in members.items():
                archive.writestr(name, value)

    def test_valid_inventory_review_and_roundtrip(self) -> None:
        self.assertTrue(evidence.verify_run(self.run)["ok"])
        self.assertTrue(evidence.validate_review(self.run, self.review)["ok"])
        bundle = self.bundle()
        result = evidence.verify_bundle(bundle)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["authenticity"], "not_assessed")
        with zipfile.ZipFile(bundle) as archive:
            report = archive.read("report.html").decode()
            self.assertIn("&lt;b&gt;literal&lt;/b&gt;", report)
            self.assertNotIn("A <b>literal</b>", report)
            self.assertIn("self-asserted identity", report)

    def test_finalization_and_export_never_overwrite(self) -> None:
        before = (self.run / "manifest.json").read_bytes()
        with self.assertRaises(ValueError):
            evidence.build_manifest(
                self.run,
                run_id="another",
                case_id="case_demo",
                analysis_digest=self.manifest["analysis_digest"],
            )
        self.assertEqual(before, (self.run / "manifest.json").read_bytes())
        path = self.bundle()
        digest = sha256_file(path)
        with self.assertRaises(FileExistsError):
            evidence.export_bundle(self.run, self.review_path, path)
        self.assertEqual(digest, sha256_file(path))

    def test_modified_missing_extra_and_empty_inventory(self) -> None:
        for variant in ("changed", "missing", "extra", "empty", "omitted"):
            with self.subTest(variant=variant):
                clone = self.root / variant
                shutil.copytree(self.run, clone)
                if variant == "changed":
                    (clone / "catalog.json").write_text("[]")
                elif variant == "missing":
                    (clone / "catalog.json").unlink()
                elif variant == "extra":
                    (clone / "unlisted.txt").write_text("extra synthetic bytes")
                else:
                    manifest = json.loads((clone / "manifest.json").read_text())
                    manifest["files"] = (
                        []
                        if variant == "empty"
                        else [
                            row
                            for row in manifest["files"]
                            if row["path"] != "catalog.json"
                        ]
                    )
                    write_json(clone / "manifest.json", manifest)
                self.assertFalse(evidence.verify_run(clone)["ok"])

    def test_duplicate_manifest_keys_rejected(self) -> None:
        content = (self.run / "manifest.json").read_text()
        (self.run / "manifest.json").write_text(
            content.replace(
                '"schema_version":"2.0"',
                '"schema_version":"2.0","schema_version":"2.0"',
            )
        )
        self.assertFalse(evidence.verify_run(self.run)["ok"])

    def test_analysis_digest_recomputed(self) -> None:
        manifest = self.manifest.copy()
        manifest["analysis_digest"] = "0" * 64
        write_json(self.run / "manifest.json", manifest)
        result = evidence.verify_run(self.run)
        self.assertFalse(result["ok"])
        self.assertIn("analysis_digest", " ".join(result["issues"]))

    def test_decimal_numbers_must_be_strings(self) -> None:
        analysis = json.loads((self.run / "analysis.json").read_text())
        analysis["findings"][0]["metrics"]["amount"] = 12.50
        write_json(self.run / "analysis.json", analysis)
        (self.run / "manifest.json").unlink()
        with self.assertRaisesRegex(ValueError, "decimals must be strings"):
            evidence.build_manifest(
                self.run,
                run_id="run_demo",
                case_id="case_demo",
                analysis_digest=sha256_bytes(canonical_json(analysis)),
            )

    def test_review_coverage_acknowledgment_and_evidence(self) -> None:
        for field, value in (
            ("findings", []),
            ("acknowledge_limitations", False),
            ("reviewer", ""),
            ("run_id", "wrong_run"),
        ):
            with self.subTest(field=field):
                review = {**self.review, field: value}
                self.assertFalse(evidence.validate_review(self.run, review)["ok"])
        analysis = json.loads((self.run / "analysis.json").read_text())
        analysis["findings"][0]["record_refs"][0]["record_id"] = "ABSENT"
        write_json(self.run / "analysis.json", analysis)
        (self.run / "manifest.json").unlink()
        evidence.build_manifest(
            self.run,
            run_id="run_demo",
            case_id="case_demo",
            analysis_digest=sha256_bytes(canonical_json(analysis)),
        )
        self.assertFalse(evidence.validate_review(self.run, self.review)["ok"])

    def test_unchanged_scaffolding_not_completed_review(self) -> None:
        original = json.loads((self.run / "analysis.json").read_text())["findings"][0]
        for name in ("unknowns", "alternatives", "falsifiers"):
            self.review["findings"][0][name] = original[name]
        self.assertFalse(evidence.validate_review(self.run, self.review)["ok"])

    def test_zero_findings_still_requires_explicit_review(self) -> None:
        empty = self.root / "zero"
        _, review = make_run(empty, finding=False)
        self.assertTrue(evidence.validate_review(empty, review)["ok"])
        review["summary"] = ""
        self.assertFalse(evidence.validate_review(empty, review)["ok"])

    def test_review_manifest_anchor_enforced(self) -> None:
        wrapper = json.loads(self.review_path.read_text())
        wrapper["run_manifest_sha256"] = "0" * 64
        write_json(self.review_path, wrapper)
        with self.assertRaisesRegex(ValueError, "exact run manifest"):
            self.bundle()

    def test_credential_patterns_block_export(self) -> None:
        self.review["summary"] = (
            "The synthetic review contains password=fake_test_only for a scanner check."
        )
        self.write_review()
        with self.assertRaisesRegex(ValueError, "credential scan failed"):
            self.bundle()

    def test_bundle_changed_missing_extra_and_empty_inventory(self) -> None:
        original = self.bundle()
        for variant in ("changed", "missing", "extra", "empty"):
            with self.subTest(variant=variant):
                path = self.root / f"{variant}.zip"
                shutil.copyfile(original, path)

                def change(members):
                    if variant == "changed":
                        members["report.md"] = b"Changed synthetic report"
                    elif variant == "missing":
                        del members["run/catalog.json"]
                    elif variant == "extra":
                        members["unexpected.txt"] = b"Extra synthetic file"
                    else:
                        manifest = json.loads(members[evidence.BUNDLE_MANIFEST])
                        manifest["files"] = []
                        members[evidence.BUNDLE_MANIFEST] = canonical_json(manifest)

                self.rewrite_bundle(path, change)
                self.assertFalse(evidence.verify_bundle(path)["ok"])

    def test_bundle_duplicate_and_limits(self) -> None:
        path = self.bundle()
        with patch.object(evidence, "MAX_FILE_BYTES", 10):
            self.assertFalse(evidence.verify_bundle(path)["ok"])
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("report.html", b"duplicate synthetic member")
        self.assertFalse(evidence.verify_bundle(path)["ok"])

    def test_symlink_inventory_rejected(self) -> None:
        link = self.run / "alias.txt"
        try:
            link.symlink_to(self.run / "catalog.json")
        except OSError:
            self.skipTest("Host cannot create symbolic links")
        self.assertFalse(evidence.verify_run(self.run)["ok"])

    def test_external_ed25519_signature(self) -> None:
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )
        except ImportError:
            self.skipTest("Optional cryptography dependency unavailable")
        key = Ed25519PrivateKey.generate()
        public = self.root / "trusted.pem"
        public.write_bytes(
            key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        artifact = self.run / "manifest.json"
        signature = self.root / "manifest.sig"
        signature.write_bytes(key.sign(artifact.read_bytes()))
        self.assertTrue(
            evidence.verify_ed25519_signature(artifact, signature, public)["ok"]
        )
        signature.write_bytes(b"0" * 64)
        self.assertFalse(
            evidence.verify_ed25519_signature(artifact, signature, public)["ok"]
        )
        from cryptography.exceptions import UnsupportedAlgorithm

        with patch(
            "cryptography.hazmat.primitives.serialization.load_pem_public_key",
            side_effect=UnsupportedAlgorithm("Synthetic unsupported algorithm"),
        ):
            self.assertFalse(
                evidence.verify_ed25519_signature(artifact, signature, public)["ok"]
            )


if __name__ == "__main__":
    unittest.main()
