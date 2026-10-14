"""Versioned data contracts for analytical intent, observations, and review."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
]
Text = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=10000
    ),
]
Substance = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=12, max_length=10000
    ),
]
SubstanceList = Annotated[list[Substance], Field(min_length=1, max_length=100)]
Count = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]


def _iso_date(value: Any) -> Any:
    if value is None or type(value) is date:
        return value
    if (
        isinstance(value, datetime)
        or not isinstance(value, str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
    ):
        raise ValueError("Dates must use the explicit YYYY-MM-DD format")
    return value


def _substantive_text(value: str | list[str]) -> str | list[str]:
    values = [value] if isinstance(value, str) else value
    for text in values:
        cleaned = re.sub(r"[^a-z0-9]", "", text.lower())
        placeholders = {
            "tbd",
            "todo",
            "placeholder",
            "notapplicable",
            "unknown",
            "none",
            "na",
        }
        # A syntax gate cannot assess reasoning quality. It can reject obvious
        # empty/punctuation-only or repeated placeholder submissions.
        if not any(character.isalnum() for character in text) or any(
            cleaned and cleaned == word * (len(cleaned) // len(word))
            for word in placeholders
        ):
            raise ValueError("Replace placeholders with case-specific reasoning")
    return value


def _metric_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int:
        if not -(2**63) <= value < 2**63:
            raise ValueError(
                "Metric integers outside signed 64-bit range must be strings"
            )
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _metric_value(item)
        return
    if isinstance(value, list):
        for item in value:
            _metric_value(item)
        return
    raise ValueError(
        "Metrics require JSON values with exact decimal amounts as strings"
    )


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Scope(Contract):
    date_from: date | None = None
    date_to: date | None = None
    domains: list[Text] = Field(default_factory=list, max_length=100)
    entity_ids: list[Identifier] = Field(default_factory=list, max_length=10000)

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def explicit_dates(cls, value: Any) -> Any:
        return _iso_date(value)

    @model_validator(mode="after")
    def date_order(self) -> Scope:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be no later than date_to")
        return self


class Case(Contract):
    schema_version: Literal["2.0"] = "2.0"
    case_id: Identifier
    question: Substance
    dataset_id: Identifier
    as_of: date
    investigations: list[Identifier] = Field(min_length=1, max_length=100)
    scope: Scope = Field(default_factory=Scope)
    parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    watchlist_snapshot_id: Identifier | None = None

    @field_validator("as_of", mode="before")
    @classmethod
    def explicit_date(cls, value: Any) -> Any:
        return _iso_date(value)

    @field_validator("investigations")
    @classmethod
    def unique_investigations(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Investigations must not be repeated")
        return values

    @model_validator(mode="after")
    def parameter_scope(self) -> Case:
        if set(self.parameters) - set(self.investigations):
            raise ValueError("Parameters may only refer to selected investigations")
        return self


class RecordRef(Contract):
    table: Identifier
    record_id: Text


class SourceRef(Contract):
    snapshot_id: Identifier
    record_id: Text
    source_id: Identifier


class Finding(Contract):
    finding_id: Identifier
    investigation_id: Identifier
    title: Text
    observation: Substance
    entity_ids: list[Identifier] = Field(default_factory=list)
    record_refs: list[RecordRef] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    unknowns: SubstanceList
    alternatives: SubstanceList
    falsifiers: SubstanceList
    source_refs: list[SourceRef] = Field(default_factory=list)

    @field_validator("metrics")
    @classmethod
    def portable_metrics(cls, value: dict[str, Any]) -> dict[str, Any]:
        _metric_value(value)
        return value

    @model_validator(mode="after")
    def evidence_required(self) -> Finding:
        if not self.record_refs and not self.source_refs:
            raise ValueError("Findings must cite dataset records or source records")
        return self


class Coverage(Contract):
    investigation_id: Identifier
    status: Literal["executed", "not_evaluable"]
    records_evaluated: Count
    findings_count: Count
    reason: str = ""
    limitations: list[Text] = Field(default_factory=list)


class Analysis(Contract):
    findings: list[Finding]
    coverage: list[Coverage]
    scope_counts: dict[str, Count]
    warnings: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_counts(self) -> Analysis:
        ids = [finding.finding_id for finding in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("Finding IDs must be unique")
        coverage_ids = [row.investigation_id for row in self.coverage]
        if len(coverage_ids) != len(set(coverage_ids)):
            raise ValueError("Coverage entries must be unique")
        for row in self.coverage:
            actual = sum(
                f.investigation_id == row.investigation_id for f in self.findings
            )
            if row.findings_count != actual:
                raise ValueError(
                    f"Coverage count differs from findings: {row.investigation_id}"
                )
            if row.status == "not_evaluable" and (actual or not row.reason.strip()):
                raise ValueError(
                    "Not-evaluable coverage needs a reason and no findings"
                )
        if {f.investigation_id for f in self.findings} - set(coverage_ids):
            raise ValueError("Every finding requires a coverage entry")
        return self


class FindingReview(Contract):
    finding_id: Identifier
    disposition: Literal["follow_up", "explained", "escalate"]
    rationale: Substance
    unknowns: SubstanceList
    alternatives: SubstanceList
    falsifiers: SubstanceList

    @field_validator("rationale", "unknowns", "alternatives", "falsifiers")
    @classmethod
    def reject_placeholders(cls, value: str | list[str]) -> str | list[str]:
        return _substantive_text(value)


class Review(Contract):
    schema_version: Literal["2.0"] = "2.0"
    run_id: Identifier
    reviewer: Annotated[
        str,
        StringConstraints(
            strict=True, strip_whitespace=True, min_length=2, max_length=200
        ),
    ]
    summary: Substance
    findings: list[FindingReview]
    acknowledge_limitations: StrictBool

    @field_validator("summary")
    @classmethod
    def substantive_summary(cls, value: str) -> str:
        return str(_substantive_text(value))

    @model_validator(mode="after")
    def acknowledged_and_unique(self) -> Review:
        if not self.acknowledge_limitations:
            raise ValueError(
                "A reviewer must acknowledge the coverage and data limitations"
            )
        ids = [finding.finding_id for finding in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("Every finding may only be reviewed once per revision")
        return self
