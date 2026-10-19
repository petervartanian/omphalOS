#!/usr/bin/env python3
"""Offline, labeled detection evaluation. No workspace, network, or UI writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
from collections import Counter
from pathlib import Path
from typing import Callable

from omphalos.data import validate_tables
from omphalos.investigations import analyze, catalog
from omphalos.runner import engine_inventory
from omphalos.util import canonical_json

ROOT = Path(__file__).resolve().parents[1]
COUNT_KEYS = ("tp", "fp", "fn", "tn", "unavailable_positive", "unavailable_negative")


def observation_unit(check: str, finding: dict) -> str:
    """Map emitted observations to labeled subjects, never their engine hash IDs."""
    metrics = finding["metrics"]
    if check in {
        "payment_fragmentation",
        "mixed_payment_methods",
        "threshold_cluster",
        "weekend_shipments",
    }:
        records = [
            ref["record_id"]
            for ref in finding["record_refs"]
            if ref["table"] == "shipments"
        ]
        if len(records) != 1:
            raise ValueError(f"{check} observation does not identify one shipment")
        return records[0]
    if check == "unit_price_outlier":
        return metrics["shipment_id"]
    if check == "multi_domain":
        return finding["entity_ids"][0]
    if check == "shared_address":
        return "|".join(metrics["normalized_address"])
    if check == "invoice_overlap":
        return metrics["normalized_invoice"]
    if check == "broker_concentration":
        return metrics["broker_label"]
    if check == "volume_spike":
        return finding["entity_ids"][0] + "|" + metrics["month"]
    if check == "screening_candidates":
        return finding["entity_ids"][0] + "|" + finding["source_refs"][0]["record_id"]
    if check == "data_quality":
        return metrics["table"] + "." + metrics["field"]
    raise ValueError(f"No observation-unit mapping for {check}")


def _empty_counts() -> dict:
    return dict.fromkeys(COUNT_KEYS, 0)


def _rates(counts: dict) -> dict:
    def ratio(numerator: int, denominator: int) -> dict:
        # Exact counts are authoritative; a zero denominator is undefined.
        return {
            "numerator": numerator,
            "denominator": denominator,
            "value": round(numerator / denominator, 6) if denominator else None,
        }

    return {
        "precision": ratio(counts["tp"], counts["tp"] + counts["fp"]),
        "recall": ratio(counts["tp"], counts["tp"] + counts["fn"]),
        "false_positive_rate": ratio(counts["fp"], counts["fp"] + counts["tn"]),
    }


def _validate_suite(suite: dict) -> None:
    if suite.get("schema_version") != "1.0":
        raise ValueError("Benchmark suite schema_version must be 1.0")
    if type(suite.get("synthetic")) is not bool:
        raise ValueError("Each suite must declare whether its corpus is synthetic")
    provenance = suite.get("provenance")
    if not isinstance(provenance, dict) or any(
        not isinstance(provenance.get(field), str) or not provenance[field].strip()
        for field in ("corpus_id", "label_provenance", "scope")
    ):
        raise ValueError(
            "Corpus ID, label provenance, and evaluation scope are required"
        )
    if not isinstance(suite.get("cases"), list) or not suite["cases"]:
        raise ValueError("A nonempty cases list is required")
    known = {row["id"] for row in catalog()}
    ids = set()
    for case in suite["cases"]:
        if not isinstance(case.get("id"), str) or not case["id"]:
            raise ValueError("Each benchmark case requires an ID")
        if case["id"] in ids:
            raise ValueError("Duplicate benchmark case ID")
        ids.add(case["id"])
        if case.get("check") not in known:
            raise ValueError("Unknown benchmark check")
        if case.get("kind") not in {"contract", "challenge"}:
            raise ValueError("Each case must be a contract or challenge case")
        if not isinstance(case.get("rationale"), str) or not case["rationale"].strip():
            raise ValueError("Each case requires a labeling rationale")
        if case.get("expected_coverage") not in {"executed", "not_evaluable"}:
            raise ValueError("Each case requires an explicit coverage expectation")
        if not isinstance(case.get("targets"), list) or not case["targets"]:
            raise ValueError("Each case requires labeled targets")
        units = set()
        for target in case["targets"]:
            unit = target.get("unit")
            if not isinstance(unit, str) or not unit or unit in units:
                raise ValueError("Target units must be unique nonempty strings")
            units.add(unit)
            if type(target.get("positive")) is not bool:
                raise ValueError("Target positive labels must be booleans")
            if type(target.get("ordinary_explanation", False)) is not bool:
                raise ValueError("ordinary_explanation must be a boolean")
            if target.get("ordinary_explanation") and not target["positive"]:
                raise ValueError(
                    "An ordinary-pattern burden label needs a positive target"
                )


def evaluate_suite(suite: dict, *, analyzer: Callable = analyze) -> dict:
    """Score predeclared observation targets; unavailable is never a true negative."""
    _validate_suite(suite)
    results = []
    by_check = {}
    failures = []
    for fixture in sorted(suite["cases"], key=lambda row: row["id"]):
        check = fixture["check"]
        tables, _ = validate_tables(fixture["tables"])
        case = {
            "case_id": "benchmark",
            "question": "Which labeled synthetic patterns produce review observations?",
            "dataset_id": "benchmark",
            "as_of": "2026-10-01",
            "investigations": [check],
            **fixture.get("case", {}),
        }
        if case["investigations"] != [check] or case["dataset_id"] != "benchmark":
            raise ValueError("A benchmark case must evaluate its one declared check")
        dataset = {
            "metadata": {"dataset_id": "benchmark", "synthetic": suite["synthetic"]},
            "tables": tables,
        }
        result = analyzer(dataset, case, fixture.get("watchlist"))
        if len(result["coverage"]) != 1:
            raise ValueError("Expected exactly one coverage record")
        coverage = result["coverage"][0]
        if coverage["investigation_id"] != check:
            raise ValueError("Coverage belongs to a different check")
        if coverage["status"] not in {"executed", "not_evaluable"}:
            raise ValueError("Unexpected coverage status")
        actual = Counter()
        refs = set()
        cited_count = 0
        for finding in result["findings"]:
            if finding["investigation_id"] != check:
                raise ValueError("Observation belongs to a different check")
            actual[observation_unit(check, finding)] += 1
            for ref in finding["record_refs"]:
                refs.add((ref["table"], ref["record_id"]))
                cited_count += 1
        if coverage["findings_count"] != sum(actual.values()):
            raise ValueError("Coverage observation count differs from output")
        if coverage["status"] == "not_evaluable" and actual:
            raise ValueError("Unavailable check emitted observations")
        expected = {target["unit"]: target for target in fixture["targets"]}
        counts = _empty_counts()
        missed, unexpected = [], []
        for unit, target in expected.items():
            if coverage["status"] == "not_evaluable":
                counts[
                    (
                        "unavailable_positive"
                        if target["positive"]
                        else "unavailable_negative"
                    )
                ] += 1
            elif target["positive"]:
                counts["tp" if actual[unit] else "fn"] += 1
                if not actual[unit]:
                    missed.append(unit)
            else:
                counts["fp" if actual[unit] else "tn"] += 1
                if actual[unit]:
                    unexpected.append(unit)
        # Emissions outside the labeled universe cannot disappear from scoring.
        for unit in actual.keys() - expected.keys():
            counts["fp"] += 1
            unexpected.append(unit)
        duplicates = sum(max(0, count - 1) for count in actual.values())
        ordinary = sum(
            actual[unit]
            for unit, target in expected.items()
            if target.get("ordinary_explanation")
        )
        status_matches = coverage["status"] == fixture["expected_coverage"]
        failure = (
            not status_matches
            or duplicates > 0
            or (fixture["kind"] == "contract" and (counts["fp"] or counts["fn"]))
        )
        if failure:
            failures.append(fixture["id"])
        row = {
            "id": fixture["id"],
            "check": check,
            "kind": fixture["kind"],
            "rationale": fixture["rationale"],
            "counts": counts,
            "coverage": coverage,
            "expected_coverage": fixture["expected_coverage"],
            "coverage_matches": status_matches,
            "emitted_units": dict(sorted(actual.items())),
            "missed_units": sorted(missed),
            "unexpected_units": sorted(unexpected),
            "burden": {
                "observations": sum(actual.values()),
                "duplicate_observations": duplicates,
                "ordinary_explanation_observations": ordinary,
                "cited_record_occurrences": cited_count,
                "distinct_cited_records": len(refs),
            },
            "input_sha256": hashlib.sha256(canonical_json(fixture)).hexdigest(),
            "analysis_sha256": hashlib.sha256(canonical_json(result)).hexdigest(),
        }
        results.append(row)
        aggregate = by_check.setdefault(
            check,
            {
                "cases": 0,
                "unavailable_cases": 0,
                "counts": _empty_counts(),
                "contract_counts": _empty_counts(),
                "challenge_counts": _empty_counts(),
                "burden": dict.fromkeys(row["burden"], 0),
            },
        )
        aggregate["cases"] += 1
        aggregate["unavailable_cases"] += coverage["status"] == "not_evaluable"
        for key, count in counts.items():
            aggregate["counts"][key] += count
            aggregate[fixture["kind"] + "_counts"][key] += count
        for key, count in row["burden"].items():
            aggregate["burden"][key] += count
    totals = _empty_counts()
    for aggregate in by_check.values():
        aggregate["rates"] = _rates(aggregate["counts"])
        for key in COUNT_KEYS:
            totals[key] += aggregate["counts"][key]
    return {
        "schema_version": "1.0",
        "suite_id": suite.get("suite_id", "unnamed"),
        "synthetic": suite["synthetic"],
        "provenance": suite["provenance"],
        "label_meaning": "Expected observations for predeclared subjects; not wrongdoing, identity confirmation, or clearance.",
        "limitations": [
            (
                "Constructed cases are not representative prevalence samples or independent practitioner labels."
                if suite["synthetic"]
                else "External corpus labels, authorization, representativeness, and independence are supplied by the evaluator and are not verified by this harness."
            ),
            "Rates describe only these labeled targets; they do not estimate operational accuracy.",
            "Known capability gaps remain in challenge-case misses; they are not relabeled as negatives.",
            "Unavailable targets are excluded from precision, recall, and false-positive-rate denominators.",
            "Ordinary explanations quantify review burden; the detector is not expected to decide whether they are true.",
            "Case-record citation counts are summed within cases, not deduplicated across independent fixtures.",
        ],
        "suite_sha256": hashlib.sha256(canonical_json(suite)).hexdigest(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "engine_inventory": engine_inventory(),
        "summary": {
            "cases": len(results),
            "checks": len(by_check),
            "counts": totals,
            "rates": _rates(totals),
            "contract_passed": not failures,
            "failure_case_ids": sorted(failures),
        },
        "by_check": dict(sorted(by_check.items())),
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        help="An authorized labeled JSON suite, with corpus provenance and scope",
    )
    parser.add_argument(
        "--output", type=Path, help="Write deterministic JSON here instead of stdout"
    )
    parser.add_argument(
        "--check", action="store_true", help="Fail on contract or coverage regressions"
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Also fail on challenge misses or any unavailable positive target",
    )
    args = parser.parse_args()
    if args.suite:
        suite = json.loads(args.suite.read_text(encoding="utf-8"))
    else:
        # This is a trusted repository test module, never a user-provided path.
        fixture_module = ROOT / "tests" / "detection_benchmark_fixtures.py"
        suite = runpy.run_path(str(fixture_module))["benchmark_suite"]()
    report = evaluate_suite(suite)
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.require_complete:
        counts = report["summary"]["counts"]
        if counts["fp"] or counts["fn"] or counts["unavailable_positive"]:
            return 1
    return int(
        (args.check or args.require_complete)
        and not report["summary"]["contract_passed"]
    )


if __name__ == "__main__":
    raise SystemExit(main())
