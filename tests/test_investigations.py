from copy import deepcopy
from decimal import Decimal

import pytest

from omphalos.data import create_demo, load_dataset, validate_tables
from omphalos.investigations import analyze, catalog


def dataset(tables):
    normalized, _ = validate_tables(tables)
    return {
        "tables": normalized,
        "metadata": {"dataset_id": "data", "synthetic": False},
    }


def case(*ids, **updates):
    return {
        "case_id": "case1",
        "question": "Which records require further investigation?",
        "dataset_id": "data",
        "as_of": "2026-10-13",
        "investigations": list(ids),
        **updates,
    }


def sample_prices(values, currencies=None, units=None, commodities=None):
    shipments, payments = [], []
    for i, value in enumerate(values):
        shipments.append(
            {
                "shipment_id": f"S{i}",
                "exporter_id": "E1",
                "qty": "1",
                "unit": units[i] if units else "pcs",
                "hs_code": commodities[i] if commodities else "845610",
            }
        )
        payments.append(
            {
                "payment_id": f"P{i}",
                "shipment_id": f"S{i}",
                "amount": str(value),
                "ccy": currencies[i] if currencies else "USD",
            }
        )
    return dataset(
        {
            "entities": [{"entity_id": "E1", "name": "Example"}],
            "shipments": shipments,
            "payments": payments,
        }
    )


def test_true_median_does_not_flag_normals():
    result = analyze(sample_prices([1, 1, 1, 1, 100]), case("unit_price_outlier"))
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["metrics"]["shipment_id"] == "S4"
    assert finding["metrics"]["cohort_median"] == "1"
    assert len(finding["record_refs"]) == 10


def test_even_median():
    data = sample_prices([1, 1, 2, 2, 3, 100])
    result = analyze(data, case("unit_price_outlier"))
    assert result["findings"][0]["metrics"]["cohort_median"] == "2"


@pytest.mark.parametrize("variant", ["currencies", "units", "commodities"])
def test_no_cross_currency_unit_commodity_comparisons(variant):
    options = {
        "currencies": ["USD"] * 4 + ["EUR"],
        "units": ["pcs"] * 4 + ["kg"],
        "commodities": ["845610"] * 4 + ["902780"],
    }
    result = analyze(
        sample_prices([1, 1, 1, 1, 100], **{variant: options[variant]}),
        case("unit_price_outlier"),
    )
    assert result["findings"] == []
    assert result["coverage"][0]["status"] == "not_evaluable"


def test_mixed_currency_on_same_shipment_excluded():
    data = sample_prices([1, 1, 1, 1, 100])
    data["tables"]["payments"].append(
        {"payment_id": "other", "shipment_id": "S4", "amount": "1000", "ccy": "EUR"}
    )
    result = analyze(data, case("unit_price_outlier"))
    assert result["findings"] == []
    assert any("1 with mixed" in line for line in result["coverage"][0]["limitations"])


def test_invoice_full_value_not_shared_prefix():
    data = dataset(
        {
            "entities": [
                {"entity_id": "E1", "name": "One"},
                {"entity_id": "E2", "name": "Two"},
            ],
            "shipments": [
                {"shipment_id": "S1", "exporter_id": "E1", "invoice_id": "INV-1001"},
                {"shipment_id": "S2", "exporter_id": "E2", "invoice_id": "INV-1002"},
            ],
        }
    )
    assert not analyze(data, case("invoice_overlap"))["findings"]
    data["tables"]["shipments"][1]["invoice_id"] = "inv / 1001"
    assert len(analyze(data, case("invoice_overlap"))["findings"]) == 1


def test_threshold_currency_and_upper_exclusion():
    data = sample_prices(
        [9700, 9800, 9999, 10000], currencies=["USD", "USD", "EUR", "USD"]
    )
    for p in data["tables"]["payments"]:
        p["shipment_id"] = "S0"
    result = analyze(
        data,
        case(
            "threshold_cluster",
            parameters={"threshold_cluster": {"threshold": "10000", "currency": "USD"}},
        ),
    )
    assert result["findings"][0]["metrics"]["payment_count"] == 2
    assert {
        r["record_id"]
        for r in result["findings"][0]["record_refs"]
        if r["table"] == "payments"
    } == {"P0", "P1"}
    missing = analyze(data, case("threshold_cluster"))
    assert missing["coverage"][0]["status"] == "not_evaluable"


def test_missing_tables_differ_from_executed_zero():
    entities = dataset({"entities": [{"entity_id": "E1", "name": "Example"}]})
    assert (
        analyze(entities, case("payment_fragmentation"))["coverage"][0]["status"]
        == "not_evaluable"
    )
    data = sample_prices([1])
    result = analyze(data, case("payment_fragmentation"))
    assert result["coverage"][0]["status"] == "executed" and not result["findings"]


def test_scope_and_as_of_are_executed():
    data = sample_prices([1, 1, 1, 1])
    for index, s in enumerate(data["tables"]["shipments"]):
        s.update(
            date=["2026-01-01", "2026-02-01", None, "2027-01-01"][index],
            domain="machine_tools",
        )
    bounded = analyze(
        data,
        case(
            "payment_fragmentation",
            scope={"date_from": "2026-02-01", "date_to": "2026-03-01"},
        ),
    )
    assert bounded["scope_counts"]["shipments_in_scope"] == 1
    # Undated payments are excluded when an explicit date range is supplied.
    assert bounded["scope_counts"]["payments_in_scope"] == 0
    unbounded = analyze(data, case("payment_fragmentation"))
    assert unbounded["scope_counts"]["shipments_in_scope"] == 3
    assert unbounded["scope_counts"]["payments_in_scope"] == 3


def test_volume_zeros_in_baseline_and_partial_month_excluded():
    rows = [{"shipment_id": "early", "exporter_id": "E1", "date": "2026-01-01"}]
    rows += [
        {"shipment_id": f"S{i}", "exporter_id": "E1", "date": "2026-04-02"}
        for i in range(6)
    ]
    data = dataset(
        {"entities": [{"entity_id": "E1", "name": "Example"}], "shipments": rows}
    )
    selected = case(
        "volume_spike",
        as_of="2026-05-01",
        parameters={"volume_spike": {"window_months": 3, "minimum_prior_shipments": 1}},
    )
    result = analyze(data, selected)
    metrics = result["findings"][0]["metrics"]
    assert metrics["prior_month_counts"] == {"2026-01": 1, "2026-02": 0, "2026-03": 0}
    assert Decimal(metrics["ratio"]) == 18
    selected["as_of"] = "2026-04-30"
    assert not analyze(data, selected)["findings"]


@pytest.mark.parametrize(
    "parameters",
    [
        {"not_real": 3},
        {"minimum_payments": True},
        {"minimum_payments": 1},
        {"minimum_payments": "3"},
    ],
)
def test_invalid_detector_parameters_rejected(parameters):
    with pytest.raises(ValueError):
        analyze(
            sample_prices([1]),
            case(
                "payment_fragmentation",
                parameters={"payment_fragmentation": parameters},
            ),
        )


def test_only_selected_detector_executes_and_result_deterministic(tmp_path):
    create_demo(tmp_path / "data")
    data = load_dataset(tmp_path / "data")
    selected = case("payment_fragmentation")
    one = analyze(data, selected)
    reordered = deepcopy(data)
    for rows in reordered["tables"].values():
        rows.reverse()
    two = analyze(reordered, selected)
    assert one == two
    assert {f["investigation_id"] for f in one["findings"]} == {"payment_fragmentation"}
    assert len(one["coverage"]) == 1


def test_demo_known_patterns_and_benign_installments(tmp_path):
    create_demo(tmp_path / "data")
    result = analyze(
        load_dataset(tmp_path / "data"),
        case(
            *[row["id"] for row in catalog()],
            parameters={"threshold_cluster": {"threshold": "10000", "currency": "USD"}},
        ),
    )
    counts = {
        row["investigation_id"]: row["findings_count"] for row in result["coverage"]
    }
    assert counts["shared_address"] == 1
    assert counts["volume_spike"] == 1
    assert counts["payment_fragmentation"] == 1
    assert not any(
        ref["record_id"] == "BENIGN"
        for f in result["findings"]
        if f["investigation_id"] == "payment_fragmentation"
        for ref in f["record_refs"]
    )


def test_ambient_decimal_precision_does_not_change_analysis():
    from decimal import localcontext

    data = sample_prices(["9007199254740993.12345678"] * 3)
    for p in data["tables"]["payments"]:
        p["shipment_id"] = "S0"
    selected = case("payment_fragmentation")
    with localcontext() as context:
        context.prec = 6
        one = analyze(data, selected)
    with localcontext() as context:
        context.prec = 80
        two = analyze(data, selected)
    assert one == two
    assert (
        one["findings"][0]["metrics"]["totals_by_currency"]["USD"]
        == "27021597764222979.37037034"
    )


def test_ambient_rounding_mode_does_not_change_ratios():
    from decimal import ROUND_DOWN, ROUND_UP, localcontext

    data = sample_prices([3, 3, 3, 3, 100])
    with localcontext() as context:
        context.rounding = ROUND_UP
        one = analyze(data, case("unit_price_outlier"))
    with localcontext() as context:
        context.rounding = ROUND_DOWN
        two = analyze(data, case("unit_price_outlier"))
    assert one == two
