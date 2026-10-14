"""Explainable list-record candidates; no automatic identity or legal decisions."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from .util import canonical_json, sha256_bytes


def normalized_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(
        "".join(
            c if c.isalnum() else " "
            for c in decomposed
            if not unicodedata.combining(c)
        ).split()
    )


@dataclass(frozen=True)
class _PreparedName:
    original: str
    normalized: str
    ordered: str
    counts: dict[str, int]


def _prepare_name(value: str) -> _PreparedName:
    normalized = normalized_name(value)
    return _PreparedName(
        value,
        normalized,
        " ".join(sorted(normalized.split())),
        dict(Counter(normalized)),
    )


def _score_prepared(a: _PreparedName, b: _PreparedName) -> Decimal:
    if not a.normalized or not b.normalized:
        return Decimal(0)
    if a.normalized == b.normalized or a.ordered == b.ordered:
        return Decimal(1)

    def score(x: str, y: str) -> Decimal:
        matching = sum(
            block.size
            for block in SequenceMatcher(
                None, x, y, autojunk=False
            ).get_matching_blocks()
        )
        return Decimal(2 * matching) / Decimal(len(x) + len(y))

    ordinary = score(a.normalized, b.normalized)
    if a.normalized == a.ordered and b.normalized == b.ordered:
        return ordinary
    return max(ordinary, score(a.ordered, b.ordered))


def name_score(left: str, right: str) -> Decimal:
    """Maximum exact character/token-order similarity, not a probability."""
    return _score_prepared(_prepare_name(left), _prepare_name(right))


def _can_reach(
    a: _PreparedName, b: _PreparedName, numerator: int, denominator: int
) -> bool:
    """Character intersection is an upper bound for both exact matching variants.

    This only prunes impossible candidates. It uses integer comparisons, so it
    cannot remove a candidate due to rounding near the requested threshold.
    """
    total = len(a.normalized) + len(b.normalized)
    if (
        not total
        or 2 * min(len(a.normalized), len(b.normalized)) * denominator
        < numerator * total
    ):
        return False
    common = sum(min(count, b.counts.get(char, 0)) for char, count in a.counts.items())
    return 2 * common * denominator >= numerator * total


def _identifier(value: str) -> str:
    return "".join(c for c in value.upper() if c.isalnum())


def _entity_category(value: str | None) -> str | None:
    value = normalized_name(value or "")
    if value in {
        "entity",
        "organization",
        "organisation",
        "company",
        "corporation",
        "business",
    }:
        return "organization"
    if value in {"person", "individual"}:
        return "individual"
    return value if value in {"vessel", "aircraft"} else None


def candidate_findings(
    entities: list[dict],
    snapshot: dict,
    as_of: date,
    *,
    minimum_score: Decimal = Decimal("0.90"),
    max_candidates: int = 5,
) -> tuple[list[dict], dict]:
    entries = snapshot["entries"]
    active = [
        entry
        for entry in entries
        if not (
            (entry.get("start_date") and entry["start_date"] > as_of.isoformat())
            or (entry.get("end_date") and entry["end_date"] < as_of.isoformat())
        )
    ]
    findings = []
    omitted = 0
    # Prepare Unicode, sorted tokens, and character counts only once per source name.
    prepared = [
        (
            entry,
            [
                _prepare_name(name)
                for name in [entry["name"], *entry.get("aliases", [])]
            ],
        )
        for entry in active
    ]
    threshold_numerator, threshold_denominator = minimum_score.as_integer_ratio()
    for entity in entities:
        candidates = []
        names = [
            _prepare_name(name) for name in [entity["name"], *entity.get("aliases", [])]
        ]
        for entry, source_names in prepared:
            best: tuple[Decimal, str, str] = (Decimal(0), "", "")
            for name in names:
                for source_name in source_names:
                    if not _can_reach(
                        name, source_name, threshold_numerator, threshold_denominator
                    ):
                        continue
                    score = _score_prepared(name, source_name)
                    if (score, name.original, source_name.original) > best:
                        best = (score, name.original, source_name.original)
            matched_ids = []
            identifier_comparisons = []
            for ident in entry.get("identifiers", []):
                if not isinstance(ident, dict):
                    continue
                number = ident.get("idNumber") or ident.get("number")
                kind = str(ident.get("idType") or ident.get("type") or "")
                if not isinstance(number, str):
                    continue
                # Registration IDs cannot safely be cross-matched to arbitrary passport/tax IDs.
                field = (
                    "lei"
                    if "legal entity identifier" in kind.lower()
                    or kind.lower() == "lei"
                    else "registration_id" if "registration" in kind.lower() else None
                )
                if field and entity.get(field):
                    same = _identifier(number) == _identifier(entity[field])
                    identifier_comparisons.append(
                        {
                            "field": field,
                            "source_type": kind,
                            "entity_value": entity[field],
                            "source_value": number,
                            "comparison": "equal" if same else "different",
                        }
                    )
                    if same:
                        matched_ids.append(
                            {"field": field, "source_type": kind, "value": number}
                        )
            if best[0] < minimum_score and not matched_ids:
                continue
            if matched_ids and best[0] < minimum_score:
                # For identifier-only candidates, report the actual best name score,
                # not the zero sentinel used while pruning non-candidates.
                best = max(
                    (
                        _score_prepared(name, source_name),
                        name.original,
                        source_name.original,
                    )
                    for name in names
                    for source_name in source_names
                )
            countries = entry.get("countries", [])
            country_context = "unknown"
            # Only compare like-for-like ISO codes; OFAC country labels are not ISO codes.
            iso_countries = [c for c in countries if re.fullmatch(r"[A-Z]{2}", c)]
            if entity.get("country") and iso_countries:
                country_context = (
                    "corroborates" if entity["country"] in iso_countries else "differs"
                )
            candidates.append(
                (
                    best[0],
                    entry["record_id"],
                    entry,
                    best,
                    matched_ids,
                    country_context,
                    identifier_comparisons,
                )
            )
        candidates.sort(key=lambda item: (not bool(item[4]), -item[0], item[1]))
        omitted += max(0, len(candidates) - max_candidates)
        for _, _, entry, best, ids, country_context, id_comparisons in candidates[
            :max_candidates
        ]:
            key = [entity["entity_id"], snapshot["snapshot_id"], entry["record_id"]]
            alias_quality = [
                a.get("quality")
                for a in entry.get("alias_details", [])
                if a.get("name") == best[2]
            ]
            left_type, right_type = _entity_category(
                entity.get("entity_type")
            ), _entity_category(entry.get("entity_type"))
            type_context = (
                "unknown"
                if not left_type or not right_type
                else "corroborates" if left_type == right_type else "differs"
            )
            findings.append(
                {
                    "finding_id": "screening_candidates-"
                    + sha256_bytes(canonical_json(key))[:24],
                    "investigation_id": "screening_candidates",
                    "title": "Official-list identity candidate",
                    "observation": f"Entity {entity['entity_id']} has a name or identifier candidate in {entry['list_name']}: {entry['name']}. This requires identity review.",
                    "entity_ids": [entity["entity_id"]],
                    "record_refs": [
                        {"table": "entities", "record_id": entity["entity_id"]}
                    ],
                    "metrics": {
                        "name_similarity": format(
                            best[0].quantize(Decimal("0.0001")), "f"
                        ),
                        "minimum_similarity": str(minimum_score),
                        "entity_name_compared": best[1],
                        "source_name_compared": best[2],
                        "identifier_matches": ids,
                        "identifier_comparisons": id_comparisons,
                        "entity_type_context": type_context,
                        "entity_type_supplied": entity.get("entity_type"),
                        "source_entity_type": entry.get("entity_type"),
                        "country_context": country_context,
                        "source_countries": countries,
                        "alias_quality": alias_quality,
                        "listing_start_date": entry.get("start_date"),
                        "listing_end_date": entry.get("end_date"),
                        "source_updated_at": snapshot.get("metadata", {}).get(
                            "source_updated_at"
                        ),
                        "list_name": entry["list_name"],
                        "programs": entry.get("programs", []),
                    },
                    "unknowns": [
                        "Identity equivalence and the legal effect of this specific listing require independent review.",
                        "Missing listing dates do not establish membership on the case's historical as-of date.",
                    ],
                    "alternatives": [
                        "Unrelated people or organizations may share a name, alias, or an unqualified registration number."
                    ],
                    "falsifiers": [
                        "Authoritative identity documents, dates of birth, full addresses, or registration jurisdictions may establish that these are different entities."
                    ],
                    "source_refs": [
                        {
                            "snapshot_id": snapshot["snapshot_id"],
                            "record_id": entry["record_id"],
                            "source_id": snapshot["source_id"],
                        }
                    ],
                }
            )
    return findings, {
        "source_records_considered": len(active),
        "source_records_excluded_by_dates": len(entries) - len(active),
        "candidates_omitted_by_display_limit": omitted,
    }
