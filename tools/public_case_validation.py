#!/usr/bin/env python3
"""Evaluate frozen official-record extracts offline; no operational workspace writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
from pathlib import Path

from omphalos.data import validate_tables
from omphalos.investigations import analyze

ROOT = Path(__file__).resolve().parents[1]
FROZEN_CORPUS_SHA256 = (
    "6267e4d2edd57813f25a999679e8d805d5e4b18df4437b9ec97e7f4bb3532d97"
)


def corpus():
    # Fixed repository-owned module, never an uploaded Python file.
    fixtures = runpy.run_path(str(ROOT / "tests" / "public_case_fixtures.py"))
    return {
        "screening": fixtures["public_case_suite"](),
        "transaction_coverage": fixtures["seagate_coverage_case"](),
    }


def corpus_sha256(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def evaluate_public_cases():
    frozen = corpus()
    digest = corpus_sha256(frozen)
    if digest != FROZEN_CORPUS_SHA256:
        raise ValueError(
            "Public-case labels changed; create a separately versioned corpus instead"
        )
    benchmark = runpy.run_path(str(ROOT / "tools" / "detection_benchmark.py"))
    screening = benchmark["evaluate_suite"](frozen["screening"])
    fixture = frozen["transaction_coverage"]
    tables, _ = validate_tables(fixture["tables"])
    coverage = analyze(
        {
            "tables": tables,
            "metadata": {"dataset_id": "public-coverage", "synthetic": False},
        },
        fixture["case"],
    )
    coverage_passed = (
        not coverage["findings"]
        and len(coverage["coverage"]) == len(fixture["case"]["investigations"])
        and all(row["status"] == "not_evaluable" for row in coverage["coverage"])
    )
    input_kinds = {
        row["id"]: row["provenance"]["input_kind"]
        for row in frozen["screening"]["cases"]
    }
    by_input_kind = {}
    for result in screening["cases"]:
        kind = input_kinds[result["id"]]
        result["input_kind"] = kind
        grouped = by_input_kind.setdefault(kind, {"cases": 0, "counts": {}})
        grouped["cases"] += 1
        for name, count in result["counts"].items():
            grouped["counts"][name] = grouped["counts"].get(name, 0) + count
    return {
        "schema_version": "1.0",
        "validation_kind": "public-source desk validation",
        "independent_practitioner_validation": False,
        "frozen_corpus_sha256": digest,
        "source_documents": frozen["screening"]["source_documents"],
        "screening": screening,
        "by_input_kind": by_input_kind,
        "transaction_coverage": {
            "source_document": fixture["source_document"],
            "expectation": fixture["expected"],
            "coverage": coverage["coverage"],
            "findings_count": len(coverage["findings"]),
            "passed": coverage_passed,
        },
        "passed": screening["summary"]["contract_passed"] and coverage_passed,
        "limitations": [
            "Six historically published organization records are a convenience sample, not an operational prevalence sample.",
            "Names, aliases and identifiers are official-source extracts; formatting, missing-data, placeholder-name and namespace controls are explicitly constructed.",
            "Candidate labels do not establish identity, current restrictions, prohibited conduct, or clearance.",
            "The BIS case tests missing transaction evidence, not whether heuristics can reproduce an enforcement decision.",
            "Software agents selected and checked this corpus. No working investigators participated, and no independent human adjudication is claimed.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = evaluate_public_cases()
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return int(args.check and not report["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
