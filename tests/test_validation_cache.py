"""Validation reuse is bound to actual bytes, never filenames or timestamps."""

from __future__ import annotations

import os
import random
import re
from pathlib import Path

import pytest
from test_evidence import make_run
from test_sources_screening import csl_payload

from omphalos import evidence, sources
from omphalos.util import canonical_json, read_json, sha256_file, write_json


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('"password": "12345678"', True),
        ("notpassword=12345678", False),
        ("_token=12345678", False),
        ("-token=12345678", True),
        ("épassword=12345678", False),
        ("密码token=12345678", False),
        ("naccess-token=12345678", True),
        ("naccess_token=12345678", False),
        ("apiKey=12345678", True),
        ("apİkey=12345678", True),
        ("apıkey=12345678", True),
        ("ſecret-key=12345678", True),
        ("token\n:\n'12345678'", True),
        ("token=1234567", False),
        ("token=1234;5678", False),
        ("naccess-token=short password=12345678", True),
        ("tokenization and access token count: 12345678", False),
    ],
)
def test_credential_candidates_keep_original_boundaries_and_overlaps(
    text: str, expected: bool
) -> None:
    assert bool(evidence._CREDENTIAL_ASSIGNMENT.search(text)) is expected
    assert evidence._credential_assignment_present(text) is expected


def test_credential_candidate_search_matches_original_rule() -> None:
    randomizer = random.Random(281_733)
    fragments = (
        "password",
        "TOKEN",
        "api-key",
        "apıkey",
        "apİKey",
        "access-token",
        "access_token",
        "ſecret-key",
        "secretKEY",
        "n",
        "é",
        "密码",
        "_",
        "-",
        "=",
        ":",
        "\n",
        "\t",
        "'",
        '"',
        ",",
        ";",
        "{",
        "}",
        "1234567",
        "12345678",
        "record summary",
    )
    for _ in range(5_000):
        text = "".join(randomizer.choices(fragments, k=randomizer.randrange(1, 25)))
        assert evidence._credential_assignment_present(text) is bool(
            evidence._CREDENTIAL_ASSIGNMENT.search(text)
        ), repr(text)


def test_source_cache_rehashes_bytes_and_returns_independent_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "input.json"
    write_json(raw, csl_payload())
    destination = tmp_path / "source"
    sources.import_source("csl", raw, destination)
    sources._VALIDATED_SOURCES.clear()
    parse = sources._parse_csl
    calls = []

    def counted(value: bytes) -> tuple:
        calls.append(value)
        return parse(value)

    monkeypatch.setattr(sources, "_parse_csl", counted)
    first = sources.load_source(destination)
    first["entries"][0]["name"] = "Caller mutation must not enter cache"
    assert (
        sources.load_source(destination)["entries"][0]["name"]
        != first["entries"][0]["name"]
    )
    assert len(calls) == 1
    retained = destination / "raw.json"
    before = retained.stat()
    retained.write_bytes(retained.read_bytes().replace(b"Harbor", b"HARBOR"))
    os.utime(retained, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ValueError, match="checksum"):
        sources.load_source(destination)
    manifest_path = destination / "source-manifest.json"
    manifest = read_json(manifest_path)
    manifest["sha256"] = sha256_file(retained)
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError):
        sources.load_source(destination)


def test_source_cache_does_not_hide_rehashed_normalized_tampering(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "input.json"
    write_json(raw, csl_payload())
    destination = tmp_path / "source"
    sources.import_source("csl", raw, destination)
    sources.load_source(destination)
    normalized = destination / "source.json"
    changed = read_json(normalized)
    changed["entries"][0]["name"] = "Invented source identity"
    write_json(normalized, changed)
    manifest_path = destination / "source-manifest.json"
    manifest = read_json(manifest_path)
    manifest["normalized_sha256"] = sha256_file(normalized)
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="differ from original"):
        sources.load_source(destination)


def test_scan_cache_is_byte_bound_and_relabels_the_current_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence._SCAN_RESULTS.clear()

    class Pattern:
        pattern = "secret"
        flags = 0
        calls = 0

        def search(self, value: str) -> re.Match | None:
            self.calls += 1
            return re.search(self.pattern, value)

    scanner = Pattern()
    monkeypatch.setattr(evidence, "_SECRET_PATTERNS", (("fixture", scanner),))
    assert evidence._scan("first.json", b'{"value":"public"}') == []
    assert evidence._scan("second.json", b'{"value":"public"}') == []
    assert scanner.calls == 1
    assert evidence._scan("second.json", b'{"value":"secret"}') == [
        "Credential pattern fixture in second.json"
    ]
    assert evidence._scan("third.json", b'{"value":"secret"}') == [
        "Credential pattern fixture in third.json"
    ]
    assert scanner.calls == 2
    for index in range(70):
        evidence._scan("bounded.json", str(index).encode())
    assert len(evidence._SCAN_RESULTS) == 64


def test_source_reference_cache_rejects_changed_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "run"
    _, review = make_run(root)
    analysis = read_json(root / "analysis.json")
    analysis["findings"][0]["source_refs"] = [
        {"source_id": "csl", "snapshot_id": "source", "record_id": "R1"}
    ]
    source = canonical_json(
        {"source_id": "csl", "snapshot_id": "source", "entries": [{"record_id": "R1"}]}
    )
    content = {
        "analysis.json": canonical_json(analysis),
        "data/dataset.json": (root / "data/dataset.json").read_bytes(),
        "sources/source.json": source,
    }
    evidence._SOURCE_REFERENCES.clear()
    decode = evidence._json_bytes
    calls = []

    def counted(raw: bytes, **kwargs: object) -> object:
        if raw == source:
            calls.append(raw)
        return decode(raw, **kwargs)

    monkeypatch.setattr(evidence, "_json_bytes", counted)
    assert evidence._review_issues(content, review, "run_demo") == []
    assert evidence._review_issues(content, review, "run_demo") == []
    assert len(calls) == 1
    content["sources/source.json"] = source.replace(b"R1", b"R2")
    assert "Unresolved source evidence" in "; ".join(
        evidence._review_issues(content, review, "run_demo")
    )
    assert all(
        isinstance(value, frozenset) for value in evidence._SOURCE_REFERENCES.values()
    )
