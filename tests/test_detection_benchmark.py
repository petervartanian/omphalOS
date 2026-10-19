"""The evaluator must catch wrong targets, misses, and unavailable coverage."""

import importlib.util
import json
import os
import runpy
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from omphalos.investigations import analyze, catalog

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "detection_benchmark", ROOT / "tools" / "detection_benchmark.py"
)
BENCHMARK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCHMARK)
FIXTURES = runpy.run_path(str(ROOT / "tests" / "detection_benchmark_fixtures.py"))


def suite_with(*case_ids):
    suite = FIXTURES["benchmark_suite"]()
    suite["cases"] = [row for row in suite["cases"] if row["id"] in case_ids]
    assert len(suite["cases"]) == len(case_ids)
    return suite


def test_full_catalog_contracts_and_capability_gaps_are_separately_measured():
    suite = FIXTURES["benchmark_suite"]()
    before = deepcopy(suite)
    report = BENCHMARK.evaluate_suite(suite)
    assert suite == before
    assert set(report["by_check"]) == {row["id"] for row in catalog()}
    assert report["summary"]["contract_passed"]
    for result in report["by_check"].values():
        counts = result["contract_counts"]
        assert counts["tp"] > 0 and counts["tn"] > 0
        assert counts["fp"] == counts["fn"] == 0
        assert result["unavailable_cases"] > 0
    by_id = {row["id"]: row for row in report["cases"]}
    cap = by_id["screening_candidates-approximate-display-limit-challenge"]
    assert cap["counts"]["tp"] == 7 and cap["counts"]["fn"] == 0
    assert by_id["screening_candidates-cross-script-challenge"]["counts"]["tp"] == 1
    assert by_id["screening_candidates-cross-script-challenge"]["counts"]["fn"] == 0
    assert by_id["screening_candidates-exact-matches-beyond-limit"]["counts"]["tp"] == 7
    assert (
        by_id["screening_candidates-cross-script-supplied-alias"]["counts"]["tp"] == 1
    )
    assert report["summary"]["counts"]["unavailable_positive"] > 0
    assert report["summary"]["counts"]["fn"] == 0
    assert all(
        row["input_sha256"] and row["analysis_sha256"] for row in report["cases"]
    )


def test_same_output_count_on_the_wrong_subject_is_both_a_miss_and_false_positive():
    suite = suite_with("unit_price_outlier-high-inclusive")

    def wrong_subject(*args):
        result = analyze(*args)
        result["findings"][0]["metrics"]["shipment_id"] = "S1"
        return result

    report = BENCHMARK.evaluate_suite(suite, analyzer=wrong_subject)
    counts = report["summary"]["counts"]
    assert counts["fn"] == counts["fp"] == 1 and counts["tp"] == 0
    assert not report["summary"]["contract_passed"]
    assert report["cases"][0]["missed_units"] == ["S5"]
    assert report["cases"][0]["unexpected_units"] == ["S1"]


def test_an_unlabeled_emission_cannot_disappear_from_scoring():
    suite = suite_with("unit_price_outlier-high-inclusive")

    def unexpected_subject(*args):
        result = analyze(*args)
        result["findings"][0]["metrics"]["shipment_id"] = "unlabeled-subject"
        return result

    report = BENCHMARK.evaluate_suite(suite, analyzer=unexpected_subject)
    assert report["summary"]["counts"]["fp"] == 1
    assert report["summary"]["counts"]["fn"] == 1
    assert report["cases"][0]["unexpected_units"] == ["unlabeled-subject"]


def test_dropped_observation_is_a_miss_even_if_coverage_count_is_consistent():
    suite = suite_with("payment_fragmentation-count-3")

    def suppress(*args):
        result = analyze(*args)
        result["findings"] = []
        result["coverage"][0]["findings_count"] = 0
        return result

    report = BENCHMARK.evaluate_suite(suite, analyzer=suppress)
    assert report["summary"]["counts"]["fn"] == 1
    assert not report["summary"]["contract_passed"]


def test_duplicate_observation_cannot_inflate_true_positive_count():
    suite = suite_with("payment_fragmentation-count-3")

    def duplicate(*args):
        result = analyze(*args)
        result["findings"] *= 2
        result["coverage"][0]["findings_count"] = 2
        return result

    report = BENCHMARK.evaluate_suite(suite, analyzer=duplicate)
    assert report["summary"]["counts"]["tp"] == 1
    assert report["cases"][0]["burden"]["duplicate_observations"] == 1
    assert not report["summary"]["contract_passed"]


def test_unavailable_checks_are_neither_clean_results_nor_misses():
    suite = suite_with("unit_price_outlier-separate-currency")
    report = BENCHMARK.evaluate_suite(suite)
    counts = report["summary"]["counts"]
    assert counts == {
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "tn": 0,
        "unavailable_positive": 1,
        "unavailable_negative": 4,
    }
    assert all(rate["value"] is None for rate in report["summary"]["rates"].values())
    assert report["summary"]["contract_passed"]


def test_coverage_regression_is_a_failure_even_without_false_observations():
    suite = suite_with("payment_fragmentation-count-2")

    def unavailable(*args):
        result = analyze(*args)
        result["coverage"][0].update(status="not_evaluable", records_evaluated=0)
        return result

    report = BENCHMARK.evaluate_suite(suite, analyzer=unavailable)
    assert not report["summary"]["contract_passed"]
    assert not report["cases"][0]["coverage_matches"]


def test_ordinary_explanations_are_burden_not_false_positive_legal_labels():
    suite = suite_with("payment_fragmentation-ordinary-installments")
    report = BENCHMARK.evaluate_suite(suite)
    result = report["cases"][0]
    assert result["counts"]["tp"] == 1 and result["counts"]["fp"] == 0
    assert result["burden"]["ordinary_explanation_observations"] == 1
    assert result["burden"]["distinct_cited_records"] == 4


def test_permuting_record_and_source_order_preserves_scored_observations():
    suite = FIXTURES["benchmark_suite"]()
    original = BENCHMARK.evaluate_suite(suite)
    for case in suite["cases"]:
        for rows in case["tables"].values():
            rows.reverse()
        if case.get("watchlist"):
            case["watchlist"]["entries"].reverse()
    permuted = BENCHMARK.evaluate_suite(suite)
    assert original["summary"] == permuted["summary"]
    assert original["by_check"] == permuted["by_check"]
    assert [row["analysis_sha256"] for row in original["cases"]] == [
        row["analysis_sha256"] for row in permuted["cases"]
    ]


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate_case",
        "duplicate_target",
        "nonboolean_label",
        "missing_provenance",
        "missing_scope",
        "unknown_check",
    ],
)
def test_malformed_labels_and_missing_provenance_fail_closed(problem):
    suite = suite_with("payment_fragmentation-count-3")
    if problem == "duplicate_case":
        suite["cases"] *= 2
    elif problem == "duplicate_target":
        suite["cases"][0]["targets"] *= 2
    elif problem == "nonboolean_label":
        suite["cases"][0]["targets"][0]["positive"] = 1
    elif problem == "missing_provenance":
        suite.pop("provenance")
    elif problem == "missing_scope":
        suite["provenance"]["scope"] = ""
    else:
        suite["cases"][0]["check"] = "invented_detector"
    with pytest.raises(ValueError):
        BENCHMARK.evaluate_suite(suite)


def test_external_corpus_metadata_is_retained_without_claiming_label_validation():
    # Still uses invented records here; this exercises the external-corpus contract.
    suite = suite_with("payment_fragmentation-count-3")
    suite["synthetic"] = False
    suite["provenance"] = {
        "corpus_id": "local-evaluator-accession",
        "label_provenance": "Evaluator-supplied labels; independently reviewed elsewhere.",
        "scope": "A locally authorized corpus limited to linked payment counts.",
    }
    result = BENCHMARK.evaluate_suite(suite)
    assert result["synthetic"] is False
    assert result["provenance"] == suite["provenance"]
    assert "not verified by this harness" in result["limitations"][0]


def test_cli_outputs_identical_reports_and_does_not_claim_complete_coverage(tmp_path):
    output = tmp_path / "evaluation.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    command = [
        sys.executable,
        str(ROOT / "tools" / "detection_benchmark.py"),
        "--output",
        str(output),
    ]
    first = subprocess.run([*command, "--check"], env=env, capture_output=True)
    assert first.returncode == 0, first.stderr.decode()
    raw = output.read_bytes()
    second = subprocess.run(
        [*command, "--require-complete"], env=env, capture_output=True
    )
    assert second.returncode == 1, second.stderr.decode()
    assert output.read_bytes() == raw
    assert json.loads(raw)["summary"]["contract_passed"]


def test_cli_accepts_external_json_without_loading_python_from_input(tmp_path):
    suite = suite_with("payment_fragmentation-count-3")
    source = tmp_path / "labeled-corpus.json"
    source.write_text(json.dumps(suite), encoding="utf-8")
    output = tmp_path / "evaluation.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "detection_benchmark.py"),
            "--suite",
            str(source),
            "--output",
            str(output),
            "--check",
        ],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert (
        json.loads(output.read_text(encoding="utf-8"))["summary"]["counts"]["tp"] == 1
    )
